import os
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from models import db, Persona
from services.facial_service import FacialService
from utils.helpers import guardar_imagen
from routes.auth import get_contexto_actual

personas_bp = Blueprint('personas', __name__)


@personas_bp.route('/registrar', methods=['POST'])
@jwt_required()
def registrar_persona():
    ctx         = get_contexto_actual()
    empresa_id  = ctx['empresa_id']
    sucursal_id = ctx['sucursal_id']

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

    if Persona.query.filter_by(cedula=cedula, empresa_id=empresa_id).first():
        return jsonify({'error': f"La cedula '{cedula}' ya esta registrada en la empresa"}), 409

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

    persona = Persona(
        cedula=cedula,
        nombre=nombre,
        imagen_path=nombre_archivo,
        empresa_id=empresa_id,
        sucursal_registro_id=sucursal_id
    )
    persona.set_encoding(encoding)

    db.session.add(persona)
    db.session.commit()

    return jsonify({
        'registrado': True,
        'mensaje': f'{nombre} registrado exitosamente',
        'persona': persona.to_dict()
    }), 201


@personas_bp.route('/personas', methods=['GET'])
@jwt_required()
def listar_personas():
    ctx        = get_contexto_actual()
    empresa_id = ctx['empresa_id']

    solo_activos    = request.args.get('activo', 'true').lower() != 'false'
    busqueda        = request.args.get('q', '').strip()
    sucursal_filtro = request.args.get('sucursal_id', None)

    query = Persona.query.filter_by(empresa_id=empresa_id)

    if solo_activos:
        query = query.filter_by(activo=True)

    if sucursal_filtro and ctx['rol'] == 'admin_empresa':
        query = query.filter_by(sucursal_registro_id=sucursal_filtro)

    if busqueda:
        patron = f'%{busqueda}%'
        query = query.filter(
            db.or_(
                Persona.nombre.ilike(patron),
                Persona.cedula.ilike(patron)
            )
        )

    personas = query.order_by(Persona.nombre.asc()).all()

    return jsonify({
        'personas': [p.to_dict() for p in personas],
        'total': len(personas)
    }), 200


@personas_bp.route('/personas/<cedula>', methods=['GET'])
@jwt_required()
def obtener_persona(cedula: str):
    ctx = get_contexto_actual()

    persona = Persona.query.filter_by(
        cedula=cedula,
        empresa_id=ctx['empresa_id']
    ).first()

    if not persona:
        return jsonify({'error': f"No se encontro persona con cedula '{cedula}' en la empresa"}), 404

    return jsonify({'persona': persona.to_dict()}), 200


@personas_bp.route('/personas/<cedula>', methods=['PUT'])
@jwt_required()
def actualizar_persona(cedula: str):
    ctx = get_contexto_actual()

    persona = Persona.query.filter_by(
        cedula=cedula,
        empresa_id=ctx['empresa_id']
    ).first()

    if not persona:
        return jsonify({'error': f"No se encontro persona con cedula '{cedula}'"}), 404

    nuevo_nombre = request.form.get('nombre', '').strip()
    if nuevo_nombre:
        persona.nombre = nuevo_nombre

    if 'imagen' in request.files and request.files['imagen'].filename != '':
        archivo  = request.files['imagen']
        carpeta  = current_app.config['UPLOAD_FOLDER_REGISTROS']

        try:
            nombre_archivo = guardar_imagen(archivo, carpeta, prefijo=f"reg_{cedula}")
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        ruta_imagen = os.path.join(carpeta, nombre_archivo)
        servicio    = FacialService(threshold=current_app.config['FACE_DISTANCE_THRESHOLD'])
        servicio.preprocesar_imagen(ruta_imagen)

        try:
            encoding = servicio.extraer_encoding(ruta_imagen)
        except ValueError as e:
            os.remove(ruta_imagen)
            return jsonify({'error': f'Error procesando imagen: {str(e)}'}), 422

        if encoding is None:
            os.remove(ruta_imagen)
            return jsonify({'error': 'No se detecto ningun rostro en la imagen'}), 422

        if persona.imagen_path:
            ruta_anterior = os.path.join(carpeta, persona.imagen_path)
            if os.path.exists(ruta_anterior):
                os.remove(ruta_anterior)

        persona.imagen_path = nombre_archivo
        persona.set_encoding(encoding)

    db.session.commit()

    return jsonify({
        'actualizado': True,
        'mensaje': f'{persona.nombre} actualizado exitosamente',
        'persona': persona.to_dict()
    }), 200


@personas_bp.route('/personas/<cedula>', methods=['DELETE'])
@jwt_required()
def desactivar_persona(cedula: str):
    ctx = get_contexto_actual()

    persona = Persona.query.filter_by(
        cedula=cedula,
        empresa_id=ctx['empresa_id']
    ).first()

    if not persona:
        return jsonify({'error': f"No se encontro persona con cedula '{cedula}'"}), 404

    persona.activo = False
    db.session.commit()

    return jsonify({
        'desactivado': True,
        'mensaje': f'{persona.nombre} desactivado exitosamente'
    }), 200


@personas_bp.route('/personas/<cedula>/activar', methods=['PATCH'])
@jwt_required()
def activar_persona(cedula: str):
    ctx = get_contexto_actual()

    persona = Persona.query.filter_by(
        cedula=cedula,
        empresa_id=ctx['empresa_id']
    ).first()

    if not persona:
        return jsonify({'error': f"No se encontro persona con cedula '{cedula}'"}), 404

    persona.activo = True
    db.session.commit()

    return jsonify({
        'activado': True,
        'mensaje': f'{persona.nombre} activado exitosamente',
        'persona': persona.to_dict()
    }), 200
