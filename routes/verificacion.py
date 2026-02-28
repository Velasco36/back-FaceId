import os
import traceback
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from models import db, Persona, Movimiento, SesionJornada
from services.facial_service import FacialService
from utils.helpers import guardar_imagen
from routes.auth import get_contexto_actual
from pytz import timezone

verificacion_bp = Blueprint('verificacion', __name__)

VEN_TZ = timezone('America/Caracas')
TIEMPO_MINIMO_ENTRE_REGISTROS = 2


def get_venezuela_time():
    return datetime.now(VEN_TZ).replace(tzinfo=None)


def formatear_tiempo_restante(segundos):
    if segundos < 60:
        return f"{int(segundos)} segundo{'s' if int(segundos) != 1 else ''}"
    minutos = int(segundos // 60)
    seg_restantes = int(segundos % 60)
    if seg_restantes == 0:
        return f"{minutos} minuto{'s' if minutos != 1 else ''}"
    return f"{minutos} minuto{'s' if minutos != 1 else ''} y {seg_restantes} segundo{'s' if seg_restantes != 1 else ''}"


def verificar_registro_reciente(cedula, empresa_id, tiempo_minimo_minutos=TIEMPO_MINIMO_ENTRE_REGISTROS):
    tiempo_limite = get_venezuela_time() - timedelta(minutes=tiempo_minimo_minutos)

    ultimo_movimiento = Movimiento.query.filter_by(
        cedula=cedula,
        empresa_id=empresa_id
    ).order_by(Movimiento.fecha_hora.desc()).first()

    if ultimo_movimiento and ultimo_movimiento.fecha_hora > tiempo_limite:
        tiempo_transcurrido = get_venezuela_time() - ultimo_movimiento.fecha_hora
        segundos_totales    = tiempo_transcurrido.total_seconds()
        segundos_restantes  = (tiempo_minimo_minutos * 60) - segundos_totales

        tiempo_restante = {
            'segundos_totales':  round(segundos_restantes, 1),
            'minutos':           int(segundos_restantes // 60),
            'segundos':          int(segundos_restantes % 60),
            'formato_decimal':   round(segundos_restantes / 60, 1),
            'texto_amigable':    formatear_tiempo_restante(segundos_restantes)
        }
        return True, ultimo_movimiento, tiempo_restante

    return False, ultimo_movimiento, None


# ─────────────────────────────────────────────
# VERIFICAR IDENTIDAD
# ─────────────────────────────────────────────
@verificacion_bp.route('/verificar', methods=['POST'])
@jwt_required()
def verificar_identidad():
    ctx         = get_contexto_actual()
    empresa_id  = ctx['empresa_id']
    sucursal_id = ctx['sucursal_id']
    usuario_id  = ctx['usuario_id']

    if 'imagen' not in request.files:
        return jsonify({'error': 'Se requiere una imagen para verificar'}), 400

    archivo = request.files['imagen']
    if archivo.filename == '':
        return jsonify({'error': 'No se selecciono ningun archivo'}), 400

    carpeta = current_app.config['UPLOAD_FOLDER_MOVIMIENTOS']

    try:
        nombre_archivo = guardar_imagen(archivo, carpeta, prefijo='temp_verif')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    ruta_imagen = os.path.join(carpeta, nombre_archivo)
    current_app.logger.info(f"[VERIFICAR] Imagen guardada en: {ruta_imagen}")

    threshold = current_app.config['FACE_DISTANCE_THRESHOLD']
    servicio  = FacialService(threshold=threshold)

    try:
        servicio.preprocesar_imagen(ruta_imagen)
        encoding_consulta = servicio.extraer_encoding(ruta_imagen)

        if encoding_consulta is None:
            _eliminar_archivo(ruta_imagen)
            return jsonify({
                'verificado': False,
                'error': 'No se detecto ningun rostro en la imagen proporcionada.'
            }), 422

        personas = Persona.query.filter_by(
            empresa_id=empresa_id,
            activo=True
        ).filter(Persona.encoding_facial.isnot(None)).all()

        if not personas:
            _eliminar_archivo(ruta_imagen)
            return jsonify({
                'verificado': False,
                'mensaje': 'No hay personas registradas en la empresa'
            }), 200

        personas_encodings = [
            (p, p.get_encoding()) for p in personas if p.get_encoding() is not None
        ]

        resultado = servicio.comparar_con_base(encoding_consulta, personas_encodings)
        _eliminar_archivo(ruta_imagen)

        if resultado is None:
            return jsonify({
                'verificado': False,
                'mensaje': 'No se encontro ninguna coincidencia en el sistema',
                'personas_comparadas': len(personas_encodings)
            }), 200

        persona_encontrada = resultado['persona']

        tiene_reciente, ultimo_mov, tiempo_restante = verificar_registro_reciente(
            persona_encontrada.cedula,
            empresa_id
        )

        if tiene_reciente:
            segundos_transcurridos = (get_venezuela_time() - ultimo_mov.fecha_hora).total_seconds()
            current_app.logger.warning(
                f"[VERIFICAR] Bloqueado para {persona_encontrada.nombre}. "
                f"Último registro hace {segundos_transcurridos:.1f}s"
            )
            return jsonify({
                'verificado':         True,
                'registro_duplicado': True,
                'mensaje':            '⚠️ Ya se registró un movimiento recientemente.',
                'mensaje_detallado':  f'Debe esperar {tiempo_restante["texto_amigable"]} antes del próximo registro.',
                'persona': {
                    'id':     persona_encontrada.id,
                    'nombre': persona_encontrada.nombre,
                    'cedula': persona_encontrada.cedula,
                },
                'ultimo_registro': {
                    'tipo':          ultimo_mov.tipo,
                    'fecha_hora':    ultimo_mov.fecha_hora.isoformat(),
                    'hace_segundos': round(segundos_transcurridos, 1),
                    'hace_minutos':  round(segundos_transcurridos / 60, 1),
                    'hace_texto':    formatear_tiempo_restante(segundos_transcurridos)
                },
                'tiempo_restante':       tiempo_restante,
                'movimiento_registrado': None
            }), 200

        sesion_abierta = SesionJornada.query.filter_by(
            cedula=persona_encontrada.cedula,
            empresa_id=empresa_id,
            abierta=True
        ).first()

        tipo_movimiento = 'salida' if sesion_abierta else 'entrada'

        hora_vzla = get_venezuela_time()
        current_app.logger.info(
            f"[VERIFICAR] Registrando {tipo_movimiento} para {persona_encontrada.nombre} a las {hora_vzla}"
        )

        movimiento = Movimiento(
            cedula=persona_encontrada.cedula,
            persona_id=persona_encontrada.id,
            tipo=tipo_movimiento,
            observacion=f'Registro automático: {tipo_movimiento}',
            fecha_hora=hora_vzla,
            confianza_verificacion=resultado['confianza'],
            empresa_id=empresa_id,
            sucursal_id=sucursal_id,
            usuario_id=usuario_id,
        )
        db.session.add(movimiento)
        db.session.flush()

        if tipo_movimiento == 'entrada':
            nueva_sesion = SesionJornada(
                cedula=persona_encontrada.cedula,
                persona_id=persona_encontrada.id,
                empresa_id=empresa_id,
                movimiento_entrada_id=movimiento.id,
                sucursal_entrada_id=sucursal_id,
                fecha_entrada=hora_vzla,
                abierta=True,
            )
            db.session.add(nueva_sesion)
        else:
            sesion_abierta.movimiento_salida_id = movimiento.id
            sesion_abierta.sucursal_salida_id   = sucursal_id
            sesion_abierta.fecha_salida         = hora_vzla
            sesion_abierta.abierta              = False

        db.session.commit()
        current_app.logger.info(f"[VERIFICAR] Movimiento #{movimiento.id} registrado")

        return jsonify({
            'verificado':         True,
            'registro_duplicado': False,
            'mensaje':            f'✅ {tipo_movimiento.capitalize()} registrada exitosamente',
            'persona': {
                'id':     persona_encontrada.id,
                'nombre': persona_encontrada.nombre,
                'cedula': persona_encontrada.cedula,
            },
            'confianza':           resultado['confianza'],
            'distancia':           resultado['distancia'],
            'personas_comparadas': len(personas_encodings),
            'movimiento_registrado': {
                'id':        movimiento.id,
                'tipo':      tipo_movimiento,
                'fecha_hora': movimiento.fecha_hora.isoformat(),
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"[VERIFICAR] Error:\n{traceback.format_exc()}")
        _eliminar_archivo(ruta_imagen)
        return jsonify({'error': f'Error interno durante verificacion: {str(e)}'}), 500

# ─────────────────────────────────────────────
# ESTADO DE REGISTRO
# ─────────────────────────────────────────────
@verificacion_bp.route('/estado-registro/<cedula>', methods=['GET'])
@jwt_required()
def consultar_estado_registro(cedula):
    ctx        = get_contexto_actual()
    empresa_id = ctx['empresa_id']

    persona = Persona.query.filter_by(
        cedula=cedula,
        empresa_id=empresa_id,
        activo=True
    ).first()

    if not persona:
        return jsonify({'error': 'Persona no encontrada en la empresa'}), 404

    tiene_reciente, ultimo_mov, tiempo_restante = verificar_registro_reciente(
        cedula, empresa_id
    )

    sesion_abierta = SesionJornada.query.filter_by(
        cedula=cedula,
        empresa_id=empresa_id,
        abierta=True
    ).first()

    proximo_tipo = 'salida' if sesion_abierta else 'entrada'

    if tiene_reciente:
        segundos_transcurridos = (get_venezuela_time() - ultimo_mov.fecha_hora).total_seconds()
        return jsonify({
            'puede_registrarse': False,
            'mensaje':           f'Debe esperar {tiempo_restante["texto_amigable"]}',
            'proximo_tipo':      proximo_tipo,
            'persona': {
                'id':     persona.id,
                'nombre': persona.nombre,
                'cedula': persona.cedula
            },
            'ultimo_registro': {
                'tipo':          ultimo_mov.tipo,
                'sucursal_id':   ultimo_mov.sucursal_id,
                'fecha_hora':    ultimo_mov.fecha_hora.isoformat(),
                'hace_segundos': round(segundos_transcurridos, 1),
                'hace_minutos':  round(segundos_transcurridos / 60, 1),
                'hace_texto':    formatear_tiempo_restante(segundos_transcurridos)
            },
            'tiempo_restante': tiempo_restante
        }), 200

    return jsonify({
        'puede_registrarse':  True,
        'mensaje':            f'Puede registrar: {proximo_tipo}',
        'proximo_tipo':       proximo_tipo,
        'persona': {
            'id':     persona.id,
            'nombre': persona.nombre,
            'cedula': persona.cedula
        },
        'jornada_activa':    sesion_abierta.to_dict() if sesion_abierta else None,
        'ultimo_movimiento': ultimo_mov.to_dict() if ultimo_mov else None
    }), 200


# ── Helper ────────────────────────────────────────────────────────────────────
def _eliminar_archivo(ruta):
    try:
        if os.path.exists(ruta):
            os.remove(ruta)
    except OSError as e:
        current_app.logger.warning(f"[VERIFICAR] No se pudo eliminar archivo temporal: {e}")
