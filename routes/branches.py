from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Sucursal
from functools import wraps
from routes.auth import get_contexto_actual

sucursal_bp = Blueprint('sucursal', __name__)


# ─────────────────────────────────────────────
# DECORATOR — solo admin_empresa
# ─────────────────────────────────────────────
def solo_admin_empresa(f):
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        ctx = get_contexto_actual()
        if ctx['rol'] not in ('admin_empresa', 'super_admin'):
            return jsonify({'error': 'Acceso denegado. Se requiere rol admin_empresa'}), 403
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
# LISTAR sucursales de la empresa
# ─────────────────────────────────────────────
@sucursal_bp.route('/sucursales', methods=['GET'])
@jwt_required()
def listar_sucursales():
    ctx        = get_contexto_actual()
    solo_activas = request.args.get('activo', 'true').lower() != 'false'

    query = Sucursal.query.filter_by(empresa_id=ctx['empresa_id'])

    if solo_activas:
        query = query.filter_by(activo=True)

    sucursales = query.order_by(Sucursal.es_matriz.desc(), Sucursal.nombre.asc()).all()

    return jsonify({
        'sucursales': [s.to_dict() for s in sucursales],
        'total': len(sucursales)
    }), 200


# ─────────────────────────────────────────────
# OBTENER sucursal por id
# ─────────────────────────────────────────────
@sucursal_bp.route('/sucursales/<int:sucursal_id>', methods=['GET'])
@jwt_required()
def obtener_sucursal(sucursal_id):
    ctx = get_contexto_actual()

    sucursal = Sucursal.query.filter_by(
        id=sucursal_id,
        empresa_id=ctx['empresa_id']
    ).first_or_404()

    return jsonify({'sucursal': sucursal.to_dict()}), 200


# ─────────────────────────────────────────────
# CREAR sucursal
# ─────────────────────────────────────────────
@sucursal_bp.route('/sucursales', methods=['POST'])
@solo_admin_empresa
def crear_sucursal():
    ctx  = get_contexto_actual()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Se requiere JSON en el body'}), 400

    nombre = data.get('nombre', '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre es requerido'}), 400

    sucursal = Sucursal(
        nombre=nombre,
        direccion=data.get('direccion'),
        telefono=data.get('telefono'),
        es_matriz=False,           # solo una matriz por empresa
        empresa_id=ctx['empresa_id']
    )
    db.session.add(sucursal)
    db.session.commit()

    return jsonify({
        'mensaje': 'Sucursal creada exitosamente',
        'sucursal': sucursal.to_dict()
    }), 201


# ─────────────────────────────────────────────
# ACTUALIZAR sucursal
# ─────────────────────────────────────────────
@sucursal_bp.route('/sucursales/<int:sucursal_id>', methods=['PUT'])
@solo_admin_empresa
def actualizar_sucursal(sucursal_id):
    ctx = get_contexto_actual()

    sucursal = Sucursal.query.filter_by(
        id=sucursal_id,
        empresa_id=ctx['empresa_id']
    ).first_or_404()

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Se requiere JSON en el body'}), 400

    for campo in ['nombre', 'direccion', 'telefono']:
        if campo in data:
            setattr(sucursal, campo, data[campo])

    if 'activo' in data:
        if sucursal.es_matriz and not data['activo']:
            return jsonify({'error': 'No se puede desactivar la Sede Principal'}), 400
        sucursal.activo = data['activo']

    db.session.commit()

    return jsonify({
        'mensaje': 'Sucursal actualizada',
        'sucursal': sucursal.to_dict()
    }), 200


# ─────────────────────────────────────────────
# DESACTIVAR sucursal
# ─────────────────────────────────────────────
@sucursal_bp.route('/sucursales/<int:sucursal_id>', methods=['DELETE'])
@solo_admin_empresa
def eliminar_sucursal(sucursal_id):
    ctx = get_contexto_actual()

    sucursal = Sucursal.query.filter_by(
        id=sucursal_id,
        empresa_id=ctx['empresa_id']
    ).first_or_404()

    if sucursal.es_matriz:
        return jsonify({'error': 'No se puede eliminar la Sede Principal'}), 400

    # Verificar que no tenga usuarios activos operando en ella
    usuarios_activos = sucursal.usuarios.filter_by(activo=True).count()
    if usuarios_activos > 0:
        return jsonify({
            'error': f'No se puede desactivar. Tiene {usuarios_activos} usuario(s) activo(s) asignado(s)'
        }), 400

    sucursal.activo = False
    db.session.commit()

    return jsonify({'mensaje': f'Sucursal {sucursal.nombre} desactivada'}), 200
