import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from models import db, Usuario, TokenBlacklist

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
ROLES_VALIDOS = {'user', 'admin'}

# Configuración JWT
SECRET_KEY = '959266dcefbf456d6f0e2f427500e693577a22dc4f0b7a0ed372bcb673a73431'  # En producción, usa variable de entorno
ALGORITHM = 'HS256'
TOKEN_EXPIRATION = 24  # horas

def obtener_datos_request():
    """Función helper para obtener datos de JSON o form-data"""
    if request.is_json:
        return request.get_json()
    else:
        return request.form.to_dict()

def generar_token(usuario_id, username, rol):
    """Genera un token JWT para el usuario"""
    payload = {
        'usuario_id': usuario_id,
        'username': username,
        'rol': rol,
        'exp': datetime.utcnow() + timedelta(hours=TOKEN_EXPIRATION),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def token_requerido(f):
    """Decorador para proteger rutas que requieren autenticación"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Buscar token en headers
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]

        if not token:
            return jsonify({'error': 'Token de autenticación requerido'}), 401

        try:
            # Verificar si el token está en blacklist
            token_bloqueado = TokenBlacklist.query.filter_by(token=token).first()
            if token_bloqueado:
                return jsonify({'error': 'Token inválido o expirado'}), 401

            # Decodificar token
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            request.usuario_id = payload['usuario_id']
            request.username = payload['username']
            request.rol = payload['rol']

        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido'}), 401

        return f(*args, **kwargs)
    return decorated

def admin_requerido(f):
    """Decorador para rutas que requieren rol de admin"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.rol != 'admin':
            return jsonify({'error': 'Se requieren permisos de administrador'}), 403
        return f(*args, **kwargs)
    return decorated

@auth_bp.route('/registro', methods=['POST'])
def registro():
    data = obtener_datos_request()
    if not data:
        return jsonify({'error': 'Se requieren datos'}), 400

    username = data.get('username', '').strip().upper()  # 🔥 Convertir a mayúsculas
    password = data.get('password', '').strip()
    rol = data.get('rol', 'user').strip().lower()

    # Validaciones
    errores = {}
    if not username:
        errores['username'] = 'El username es requerido'
    elif len(username) < 3:
        errores['username'] = 'El username debe tener al menos 3 caracteres'

    if not password:
        errores['password'] = 'La contraseña es requerida'
    elif len(password) < 6:
        errores['password'] = 'La contraseña debe tener al menos 6 caracteres'

    if rol not in ROLES_VALIDOS:
        errores['rol'] = f"El rol debe ser 'user' o 'admin'"

    if errores:
        return jsonify({'error': 'Datos inválidos', 'detalles': errores}), 400

    # Verificar que el username no exista (búsqueda case-insensitive)
    if Usuario.query.filter(Usuario.username.ilike(username)).first():  # 🔥 Buscar sin importar mayúsculas/minúsculas
        return jsonify({'error': f"El username '{username}' ya está en uso"}), 409

    usuario = Usuario(username=username, rol=rol)
    usuario.set_password(password)

    db.session.add(usuario)
    db.session.commit()

    return jsonify({
        'success': True,
        'mensaje': f"Usuario '{username}' registrado exitosamente",
        'usuario': usuario.to_dict()
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = obtener_datos_request()
    if not data:
        return jsonify({'error': 'Se requieren datos'}), 400

    username = data.get('username', '').strip().upper()  
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': 'Username y contraseña son requeridos'}), 400

    # Buscar usuario con case-insensitive
    usuario = Usuario.query.filter(Usuario.username.ilike(username), Usuario.activo == True).first()

    if not usuario or not usuario.check_password(password):
        return jsonify({'error': 'Credenciales inválidas'}), 401

    # Generar token
    token = generar_token(usuario.id, usuario.username, usuario.rol)

    return jsonify({
        'success': True,
        'mensaje': f'Bienvenido, {usuario.username}',
        'token': token,
        'usuario': usuario.to_dict()
    }), 200
    data = obtener_datos_request()
    if not data:
        return jsonify({'error': 'Se requieren datos'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': 'Username y contraseña son requeridos'}), 400

    usuario = Usuario.query.filter_by(username=username, activo=True).first()

    if not usuario or not usuario.check_password(password):
        return jsonify({'error': 'Credenciales inválidas'}), 401

    # Generar token
    token = generar_token(usuario.id, usuario.username, usuario.rol)

    return jsonify({
        'success': True,
        'mensaje': f'Bienvenido, {usuario.username}',
        'token': token,
        'usuario': usuario.to_dict()
    }), 200

@auth_bp.route('/logout', methods=['POST'])
@token_requerido
def logout():
    """
    Cierra la sesión del usuario agregando su token a la blacklist
    """
    token = request.headers['Authorization'].split(' ')[1]

    # Agregar token a blacklist
    token_bloqueado = TokenBlacklist(token=token)
    db.session.add(token_bloqueado)
    db.session.commit()

    return jsonify({
        'success': True,
        'mensaje': 'Sesión cerrada exitosamente'
    }), 200

@auth_bp.route('/perfil', methods=['GET'])
@token_requerido
def perfil():
    """Obtiene información del usuario autenticado"""
    usuario = Usuario.query.get(request.usuario_id)
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    return jsonify({
        'success': True,
        'usuario': usuario.to_dict()
    }), 200

@auth_bp.route('/usuarios', methods=['GET'])
@token_requerido
@admin_requerido
def listar_usuarios():
    """Lista todos los usuarios (solo admin)"""
    usuarios = Usuario.query.filter_by(activo=True).all()
    return jsonify({
        'usuarios': [u.to_dict() for u in usuarios],
        'total': len(usuarios)
    }), 200

@auth_bp.route('/usuarios/<int:id>', methods=['DELETE'])
@token_requerido
@admin_requerido
def desactivar_usuario(id):
    """Desactiva un usuario (solo admin)"""
    usuario = Usuario.query.get(id)
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    usuario.activo = False
    db.session.commit()

    return jsonify({
        'success': True,
        'mensaje': f"Usuario '{usuario.username}' desactivado"
    }), 200

@auth_bp.route('/usuarios/<int:id>/rol', methods=['PATCH'])
@token_requerido
@admin_requerido
def cambiar_rol(id):
    """Cambia el rol de un usuario (solo admin)"""
    usuario = Usuario.query.get(id)
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    data = obtener_datos_request()
    nuevo_rol = data.get('rol', '').strip().lower()

    if nuevo_rol not in ROLES_VALIDOS:
        return jsonify({'error': "El rol debe ser 'user' o 'admin'"}), 400

    usuario.rol = nuevo_rol
    db.session.commit()

    return jsonify({
        'success': True,
        'mensaje': f"Rol actualizado a '{nuevo_rol}'",
        'usuario': usuario.to_dict()
    }), 200

@auth_bp.route('/verificar-token', methods=['GET'])
@token_requerido
def verificar_token():
    """Verifica si el token es válido"""
    return jsonify({
        'success': True,
        'mensaje': 'Token válido',
        'usuario': {
            'id': request.usuario_id,
            'username': request.username,
            'rol': request.rol
        }
    }), 200
