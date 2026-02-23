import os
import traceback
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from models import db, Persona, Movimiento
from services.facial_service import FacialService
from utils.helpers import guardar_imagen
from pytz import timezone

verificacion_bp = Blueprint('verificacion', __name__)

# Zona horaria de Venezuela (UTC-4)
VEN_TZ = timezone('America/Caracas')

# Tiempo mínimo entre registros de la misma persona (en minutos)
TIEMPO_MINIMO_ENTRE_REGISTROS = 2


def get_venezuela_time():
    """Retorna la hora actual de Venezuela como naive datetime (sin tzinfo)"""
    return datetime.now(VEN_TZ).replace(tzinfo=None)


def formatear_tiempo_restante(segundos):
    """
    Formatea el tiempo restante en minutos y segundos de forma legible
    Ejemplo: 1 minuto 30 segundos, 45 segundos, etc.
    """
    if segundos < 60:
        return f"{int(segundos)} segundo{'s' if int(segundos) != 1 else ''}"
    else:
        minutos = int(segundos // 60)
        seg_restantes = int(segundos % 60)

        if seg_restantes == 0:
            return f"{minutos} minuto{'s' if minutos != 1 else ''}"
        else:
            return f"{minutos} minuto{'s' if minutos != 1 else ''} y {seg_restantes} segundo{'s' if seg_restantes != 1 else ''}"


def verificar_registro_reciente(cedula, tiempo_minimo_minutos=TIEMPO_MINIMO_ENTRE_REGISTROS):
    """
    Verifica si la persona ya tiene un registro en los últimos X minutos.
    Retorna (tiene_registro_reciente, ultimo_movimiento, tiempo_restante_dict)
    """
    tiempo_limite = get_venezuela_time() - timedelta(minutes=tiempo_minimo_minutos)

    ultimo_movimiento = Movimiento.query.filter_by(
        cedula=cedula
    ).order_by(Movimiento.fecha_hora.desc()).first()

    if ultimo_movimiento and ultimo_movimiento.fecha_hora > tiempo_limite:
        # Calcular tiempo restante
        tiempo_transcurrido = get_venezuela_time() - ultimo_movimiento.fecha_hora
        segundos_totales = tiempo_transcurrido.total_seconds()
        segundos_restantes = (tiempo_minimo_minutos * 60) - segundos_totales

        # Crear diccionario con diferentes formatos de tiempo
        tiempo_restante = {
            'segundos_totales': round(segundos_restantes, 1),
            'minutos': int(segundos_restantes // 60),
            'segundos': int(segundos_restantes % 60),
            'formato_decimal': round(segundos_restantes / 60, 1),  # minutos en decimal (ej: 1.5)
            'texto_amigable': formatear_tiempo_restante(segundos_restantes)
        }

        return True, ultimo_movimiento, tiempo_restante

    return False, ultimo_movimiento, None


@verificacion_bp.route('/verificar', methods=['POST'])
def verificar_identidad():
    if 'imagen' not in request.files:
        return jsonify({'error': 'Se requiere una imagen para verificar'}), 400

    archivo = request.files['imagen']
    if archivo.filename == '':
        return jsonify({'error': 'No se selecciono ningun archivo'}), 400

    carpeta = current_app.config['UPLOAD_FOLDER_MOVIMIENTOS']

    # Guardar imagen temporal para procesar
    try:
        nombre_archivo = guardar_imagen(archivo, carpeta, prefijo='temp_verif')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    ruta_imagen = os.path.join(carpeta, nombre_archivo)

    # Debug: verificar que el archivo existe
    current_app.logger.info(f"[VERIFICAR] Imagen guardada en: {ruta_imagen}")
    current_app.logger.info(f"[VERIFICAR] Archivo existe: {os.path.exists(ruta_imagen)}")

    threshold = current_app.config['FACE_DISTANCE_THRESHOLD']
    servicio = FacialService(threshold=threshold)

    try:
        servicio.preprocesar_imagen(ruta_imagen)
        encoding_consulta = servicio.extraer_encoding(ruta_imagen)

        if encoding_consulta is None:
            # Eliminar imagen si no se detectó rostro
            try:
                os.remove(ruta_imagen)
            except OSError:
                pass
            return jsonify({
                'verificado': False,
                'error': 'No se detecto ningun rostro en la imagen proporcionada.'
            }), 422

        personas = Persona.query.filter(
            Persona.activo == True,
            Persona.encoding_facial.isnot(None)
        ).all()

        if not personas:
            try:
                os.remove(ruta_imagen)
            except OSError:
                pass
            return jsonify({
                'verificado': False,
                'mensaje': 'No hay personas registradas en el sistema'
            }), 200

        personas_encodings = []
        for persona in personas:
            enc = persona.get_encoding()
            if enc is not None:
                personas_encodings.append((persona, enc))

        resultado = servicio.comparar_con_base(encoding_consulta, personas_encodings)

        # Eliminar imagen temporal después de procesar (siempre)
        try:
            os.remove(ruta_imagen)
            current_app.logger.info(f"[VERIFICAR] Imagen temporal eliminada: {ruta_imagen}")
        except OSError as e:
            current_app.logger.warning(f"[VERIFICAR] No se pudo eliminar imagen temporal: {e}")

        if resultado is None:
            return jsonify({
                'verificado': False,
                'mensaje': 'No se encontro ninguna coincidencia en el sistema',
                'personas_comparadas': len(personas_encodings)
            }), 200

        # ── Coincidencia encontrada ──────────────────────────────────────────
        persona_encontrada = resultado['persona']

        # ========== VALIDACIÓN MEJORADA: Verificar registro reciente ==========
        tiene_reciente, ultimo_mov, tiempo_restante = verificar_registro_reciente(
            persona_encontrada.cedula
        )

        if tiene_reciente:
            tiempo_transcurrido = get_venezuela_time() - ultimo_mov.fecha_hora
            segundos_transcurridos = tiempo_transcurrido.total_seconds()

            current_app.logger.warning(
                f"[VERIFICAR] Registro bloqueado para {persona_encontrada.nombre}. "
                f"Último registro hace {segundos_transcurridos:.1f} segundos"
            )

            return jsonify({
                'verificado': True,
                'registro_duplicado': True,
                'mensaje': f'⚠️ Ya se registró un movimiento recientemente.',
                'mensaje_detallado': f'Debe esperar {tiempo_restante["texto_amigable"]} antes del próximo registro.',
                'persona': {
                    'id': persona_encontrada.id,
                    'nombre': persona_encontrada.nombre,
                    'cedula': persona_encontrada.cedula,
                },
                'ultimo_registro': {
                    'tipo': ultimo_mov.tipo,
                    'fecha_hora': ultimo_mov.fecha_hora.isoformat(),
                    'hace_segundos': round(segundos_transcurridos, 1),
                    'hace_minutos': round(segundos_transcurridos / 60, 1),
                    'hace_texto': formatear_tiempo_restante(segundos_transcurridos)
                },
                'tiempo_restante': tiempo_restante,
                'movimiento_registrado': None
            }), 200
        # ========== FIN DE LA VALIDACIÓN MEJORADA ==========

        # Determinar tipo de movimiento basado en el último registro
        if ultimo_mov is None or ultimo_mov.tipo == 'salida':
            tipo_movimiento = 'entrada'
        else:
            tipo_movimiento = 'salida'

        # Hora Venezuela sin tzinfo para compatibilidad con la BD
        hora_vzla = get_venezuela_time()

        current_app.logger.info(f"[VERIFICAR] Registrando {tipo_movimiento} para {persona_encontrada.nombre} a las {hora_vzla}")

        # Crear movimiento SIN imagen
        movimiento = Movimiento(
            cedula=persona_encontrada.cedula,
            tipo=tipo_movimiento,
            observacion=f'Registro automático: {tipo_movimiento}',
            fecha_hora=hora_vzla,
            confianza_verificacion=resultado['confianza']
        )

        db.session.add(movimiento)
        db.session.commit()

        current_app.logger.info(f"[VERIFICAR] Movimiento #{movimiento.id} registrado (sin imagen)")

        return jsonify({
            'verificado': True,
            'registro_duplicado': False,
            'mensaje': f'✅ {tipo_movimiento.capitalize()} registrada exitosamente',
            'persona': {
                'id': persona_encontrada.id,
                'nombre': persona_encontrada.nombre,
                'cedula': persona_encontrada.cedula,
            },
            'confianza': resultado['confianza'],
            'distancia': resultado['distancia'],
            'personas_comparadas': len(personas_encodings),
            'movimiento_registrado': {
                'id': movimiento.id,
                'tipo': tipo_movimiento,
                'fecha_hora': movimiento.fecha_hora.isoformat(),
            }
        }), 200

    except Exception as e:
        # Log completo del error
        current_app.logger.error(f"[VERIFICAR] Error en verificacion facial:\n{traceback.format_exc()}")
        # Intentar eliminar imagen temporal si existe
        try:
            if os.path.exists(ruta_imagen):
                os.remove(ruta_imagen)
        except OSError:
            pass
        return jsonify({'error': f'Error interno durante verificacion: {str(e)}'}), 500


@verificacion_bp.route('/estado-registro/<cedula>', methods=['GET'])
def consultar_estado_registro(cedula):
    """
    Endpoint para consultar si una persona puede registrarse
    """
    persona = Persona.query.filter_by(cedula=cedula, activo=True).first()
    if not persona:
        return jsonify({'error': 'Persona no encontrada'}), 404

    tiene_reciente, ultimo_mov, tiempo_restante = verificar_registro_reciente(cedula)

    if tiene_reciente:
        tiempo_transcurrido = get_venezuela_time() - ultimo_mov.fecha_hora
        segundos_transcurridos = tiempo_transcurrido.total_seconds()

        return jsonify({
            'puede_registrarse': False,
            'mensaje': f'Debe esperar {tiempo_restante["texto_amigable"]}',
            'persona': {
                'id': persona.id,
                'nombre': persona.nombre,
                'cedula': persona.cedula
            },
            'ultimo_registro': {
                'tipo': ultimo_mov.tipo,
                'fecha_hora': ultimo_mov.fecha_hora.isoformat(),
                'hace_segundos': round(segundos_transcurridos, 1),
                'hace_minutos': round(segundos_transcurridos / 60, 1),
                'hace_texto': formatear_tiempo_restante(segundos_transcurridos)
            },
            'tiempo_restante': tiempo_restante
        }), 200
    else:
        return jsonify({
            'puede_registrarse': True,
            'mensaje': 'Puede registrar movimiento',
            'persona': {
                'id': persona.id,
                'nombre': persona.nombre,
                'cedula': persona.cedula
            },
            'ultimo_movimiento': ultimo_mov.to_dict() if ultimo_mov else None
        }), 200
