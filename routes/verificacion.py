import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from models import db, Persona, Movimiento
from services.facial_service import FacialService
from utils.helpers import guardar_imagen
from pytz import timezone  # Necesitas instalar pytz

verificacion_bp = Blueprint('verificacion', __name__)

# Zona horaria de Venezuela (UTC-4)
VEN_TZ = timezone('America/Caracas')

def get_venezuela_time():
    """Retorna la hora actual de Venezuela"""
    return datetime.now(VEN_TZ)


@verificacion_bp.route('/verificar', methods=['POST'])
def verificar_identidad():
    if 'imagen' not in request.files:
        return jsonify({'error': 'Se requiere una imagen para verificar'}), 400
    archivo = request.files['imagen']
    if archivo.filename == '':
        return jsonify({'error': 'No se selecciono ningun archivo'}), 400
    carpeta = current_app.config['UPLOAD_FOLDER_MOVIMIENTOS']
    try:
        nombre_archivo = guardar_imagen(archivo, carpeta, prefijo='verif')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    ruta_imagen = os.path.join(carpeta, nombre_archivo)
    threshold = current_app.config['FACE_DISTANCE_THRESHOLD']
    servicio = FacialService(threshold=threshold)
    try:
        servicio.preprocesar_imagen(ruta_imagen)
        encoding_consulta = servicio.extraer_encoding(ruta_imagen)
        if encoding_consulta is None:
            return jsonify({
                'verificado': False,
                'error': 'No se detecto ningun rostro en la imagen proporcionada.'
            }), 422
        personas = Persona.query.filter(
            Persona.activo == True,
            Persona.encoding_facial.isnot(None)
        ).all()
        if not personas:
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
            try:
                os.remove(ruta_imagen)
            except OSError:
                pass
            return jsonify({
                'verificado': False,
                'mensaje': 'No se encontro ninguna coincidencia en el sistema',
                'personas_comparadas': len(personas_encodings)
            }), 200
        persona_encontrada = resultado['persona']

        # **NUEVO: Determinar el tipo de movimiento basado en el último registro**
        ultimo_movimiento = Movimiento.query.filter_by(
            cedula=persona_encontrada.cedula
        ).order_by(Movimiento.fecha_hora.desc()).first()

        # Si no hay movimientos previos o el último fue "salida", registrar "entrada"
        # Si el último fue "entrada", registrar "salida"
        if ultimo_movimiento is None or ultimo_movimiento.tipo == 'salida':
            tipo_movimiento = 'entrada'
        else:
            tipo_movimiento = 'salida'

        # Registrar el movimiento con el tipo determinado
        movimiento = Movimiento(
            cedula=persona_encontrada.cedula,
            tipo=tipo_movimiento,
            imagen_path=nombre_archivo,
            observacion=f'Registro automático: {tipo_movimiento}',
            fecha_hora=get_venezuela_time(),
            confianza_verificacion=resultado['confianza']  # Opcional: guardar la confianza
        )
        db.session.add(movimiento)
        db.session.commit()

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
            'imagen_verificacion': nombre_archivo,
            'movimiento_registrado': {
                'tipo': tipo_movimiento,
                'fecha_hora': movimiento.fecha_hora.isoformat(),
                'id': movimiento.id
            }
        }), 200
    except Exception as e:
        try:
            os.remove(ruta_imagen)
        except OSError:
            pass
        current_app.logger.error(f"Error en verificacion facial: {str(e)}")
        return jsonify({'error': f'Error interno durante verificacion: {str(e)}'}), 500
