from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Usuario, Sucursal
from functools import wraps
from routes.auth import get_contexto_actual

usuarios_bp = Blueprint('usuarios', __name__)


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
# LISTAR usuarios de la empresa
# ─────────────────────────────────────────────
@usuarios_bp.route('/usuarios', methods=['GET'])
@jwt_required()
def listar_usuarios():
    ctx        = get_contexto_actual()
    empresa_id = ctx['empresa_id']

    sucursal_filtro = request.args.get('sucursal_id', None)

    query = Usuario.query.filter_by(empresa_id=empresa_id)

    # Admin ve toda la empresa, user solo ve su sucursal
    if ctx['rol'] not in ('admin_empresa', 'super_admin'):
        query = query.filter_by(sucursal_id=ctx['sucursal_id'])
    elif sucursal_filtro:
        query = query.filter_by(sucursal_id=sucursal_filtro)

    usuarios = query.order_by(Usuario.username.asc()).all()
    return jsonify({
        'usuarios': [u.to_dict() for u in usuarios],
        'total': len(usuarios)
    }), 200


# ─────────────────────────────────────────────
# OBTENER usuario por id
# ─────────────────────────────────────────────
@usuarios_bp.route('/usuarios/<int:usuario_id>', methods=['GET'])
@jwt_required()
def obtener_usuario(usuario_id):
    ctx = get_contexto_actual()

    usuario = Usuario.query.filter_by(
        id=usuario_id,
        empresa_id=ctx['empresa_id']
    ).first_or_404()

    return jsonify({'usuario': usuario.to_dict()}), 200


# ─────────────────────────────────────────────
# CREAR usuario
# ─────────────────────────────────────────────
@usuarios_bp.route('/usuarios', methods=['POST'])
@solo_admin_empresa
def crear_usuario():
    ctx  = get_contexto_actual()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Se requiere JSON en el body'}), 400

    username    = data.get('username', '').strip()
    password    = data.get('password', '')
    sucursal_id = data.get('sucursal_id')
    rol         = data.get('rol', 'user')

    errores = {}
    if not username:
        errores['username'] = 'El username es requerido'
    if not password:
        errores['password'] = 'El password es requerido'
    if not sucursal_id:
        errores['sucursal_id'] = 'La sucursal es requerida'
    if errores:
        return jsonify({'error': 'Datos incompletos', 'detalles': errores}), 400

    # Validar que el username no esté en uso
    if Usuario.query.filter_by(username=username).first():
        return jsonify({'error': 'El username ya está en uso'}), 409

    # Validar que la sucursal pertenece a la empresa
    sucursal = Sucursal.query.filter_by(
        id=sucursal_id,
        empresa_id=ctx['empresa_id'],
        activo=True
    ).first()
    if not sucursal:
        return jsonify({'error': 'Sucursal no válida para esta empresa'}), 400

    # Evitar que un admin_empresa cree super_admin
    if rol == 'super_admin' and ctx['rol'] != 'super_admin':
        return jsonify({'error': 'No tienes permisos para asignar ese rol'}), 403

    usuario = Usuario(
        username=username,
        rol=rol,
        empresa_id=ctx['empresa_id'],
        sucursal_id=sucursal_id,
        activo=True
    )
    usuario.set_password(password)

    db.session.add(usuario)
    db.session.commit()

    return jsonify({
        'mensaje': 'Usuario creado exitosamente',
        'usuario': usuario.to_dict()
    }), 201


# ─────────────────────────────────────────────
# ACTUALIZAR usuario
# ─────────────────────────────────────────────
@usuarios_bp.route('/usuarios/<int:usuario_id>', methods=['PUT'])
@solo_admin_empresa
def actualizar_usuario(usuario_id):
    ctx = get_contexto_actual()

    usuario = Usuario.query.filter_by(
        id=usuario_id,
        empresa_id=ctx['empresa_id']
    ).first_or_404()

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Se requiere JSON en el body'}), 400

    if 'username' in data:
        existing = Usuario.query.filter(
            Usuario.username == data['username'],
            Usuario.id != usuario_id
        ).first()
        if existing:
            return jsonify({'error': 'El username ya está en uso'}), 409
        usuario.username = data['username'].strip()

    if 'rol' in data:
        if data['rol'] == 'super_admin' and ctx['rol'] != 'super_admin':
            return jsonify({'error': 'No tienes permisos para asignar ese rol'}), 403
        usuario.rol = data['rol']

    if 'sucursal_id' in data:
        sucursal = Sucursal.query.filter_by(
            id=data['sucursal_id'],
            empresa_id=ctx['empresa_id'],
            activo=True
        ).first()
        if not sucursal:
            return jsonify({'error': 'Sucursal no válida para esta empresa'}), 400
        usuario.sucursal_id = data['sucursal_id']

    if 'activo' in data:
        usuario.activo = data['activo']

    if 'password' in data and data['password']:
        usuario.set_password(data['password'])

    db.session.commit()

    return jsonify({
        'mensaje': 'Usuario actualizado',
        'usuario': usuario.to_dict()
    }), 200


# ─────────────────────────────────────────────
# DESACTIVAR usuario
# ─────────────────────────────────────────────
@usuarios_bp.route('/usuarios/<int:usuario_id>', methods=['DELETE'])
@solo_admin_empresa
def eliminar_usuario(usuario_id):
    ctx = get_contexto_actual()

    usuario = Usuario.query.filter_by(
        id=usuario_id,
        empresa_id=ctx['empresa_id']
    ).first_or_404()

    # No permitir eliminarse a sí mismo
    if usuario.id == ctx['usuario_id']:
        return jsonify({'error': 'No puedes desactivarte a ti mismo'}), 400

    usuario.activo = False
    db.session.commit()

    return jsonify({'mensaje': f'Usuario {usuario.username} desactivado'}), 200


# ─────────────────────────────────────────────
# TODOS LOS USUARIOS — solo super_admin
# ─────────────────────────────────────────────
@usuarios_bp.route('/todos-los-usuarios', methods=['GET'])
@jwt_required()
def ver_todos_usuarios():
    ctx = get_contexto_actual()

    if ctx['rol'] != 'super_admin':
        return jsonify({'error': 'Acceso denegado'}), 403

    usuarios = Usuario.query.order_by(Usuario.empresa_id, Usuario.username).all()
    return jsonify({
        'usuarios': [u.to_dict() for u in usuarios],
        'total': len(usuarios)
    }), 200
