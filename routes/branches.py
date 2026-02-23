from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from models import db, Sucursal, Empresa, Usuario
from utils.decorators import admin_required, admin_empresa_required

sucursal_bp = Blueprint('sucursal', __name__)

# Crear una nueva sucursal
@sucursal_bp.route('/sucursales', methods=['POST'])
@jwt_required()
def crear_sucursal():
    try:
        data = request.get_json()
        current_user = get_jwt_identity()
        usuario = Usuario.query.get(current_user['id'])

        # Validar campos requeridos
        if not data.get('nombre') or not data.get('empresa_id'):
            return jsonify({'error': 'Nombre y empresa_id son requeridos'}), 400

        # Verificar permisos
        if not usuario.es_admin() and usuario.empresa_id != data['empresa_id']:
            return jsonify({'error': 'No tiene permisos para crear sucursales en esta empresa'}), 403

        # Verificar que la empresa existe y está activa
        empresa = Empresa.query.get(data['empresa_id'])
        if not empresa or not empresa.activo:
            return jsonify({'error': 'Empresa no válida o inactiva'}), 400

        # Crear nueva sucursal
        nueva_sucursal = Sucursal(
            nombre=data['nombre'],
            direccion=data.get('direccion'),
            telefono=data.get('telefono'),
            empresa_id=data['empresa_id'],
            activo=data.get('activo', True)
        )

        db.session.add(nueva_sucursal)
        db.session.commit()

        return jsonify({
            'mensaje': 'Sucursal creada exitosamente',
            'sucursal': nueva_sucursal.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Obtener todas las sucursales (con filtros)
@sucursal_bp.route('/sucursales', methods=['GET'])
@jwt_required()
def listar_sucursales():
    try:
        # Obtener parámetros de consulta
        pagina = request.args.get('pagina', 1, type=int)
        por_pagina = request.args.get('por_pagina', 10, type=int)
        empresa_id = request.args.get('empresa_id', type=int)
        solo_activas = request.args.get('solo_activas', 'true').lower() == 'true'

        # Construir query
        query = Sucursal.query

        if empresa_id:
            query = query.filter_by(empresa_id=empresa_id)

        if solo_activas:
            query = query.filter_by(activo=True)

        # Paginación
        sucursales = query.order_by(Sucursal.nombre).paginate(
            page=pagina,
            per_page=por_pagina,
            error_out=False
        )

        return jsonify({
            'sucursales': [sucursal.to_dict() for sucursal in sucursales.items],
            'total': sucursales.total,
            'pagina': pagina,
            'por_pagina': por_pagina,
            'total_paginas': sucursales.pages
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Obtener todas las sucursales de una empresa específica
@sucursal_bp.route('/empresas/<int:empresa_id>/sucursales', methods=['GET'])
@jwt_required()
def listar_sucursales_por_empresa(empresa_id):
    try:
        # Verificar que la empresa existe
        empresa = Empresa.query.get_or_404(empresa_id)

        # Obtener parámetros de consulta
        solo_activas = request.args.get('solo_activas', 'true').lower() == 'true'

        # Construir query
        query = Sucursal.query.filter_by(empresa_id=empresa_id)

        if solo_activas:
            query = query.filter_by(activo=True)

        sucursales = query.order_by(Sucursal.nombre).all()

        return jsonify({
            'empresa_id': empresa_id,
            'empresa_nombre': empresa.nombre,
            'total': len(sucursales),
            'sucursales': [sucursal.to_dict() for sucursal in sucursales]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Obtener una sucursal por ID
@sucursal_bp.route('/sucursales/<int:sucursal_id>', methods=['GET'])
@jwt_required()
def obtener_sucursal(sucursal_id):
    try:
        sucursal = Sucursal.query.get_or_404(sucursal_id)
        return jsonify(sucursal.to_dict()), 200
    except Exception as e:
        return jsonify({'error': 'Sucursal no encontrada'}), 404

# Actualizar una sucursal
@sucursal_bp.route('/sucursales/<int:sucursal_id>', methods=['PUT'])
@jwt_required()
def actualizar_sucursal(sucursal_id):
    try:
        sucursal = Sucursal.query.get_or_404(sucursal_id)
        data = request.get_json()
        current_user = get_jwt_identity()
        usuario = Usuario.query.get(current_user['id'])

        # Verificar permisos
        if not usuario.es_admin() and usuario.empresa_id != sucursal.empresa_id:
            return jsonify({'error': 'No tiene permisos para modificar esta sucursal'}), 403

        # Actualizar campos
        if 'nombre' in data:
            sucursal.nombre = data['nombre']

        if 'direccion' in data:
            sucursal.direccion = data['direccion']

        if 'telefono' in data:
            sucursal.telefono = data['telefono']

        if 'activo' in data:
            # Verificar si hay usuarios activos antes de desactivar
            if not data['activo'] and sucursal.activo:
                usuarios_activos = Usuario.query.filter_by(sucursal_id=sucursal_id, activo=True).count()
                if usuarios_activos > 0:
                    return jsonify({
                        'error': 'No se puede desactivar la sucursal porque tiene usuarios activos',
                        'usuarios_activos': usuarios_activos
                    }), 400
            sucursal.activo = data['activo']

        sucursal.fecha_actualizacion = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'mensaje': 'Sucursal actualizada exitosamente',
            'sucursal': sucursal.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Eliminar una sucursal (soft delete)
@sucursal_bp.route('/sucursales/<int:sucursal_id>', methods=['DELETE'])
@jwt_required()
def eliminar_sucursal(sucursal_id):
    try:
        sucursal = Sucursal.query.get_or_404(sucursal_id)
        current_user = get_jwt_identity()
        usuario = Usuario.query.get(current_user['id'])

        # Verificar permisos
        if not usuario.es_admin() and usuario.empresa_id != sucursal.empresa_id:
            return jsonify({'error': 'No tiene permisos para eliminar esta sucursal'}), 403

        # Verificar si tiene usuarios activos
        usuarios_activos = Usuario.query.filter_by(sucursal_id=sucursal_id, activo=True).count()
        if usuarios_activos > 0:
            return jsonify({
                'error': 'No se puede eliminar la sucursal porque tiene usuarios activos',
                'usuarios_activos': usuarios_activos
            }), 400

        # Verificar si tiene personas activas
        from models import Persona
        personas_activas = Persona.query.filter_by(sucursal_id=sucursal_id, activo=True).count()
        if personas_activas > 0:
            return jsonify({
                'error': 'No se puede eliminar la sucursal porque tiene personas registradas activas',
                'personas_activas': personas_activas
            }), 400

        # Soft delete
        sucursal.activo = False
        sucursal.fecha_actualizacion = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'mensaje': 'Sucursal desactivada exitosamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Obtener estadísticas de una sucursal
@sucursal_bp.route('/sucursales/<int:sucursal_id>/estadisticas', methods=['GET'])
@jwt_required()
def estadisticas_sucursal(sucursal_id):
    try:
        sucursal = Sucursal.query.get_or_404(sucursal_id)

        from models import Usuario, Persona, Movimiento

        stats = {
            'total_usuarios': Usuario.query.filter_by(sucursal_id=sucursal_id).count(),
            'usuarios_activos': Usuario.query.filter_by(sucursal_id=sucursal_id, activo=True).count(),
            'total_personas': Persona.query.filter_by(sucursal_id=sucursal_id).count(),
            'personas_activas': Persona.query.filter_by(sucursal_id=sucursal_id, activo=True).count(),
            'total_movimientos': Movimiento.query.filter_by(sucursal_id=sucursal_id).count(),
            'movimientos_hoy': Movimiento.query.filter(
                Movimiento.sucursal_id == sucursal_id,
                Movimiento.fecha_hora >= datetime.utcnow().date()
            ).count()
        }

        return jsonify(stats), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
