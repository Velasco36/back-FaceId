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

        # Registrar automáticamente una entrada con HORA DE VENEZUELA
        movimiento = Movimiento(
            cedula=persona_encontrada.cedula,
            tipo='entrada',
            imagen_path=nombre_archivo,
            observacion='Registro automático por verificación facial',
            fecha_hora=get_venezuela_time()  # CAMBIADO: ahora usa hora de Venezuela
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
                'tipo': 'entrada',
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


@verificacion_bp.route('/verificar/<cedula>', methods=['POST'])
def verificar_contra_cedula(cedula: str):
    persona = Persona.query.filter_by(cedula=cedula, activo=True).first()
    if not persona:
        return jsonify({'error': f"No se encontro persona activa con cedula '{cedula}'"}), 404

    if persona.encoding_facial is None:
        return jsonify({'error': 'La persona no tiene encoding facial registrado'}), 422

    if 'imagen' not in request.files:
        return jsonify({'error': 'Se requiere una imagen'}), 400

    archivo = request.files['imagen']
    carpeta = current_app.config['UPLOAD_FOLDER_MOVIMIENTOS']

    try:
        nombre_archivo = guardar_imagen(archivo, carpeta, prefijo=f'verif_{cedula}')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    ruta_imagen = os.path.join(carpeta, nombre_archivo)
    threshold = current_app.config['FACE_DISTANCE_THRESHOLD']
    servicio = FacialService(threshold=threshold)

    try:
        servicio.preprocesar_imagen(ruta_imagen)
        encoding_consulta = servicio.extraer_encoding(ruta_imagen)

        if encoding_consulta is None:
            os.remove(ruta_imagen)
            return jsonify({'verificado': False, 'error': 'No se detecto rostro en la imagen'}), 422

        import numpy as np
        encoding_registrado = np.array(persona.get_encoding(), dtype=np.float64)
        distancia = float(np.linalg.norm(encoding_registrado - encoding_consulta))
        coincide = distancia <= threshold
        confianza = max(0.0, round(1.0 - (distancia / threshold), 4)) if coincide else 0.0

        movimiento = None  # Inicializar variable

        # Si la verificación es exitosa, registrar entrada con HORA DE VENEZUELA
        if coincide:
            movimiento = Movimiento(
                cedula=persona.cedula,
                tipo='entrada',
                imagen_path=nombre_archivo,
                observacion='Registro automático por verificación facial con cédula',
                fecha_hora=get_venezuela_time()  # CAMBIADO: ahora usa hora de Venezuela
            )
            db.session.add(movimiento)
            db.session.commit()

        return jsonify({
            'verificado': coincide,
            'persona': {'id': persona.id, 'nombre': persona.nombre, 'cedula': persona.cedula},
            'confianza': confianza,
            'distancia': round(distancia, 4),
            'movimiento_registrado': {
                'tipo': 'entrada',
                'fecha_hora': movimiento.fecha_hora.isoformat(),
                'id': movimiento.id
            } if coincide else None
        }), 200

    except Exception as e:
        try:
            os.remove(ruta_imagen)
        except OSError:
            pass
        return jsonify({'error': f'Error en verificacion: {str(e)}'}), 500
