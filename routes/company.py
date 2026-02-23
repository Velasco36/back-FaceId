from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from models import db, Empresa, Usuario
import logging

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

empresa_bp = Blueprint('empresa', __name__)

def get_request_data():
    """
    Función auxiliar para obtener datos del request en cualquier formato
    Soporta: JSON, form-data, x-www-form-urlencoded
    """
    try:
        # Si es JSON
        if request.is_json:
            logger.debug("Datos recibidos como JSON")
            return request.get_json()

        # Si es form-data o x-www-form-urlencoded
        logger.debug("Datos recibidos como form-data")
        data = {}

        # Obtener datos del form
        for key in request.form.keys():
            data[key] = request.form.get(key)

        # Obtener archivos si existen
        files = {}
        for key in request.files.keys():
            files[key] = request.files.get(key)

        if files:
            data['_files'] = files

        logger.debug(f"Datos procesados: {data}")
        return data

    except Exception as e:
        logger.error(f"Error procesando request data: {str(e)}")
        return {}

# Crear una nueva empresa (PÚBLICO - no requiere autenticación)
@empresa_bp.route('/empresas', methods=['POST'])
def crear_empresa():
    """
    Endpoint público para crear una nueva empresa
    No requiere autenticación ni token JWT
    """
    try:
        # Obtener datos del request
        data = get_request_data()

        # Log para debug
        logger.info(f"Creando empresa con datos: {data}")
        logger.info(f"Content-Type: {request.content_type}")

        # Validar campos requeridos
        nombre = data.get('nombre')
        rif = data.get('rif')
        password = data.get('password')

        if not nombre or not rif or not password:
            return jsonify({
                'error': 'Nombre, RIF y password son requeridos',
                'received': {
                    'nombre': nombre,
                    'rif': rif,
                    'password': '***' if password else None
                }
            }), 400

        # Validar longitud de password
        if len(password) < 6:
            return jsonify({
                'error': 'La contraseña debe tener al menos 6 caracteres'
            }), 400

        # Verificar si ya existe una empresa con el mismo RIF
        empresa_existente = Empresa.query.filter_by(rif=rif).first()
        if empresa_existente:
            return jsonify({
                'error': 'Ya existe una empresa con este RIF',
                'rif': rif
            }), 400

        # Crear nueva empresa
        nueva_empresa = Empresa(
            nombre=nombre,
            rif=rif
        )
        nueva_empresa.set_password(password)

        # Guardar en base de datos
        db.session.add(nueva_empresa)
        db.session.commit()

        logger.info(f"Empresa creada exitosamente: ID {nueva_empresa.id}")

        # Crear automáticamente un usuario admin para esta empresa
        from models import Usuario
        admin_username = f"admin_{rif.lower().replace('-', '_')}"
        admin_usuario = Usuario(
            username=admin_username,
            rol="admin_empresa",
            empresa_id=nueva_empresa.id,
            activo=True
        )
        admin_usuario.set_password(password)  # Misma contraseña que la empresa

        db.session.add(admin_usuario)
        db.session.commit()

        logger.info(f"Usuario admin creado para empresa: {admin_username}")

        return jsonify({
            'mensaje': 'Empresa creada exitosamente',
            'empresa': nueva_empresa.to_dict(),
            'usuario_admin': {
                'username': admin_username,
                'mensaje': 'Usuario administrador creado automáticamente'
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando empresa: {str(e)}")
        return jsonify({
            'error': 'Error interno del servidor',
            'detalle': str(e)
        }), 500

# Login para empresa (público)
@empresa_bp.route('/empresas/login', methods=['POST'])
def login_empresa():
    """
    Endpoint público para que las empresas inicien sesión
    """
    try:
        data = get_request_data()

        rif = data.get('rif')
        password = data.get('password')

        if not rif or not password:
            return jsonify({
                'error': 'RIF y password son requeridos'
            }), 400

        # Buscar empresa
        empresa = Empresa.query.filter_by(rif=rif).first()

        if not empresa or not empresa.check_password(password):
            return jsonify({
                'error': 'Credenciales inválidas'
            }), 401

        if not empresa.activo:
            return jsonify({
                'error': 'Empresa inactiva'
            }), 401

        from flask_jwt_extended import create_access_token
        from datetime import timedelta

        # Crear token para la empresa
        access_token = create_access_token(
            identity={
                'id': empresa.id,
                'tipo': 'empresa',
                'nombre': empresa.nombre,
                'rif': empresa.rif
            },
            expires_delta=timedelta(hours=1)
        )

        return jsonify({
            'mensaje': 'Login exitoso',
            'access_token': access_token,
            'empresa': empresa.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"Error en login de empresa: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Las siguientes rutas SÍ requieren autenticación

# Obtener todas las empresas (requiere autenticación)
@empresa_bp.route('/empresas', methods=['GET'])
@jwt_required()
def listar_empresas():
    try:
        # Obtener identidad del usuario actual
        current_user = get_jwt_identity()
        logger.info(f"Usuario {current_user.get('username', 'desconocido')} listando empresas")

        # Obtener parámetros de consulta
        pagina = request.args.get('pagina', 1, type=int)
        por_pagina = request.args.get('por_pagina', 10, type=int)
        solo_activas = request.args.get('solo_activas', 'true').lower() == 'true'
        busqueda = request.args.get('busqueda', '')

        # Construir query
        query = Empresa.query

        if solo_activas:
            query = query.filter_by(activo=True)

        if busqueda:
            query = query.filter(
                (Empresa.nombre.ilike(f'%{busqueda}%')) |
                (Empresa.rif.ilike(f'%{busqueda}%'))
            )

        # Paginación
        empresas = query.order_by(Empresa.nombre).paginate(
            page=pagina,
            per_page=por_pagina,
            error_out=False
        )

        return jsonify({
            'empresas': [empresa.to_dict() for empresa in empresas.items],
            'total': empresas.total,
            'pagina': pagina,
            'por_pagina': por_pagina,
            'total_paginas': empresas.pages
        }), 200

    except Exception as e:
        logger.error(f"Error listando empresas: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Obtener una empresa por ID (requiere autenticación)
@empresa_bp.route('/empresas/<int:empresa_id>', methods=['GET'])
@jwt_required()
def obtener_empresa(empresa_id):
    try:
        empresa = Empresa.query.get_or_404(empresa_id)

        # Verificar permisos (admin o usuario de la misma empresa)
        current_user = get_jwt_identity()

        # Si es un usuario normal (no empresa)
        if 'id' in current_user and 'tipo' not in current_user:
            from models import Usuario
            usuario = Usuario.query.get(current_user['id'])
            if not usuario.es_admin() and usuario.empresa_id != empresa.id:
                return jsonify({'error': 'No tiene permisos para ver esta empresa'}), 403

        return jsonify(empresa.to_dict()), 200

    except Exception as e:
        logger.error(f"Error obteniendo empresa {empresa_id}: {str(e)}")
        return jsonify({'error': 'Empresa no encontrada'}), 404

# Actualizar una empresa (requiere autenticación)
@empresa_bp.route('/empresas/<int:empresa_id>', methods=['PUT'])
@jwt_required()
def actualizar_empresa(empresa_id):
    try:
        empresa = Empresa.query.get_or_404(empresa_id)
        data = get_request_data()

        # Verificar permisos
        current_user = get_jwt_identity()

        # Si es empresa autenticada como empresa
        if 'tipo' in current_user and current_user['tipo'] == 'empresa':
            if current_user['id'] != empresa.id:
                return jsonify({'error': 'No tiene permisos para modificar esta empresa'}), 403
        else:
            # Si es usuario normal
            from models import Usuario
            usuario = Usuario.query.get(current_user['id'])
            if not usuario.es_admin() and usuario.empresa_id != empresa.id:
                return jsonify({'error': 'No tiene permisos para modificar esta empresa'}), 403

        logger.info(f"Actualizando empresa {empresa_id} con datos: {data}")

        # Actualizar campos
        if data.get('nombre'):
            empresa.nombre = data['nombre']

        if data.get('rif') and data['rif'] != empresa.rif:
            # Verificar que el nuevo RIF no exista
            if Empresa.query.filter_by(rif=data['rif']).first():
                return jsonify({'error': 'Ya existe una empresa con este RIF'}), 400
            empresa.rif = data['rif']

        if data.get('password'):
            if len(data['password']) >= 6:
                empresa.set_password(data['password'])
            else:
                return jsonify({'error': 'La contraseña debe tener al menos 6 caracteres'}), 400

        if data.get('activo') is not None:
            # Solo admins pueden activar/desactivar empresas
            if 'tipo' in current_user and current_user['tipo'] == 'empresa':
                return jsonify({'error': 'Las empresas no pueden cambiar su propio estado'}), 403

            # Convertir string a boolean si viene de form-data
            if isinstance(data['activo'], str):
                empresa.activo = data['activo'].lower() == 'true'
            else:
                empresa.activo = data['activo']

        empresa.fecha_actualizacion = datetime.utcnow()
        db.session.commit()

        logger.info(f"Empresa {empresa_id} actualizada exitosamente")

        return jsonify({
            'mensaje': 'Empresa actualizada exitosamente',
            'empresa': empresa.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando empresa {empresa_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Eliminar una empresa (soft delete - solo admin)
@empresa_bp.route('/empresas/<int:empresa_id>', methods=['DELETE'])
@jwt_required()
def eliminar_empresa(empresa_id):
    try:
        empresa = Empresa.query.get_or_404(empresa_id)

        # Verificar permisos (solo admin)
        current_user = get_jwt_identity()
        from models import Usuario
        usuario = Usuario.query.get(current_user['id'])

        if not usuario.es_admin():
            return jsonify({'error': 'Se requieren permisos de administrador'}), 403

        logger.info(f"Eliminando empresa {empresa_id}")

        # Verificar si tiene sucursales activas
        sucursales_activas = empresa.sucursales.filter_by(activo=True).count()
        if sucursales_activas > 0:
            return jsonify({
                'error': 'No se puede eliminar la empresa porque tiene sucursales activas',
                'sucursales_activas': sucursales_activas
            }), 400

        # Verificar si tiene usuarios activos
        usuarios_activos = Usuario.query.filter_by(empresa_id=empresa_id, activo=True).count()
        if usuarios_activos > 0:
            return jsonify({
                'error': 'No se puede eliminar la empresa porque tiene usuarios activos',
                'usuarios_activos': usuarios_activos
            }), 400

        # Soft delete (desactivar)
        empresa.activo = False
        empresa.fecha_actualizacion = datetime.utcnow()
        db.session.commit()

        logger.info(f"Empresa {empresa_id} desactivada exitosamente")

        return jsonify({
            'mensaje': 'Empresa desactivada exitosamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error eliminando empresa {empresa_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Obtener estadísticas de una empresa (requiere autenticación)
@empresa_bp.route('/empresas/<int:empresa_id>/estadisticas', methods=['GET'])
@jwt_required()
def estadisticas_empresa(empresa_id):
    try:
        empresa = Empresa.query.get_or_404(empresa_id)

        # Verificar permisos
        current_user = get_jwt_identity()

        # Si es empresa autenticada como empresa
        if 'tipo' in current_user and current_user['tipo'] == 'empresa':
            if current_user['id'] != empresa.id:
                return jsonify({'error': 'No tiene permisos para ver estadísticas de esta empresa'}), 403
        else:
            # Si es usuario normal
            from models import Usuario
            usuario = Usuario.query.get(current_user['id'])
            if not usuario.es_admin() and usuario.empresa_id != empresa.id:
                return jsonify({'error': 'No tiene permisos para ver estadísticas de esta empresa'}), 403

        from models import Sucursal, Usuario, Persona, Movimiento

        # Obtener estadísticas
        stats = {
            'empresa_id': empresa.id,
            'empresa_nombre': empresa.nombre,
            'total_sucursales': empresa.sucursales.count(),
            'sucursales_activas': empresa.sucursales.filter_by(activo=True).count(),
            'total_usuarios': Usuario.query.filter_by(empresa_id=empresa_id).count(),
            'usuarios_activos': Usuario.query.filter_by(empresa_id=empresa_id, activo=True).count(),
            'total_personas': Persona.query.filter_by(empresa_id=empresa_id).count(),
            'personas_activas': Persona.query.filter_by(empresa_id=empresa_id, activo=True).count(),
            'total_movimientos': Movimiento.query.filter_by(empresa_id=empresa_id).count(),
            'movimientos_hoy': Movimiento.query.filter(
                Movimiento.empresa_id == empresa_id,
                Movimiento.fecha_hora >= datetime.utcnow().date()
            ).count()
        }

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de empresa {empresa_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Activar/Desactivar empresa (toggle - solo admin)
@empresa_bp.route('/empresas/<int:empresa_id>/toggle', methods=['POST'])
@jwt_required()
def toggle_empresa(empresa_id):
    try:
        empresa = Empresa.query.get_or_404(empresa_id)

        # Verificar permisos (solo admin)
        current_user = get_jwt_identity()
        from models import Usuario
        usuario = Usuario.query.get(current_user['id'])

        if not usuario.es_admin():
            return jsonify({'error': 'Se requieren permisos de administrador'}), 403

        # Cambiar estado
        empresa.activo = not empresa.activo
        empresa.fecha_actualizacion = datetime.utcnow()
        db.session.commit()

        estado = "activada" if empresa.activo else "desactivada"
        logger.info(f"Empresa {empresa_id} {estado}")

        return jsonify({
            'mensaje': f'Empresa {estado} exitosamente',
            'activo': empresa.activo
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling empresa {empresa_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
