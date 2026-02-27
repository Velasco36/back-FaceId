from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Empresa, Usuario, Sucursal
from functools import wraps
from routes.auth import get_contexto_actual

empresa_bp = Blueprint('empresa', __name__)


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
# REGISTRAR empresa — público, no requiere token
# ─────────────────────────────────────────────
@empresa_bp.route('/empresas', methods=['POST'])
def registrar_empresa():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Se requiere JSON en el body'}), 400

    campos = ['nombre', 'rif', 'password']
    if not all(data.get(c) for c in campos):
        return jsonify({'error': f'Campos requeridos: {", ".join(campos)}'}), 400

    if Empresa.query.filter_by(rif=data['rif']).first():
        return jsonify({'error': 'Ya existe una empresa con ese RIF'}), 409

    empresa = Empresa(nombre=data['nombre'], rif=data['rif'])
    empresa.set_password(data['password'])
    db.session.add(empresa)
    db.session.flush()

    # Sede Principal automática
    sede = Sucursal(
        nombre='Sede Principal',
        empresa_id=empresa.id,
        es_matriz=True
    )
    db.session.add(sede)
    db.session.flush()

    # Usuario admin_empresa automático
    admin = Usuario(
        username=data.get('admin_username', data['rif']),
        rol='admin_empresa',
        empresa_id=empresa.id,
        sucursal_id=sede.id
    )
    admin.set_password(data['password'])
    db.session.add(admin)
    db.session.commit()

    return jsonify({
        'mensaje': 'Empresa registrada exitosamente',
        'empresa': empresa.to_dict(),
        'sede_principal': sede.to_dict(),
        'admin_username': admin.username,
        'credenciales': {
            'username': admin.username,
            'password': '(la que ingresaste)',
            'nota': 'Guarda estas credenciales, no se volverán a mostrar'
        }
    }), 201


# ─────────────────────────────────────────────
# OBTENER empresa
# ─────────────────────────────────────────────
@empresa_bp.route('/empresas/<int:empresa_id>', methods=['GET'])
@solo_admin_empresa
def obtener_empresa(empresa_id):
    ctx = get_contexto_actual()

    # Solo puede ver su propia empresa
    if ctx['empresa_id'] != empresa_id and ctx['rol'] != 'super_admin':
        return jsonify({'error': 'No tienes acceso a esta empresa'}), 403

    empresa = Empresa.query.get_or_404(empresa_id)
    return jsonify({'empresa': empresa.to_dict()}), 200


# ─────────────────────────────────────────────
# ACTUALIZAR empresa
# ─────────────────────────────────────────────
@empresa_bp.route('/empresas/<int:empresa_id>', methods=['PUT'])
@solo_admin_empresa
def actualizar_empresa(empresa_id):
    ctx = get_contexto_actual()

    if ctx['empresa_id'] != empresa_id and ctx['rol'] != 'super_admin':
        return jsonify({'error': 'No tienes acceso a esta empresa'}), 403

    empresa = Empresa.query.get_or_404(empresa_id)
    data    = request.get_json()

    if not data:
        return jsonify({'error': 'Se requiere JSON en el body'}), 400

    if 'nombre' in data and data['nombre'].strip():
        empresa.nombre = data['nombre'].strip()

    if 'password' in data and data['password']:
        empresa.set_password(data['password'])

    db.session.commit()

    return jsonify({
        'mensaje': 'Empresa actualizada',
        'empresa': empresa.to_dict()
    }), 200


# ─────────────────────────────────────────────
# LISTAR empresas — solo super_admin
# ─────────────────────────────────────────────
@empresa_bp.route('/empresas', methods=['GET'])
@jwt_required()
def listar_empresas():
    ctx = get_contexto_actual()

    if ctx['rol'] != 'super_admin':
        return jsonify({'error': 'Acceso denegado'}), 403

    page     = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search   = request.args.get('search', '', type=str)

    query = Empresa.query

    if search:
        query = query.filter(
            db.or_(
                Empresa.nombre.ilike(f'%{search}%'),
                Empresa.rif.ilike(f'%{search}%')
            )
        )

    pagination = query.order_by(Empresa.nombre.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'empresas': [e.to_dict() for e in pagination.items],
        'paginacion': {
            'total':           pagination.total,
            'paginas':         pagination.pages,
            'pagina_actual':   page,
            'por_pagina':      per_page,
            'tiene_siguiente': pagination.has_next,
            'tiene_anterior':  pagination.has_prev,
        }
    }), 200


# ─────────────────────────────────────────────
# SUCURSALES POR RIF — público para el login
# (Flutter necesita esto antes de tener token)
# ─────────────────────────────────────────────
@empresa_bp.route('/empresas/rif/<string:rif>/sucursales', methods=['GET'])
def sucursales_por_rif(rif):
    """
    Endpoint público usado en el flujo de login:
    Flutter busca la empresa por RIF y muestra sus sucursales
    antes de que el usuario se autentique.
    """
    empresa = Empresa.query.filter_by(rif=rif, activo=True).first()
    if not empresa:
        return jsonify({'error': f'No se encontró ninguna empresa con RIF: {rif}'}), 404

    sucursales = Sucursal.query.filter_by(
        empresa_id=empresa.id,
        activo=True
    ).order_by(Sucursal.es_matriz.desc(), Sucursal.nombre.asc()).all()

    return jsonify({
        'empresa_id': empresa.id,
        'empresa':    empresa.nombre,
        'rif':        empresa.rif,
        'total_sucursales': len(sucursales),
        'sucursales': [s.to_dict() for s in sucursales]
    }), 200
