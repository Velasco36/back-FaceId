
import os
from flask import Blueprint, request, jsonify, current_app
from models import db, Persona
from services.facial_service import FacialService
from utils.helpers import guardar_imagen

personas_bp = Blueprint('personas', __name__)


@personas_bp.route('/registrar', methods=['POST'])
def registrar_persona():
    cedula = request.form.get('cedula', '').strip()
    nombre = request.form.get('nombre', '').strip()

    errores = {}
    if not cedula:
        errores['cedula'] = 'La cedula es requerida'
    if not nombre:
        errores['nombre'] = 'El nombre es requerido'
    if errores:
        return jsonify({'error': 'Datos incompletos', 'detalles': errores}), 400

    if 'imagen' not in request.files:
        return jsonify({'error': 'Se requiere una imagen'}), 400

    archivo = request.files['imagen']
    if archivo.filename == '':
        return jsonify({'error': 'No se selecciono ningun archivo'}), 400

    if Persona.query.filter_by(cedula=cedula).first():
        return jsonify({'error': f"La cedula '{cedula}' ya esta registrada"}), 409

    carpeta = current_app.config['UPLOAD_FOLDER_REGISTROS']
    try:
        nombre_archivo = guardar_imagen(archivo, carpeta, prefijo=f"reg_{cedula}")
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    ruta_imagen = os.path.join(carpeta, nombre_archivo)
    servicio = FacialService(threshold=current_app.config['FACE_DISTANCE_THRESHOLD'])
    servicio.preprocesar_imagen(ruta_imagen)

    try:
        encoding = servicio.extraer_encoding(ruta_imagen)
    except ValueError as e:
        os.remove(ruta_imagen)
        return jsonify({'error': f'Error procesando imagen: {str(e)}'}), 422

    if encoding is None:
        os.remove(ruta_imagen)
        return jsonify({
            'error': 'No se detecto ningun rostro en la imagen. '
                     'Asegurese de que la foto sea clara y el rostro este visible.'
        }), 422

    persona = Persona(cedula=cedula, nombre=nombre, imagen_path=nombre_archivo)
    persona.set_encoding(encoding)

    db.session.add(persona)
    db.session.commit()

    return jsonify({
        'registrado': True,
        'mensaje': f'{nombre} registrado exitosamente',
        'persona': persona.to_dict()
    }), 201


@personas_bp.route('/personas', methods=['GET'])
def listar_personas():
    solo_activos = request.args.get('activo', 'true').lower() != 'false'
    busqueda = request.args.get('q', '').strip()

    query = Persona.query

    if solo_activos:
        query = query.filter_by(activo=True)

    if busqueda:
        patron = f'%{busqueda}%'
        query = query.filter(
            db.or_(
                Persona.nombre.ilike(patron),
                Persona.cedula.ilike(patron)
            )
        )

    query = query.order_by(Persona.nombre.asc())
    personas = query.all()

    return jsonify({'personas': [p.to_dict() for p in personas], 'total': len(personas)}), 200


@personas_bp.route('/personas/<cedula>', methods=['GET'])
def obtener_persona(cedula: str):
    persona = Persona.query.filter_by(cedula=cedula).first()
    if not persona:
        return jsonify({'error': f"No se encontro persona con cedula '{cedula}'"}), 404
    return jsonify({'persona': persona.to_dict()}), 200
