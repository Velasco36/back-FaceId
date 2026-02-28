from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity, create_access_token
from functools import wraps
from models import db, Usuario, Sucursal, TokenBlacklist

auth_bp = Blueprint('auth', __name__)


# ─────────────────────────────────────────────
# HELPER — contexto del token
# ─────────────────────────────────────────────
def get_contexto_actual():
    claims = get_jwt()
    return {
        'usuario_id': int(get_jwt_identity()),
        'empresa_id': claims['empresa_id'],
        'sucursal_id': claims['sucursal_id'],
        'rol': claims['rol'],
        'username': claims['username'],
    }


# ─────────────────────────────────────────────
# DECORATORS
# ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    @jwt_required()
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)
    return wrapper


def rol_requerido(*roles):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def wrapper(*args, **kwargs):
            if get_jwt().get('rol') not in roles:
                return jsonify({'error': 'No tienes permisos para esta acción'}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# LOGIN — un solo paso con empresa y sucursal
# ─────────────────────────────────────────────
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Se requiere JSON en el body'}), 400

    username    = data.get('username', '').strip()
    password    = data.get('password', '')
    empresa_id  = data.get('empresa_id')
    sucursal_id = data.get('sucursal_id')

    if not all([username, password, empresa_id, sucursal_id]):
        return jsonify({'error': 'username, password, empresa_id y sucursal_id son requeridos'}), 400

    usuario = Usuario.query.filter_by(
        username=username,
        empresa_id=empresa_id,
        activo=True
    ).first()

    if not usuario or not usuario.check_password(password):
        return jsonify({'error': 'Credenciales inválidas'}), 401

    sucursal = Sucursal.query.filter_by(
        id=sucursal_id,
        empresa_id=empresa_id,
        activo=True
    ).first()

    if not sucursal:
        return jsonify({'error': 'Sucursal no válida para esta empresa'}), 403

    access_token = create_access_token(
        identity=str(usuario.id),
        additional_claims={
            'empresa_id': usuario.empresa_id,
            'sucursal_id': sucursal_id,
            'rol': usuario.rol,
            'username': usuario.username,
        }
    )

    return jsonify({
        'access_token': access_token,
        'usuario': usuario.to_dict(),
        'sucursal': sucursal.to_dict()
    }), 200


# ─────────────────────────────────────────────
# LOGOUT — invalida el token
# ─────────────────────────────────────────────
@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    jti = get_jwt()['jti']
    db.session.add(TokenBlacklist(jti=jti))
    db.session.commit()
    return jsonify({'mensaje': 'Sesión cerrada correctamente'}), 200


# ─────────────────────────────────────────────
# ME — info del usuario activo
# ─────────────────────────────────────────────
@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    ctx = get_contexto_actual()
    usuario = Usuario.query.get(ctx['usuario_id'])
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    sucursal = Sucursal.query.get(ctx['sucursal_id'])
    return jsonify({
        'usuario': usuario.to_dict(),
        'sucursal_activa': sucursal.to_dict() if sucursal else None,
    }), 200


# ─────────────────────────────────────────────
# CAMBIAR SUCURSAL — nuevo token, misma sesión
# ─────────────────────────────────────────────
@auth_bp.route('/cambiar-sucursal', methods=['POST'])
@jwt_required()
def cambiar_sucursal():
    ctx = get_contexto_actual()
    data = request.get_json()
    nueva_sucursal_id = data.get('sucursal_id')

    if not nueva_sucursal_id:
        return jsonify({'error': 'sucursal_id es requerido'}), 400

    sucursal = Sucursal.query.filter_by(
        id=nueva_sucursal_id,
        empresa_id=ctx['empresa_id'],
        activo=True
    ).first()
    if not sucursal:
        return jsonify({'error': 'Sucursal no válida para esta empresa'}), 403

    db.session.add(TokenBlacklist(jti=get_jwt()['jti']))
    db.session.commit()

    nuevo_token = create_access_token(
        identity=str(ctx['usuario_id']),
        additional_claims={
            'empresa_id': ctx['empresa_id'],
            'sucursal_id': nueva_sucursal_id,
            'rol': ctx['rol'],
            'username': ctx['username'],
        }
    )

    return jsonify({
        'access_token': nuevo_token,
        'sucursal_activa': sucursal.to_dict()
    }), 200
