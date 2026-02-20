import os
import traceback
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from models import db, Persona, Movimiento
from services.facial_service import FacialService
from utils.helpers import guardar_imagen
from pytz import timezone

verificacion_bp = Blueprint('verificacion', __name__)

# Zona horaria de Venezuela (UTC-4)
VEN_TZ = timezone('America/Caracas')


def get_venezuela_time():
    """Retorna la hora actual de Venezuela como naive datetime (sin tzinfo)"""
    return datetime.now(VEN_TZ).replace(tzinfo=None)


@verificacion_bp.route('/verificar', methods=['POST'])
def verificar_identidad():
    if 'imagen' not in request.files:
        return jsonify({'error': 'Se requiere una imagen para verificar'}), 400

    archivo = request.files['imagen']
    if archivo.filename == '':
        return jsonify({'error': 'No se selecciono ningun archivo'}), 400

    carpeta = current_app.config['UPLOAD_FOLDER_MOVIMIENTOS']

    # Guardar imagen antes de procesar
    try:
        nombre_archivo = guardar_imagen(archivo, carpeta, prefijo='verif')
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

        if resultado is None:
            # Sin coincidencia: eliminar imagen (no hay a quién asociarla)
            try:
                os.remove(ruta_imagen)
            except OSError:
                pass
            return jsonify({
                'verificado': False,
                'mensaje': 'No se encontro ninguna coincidencia en el sistema',
                'personas_comparadas': len(personas_encodings)
            }), 200

        # ── Coincidencia encontrada ──────────────────────────────────────────

        persona_encontrada = resultado['persona']

        # Determinar tipo de movimiento basado en el último registro
        ultimo_movimiento = Movimiento.query.filter_by(
            cedula=persona_encontrada.cedula
        ).order_by(Movimiento.fecha_hora.desc()).first()

        if ultimo_movimiento is None or ultimo_movimiento.tipo == 'salida':
            tipo_movimiento = 'entrada'
        else:
            tipo_movimiento = 'salida'

        # Hora Venezuela sin tzinfo para compatibilidad con la BD
        hora_vzla = get_venezuela_time()

        current_app.logger.info(f"[VERIFICAR] Registrando {tipo_movimiento} para {persona_encontrada.nombre} a las {hora_vzla}")

        movimiento = Movimiento(
            cedula=persona_encontrada.cedula,
            tipo=tipo_movimiento,
            imagen_path=nombre_archivo,         # solo el nombre del archivo
            observacion=f'Registro automático: {tipo_movimiento}',
            fecha_hora=hora_vzla,
            confianza_verificacion=resultado['confianza']
        )

        db.session.add(movimiento)
        db.session.commit()

        # Construir URL completa de la imagen
        base_url = request.host_url.rstrip('/')
        imagen_url = f"{base_url}/uploads/movimientos/{nombre_archivo}"

        current_app.logger.info(f"[VERIFICAR] Movimiento #{movimiento.id} registrado. imagen_url: {imagen_url}")

        return jsonify({
            'verificado': True,
            'persona': {
                'id': persona_encontrada.id,
                'nombre': persona_encontrada.nombre,
                'cedula': persona_encontrada.cedula,
            },
            'confianza': resultado['confianza'],
            'distancia': resultado['distancia'],
            'personas_comparadas': len(personas_encodings),
            'imagen_url': imagen_url,
            'movimiento_registrado': {
                'id': movimiento.id,
                'tipo': tipo_movimiento,
                'fecha_hora': movimiento.fecha_hora.isoformat(),
                'imagen_url': imagen_url,
            }
        }), 200

    except Exception as e:
        # Log completo del error
        current_app.logger.error(f"[VERIFICAR] Error en verificacion facial:\n{traceback.format_exc()}")
        # Eliminar imagen huérfana solo si ocurrió un error inesperado
        try:
            os.remove(ruta_imagen)
        except OSError:
            pass
        return jsonify({'error': f'Error interno durante verificacion: {str(e)}'}), 500
