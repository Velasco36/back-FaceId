import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from models import db, Persona, Movimiento, SesionJornada
from routes.auth import get_contexto_actual
from utils.helpers import paginar_query, parsear_fecha

movimientos_bp = Blueprint('movimientos', __name__)

TIPOS_VALIDOS = {'entrada', 'salida'}


# ─────────────────────────────────────────────
# REGISTRAR MOVIMIENTO
# ─────────────────────────────────────────────
@movimientos_bp.route('/movimiento', methods=['POST'])
@jwt_required()
def registrar_movimiento():
    ctx = get_contexto_actual()

    cedula      = request.form.get('cedula', '').strip()
    tipo        = request.form.get('tipo', '').strip().lower()
    observacion = request.form.get('observacion', '').strip() or None
    confianza   = request.form.get('confianza_verificacion', None)

    # Validaciones
    errores = {}
    if not cedula:
        errores['cedula'] = 'La cedula es requerida'
    if not tipo:
        errores['tipo'] = "El tipo es requerido ('entrada' o 'salida')"
    elif tipo not in TIPOS_VALIDOS:
        errores['tipo'] = f"Tipo invalido: '{tipo}'. Use 'entrada' o 'salida'"
    if errores:
        return jsonify({'error': 'Datos invalidos', 'detalles': errores}), 400

    # Buscar persona a nivel de empresa (no de sucursal)
    persona = Persona.query.filter_by(
        cedula=cedula,
        empresa_id=ctx['empresa_id'],
        activo=True
    ).first()
    if not persona:
        return jsonify({'error': f"No se encontro persona activa con cedula '{cedula}' en la empresa"}), 404

    # Crear movimiento con contexto del token
    movimiento = Movimiento(
        cedula=cedula,
        persona_id=persona.id,
        tipo=tipo,
        observacion=observacion,
        fecha_hora=datetime.utcnow(),
        confianza_verificacion=float(confianza) if confianza else None,
        empresa_id=ctx['empresa_id'],
        sucursal_id=ctx['sucursal_id'],   # ← sucursal donde opera el usuario
        usuario_id=ctx['usuario_id'],      # ← quién registró
    )
    db.session.add(movimiento)
    db.session.flush()  # obtenemos movimiento.id antes del commit

    # ── Manejo SesionJornada ──────────────────────────────────────────────
    sesion_jornada = None

    if tipo == 'entrada':
        # Si ya tiene una jornada abierta, cerrarla (caso borde: doble entrada)
        sesion_abierta = SesionJornada.query.filter_by(
            cedula=cedula,
            empresa_id=ctx['empresa_id'],
            abierta=True
        ).first()
        if sesion_abierta:
            sesion_abierta.abierta = False

        # Abrir nueva jornada
        sesion_jornada = SesionJornada(
            cedula=cedula,
            persona_id=persona.id,
            empresa_id=ctx['empresa_id'],
            movimiento_entrada_id=movimiento.id,
            sucursal_entrada_id=ctx['sucursal_id'],
            fecha_entrada=movimiento.fecha_hora,
            abierta=True,
        )
        db.session.add(sesion_jornada)

    elif tipo == 'salida':
        # Buscar jornada abierta en CUALQUIER sucursal de la empresa
        sesion_abierta = SesionJornada.query.filter_by(
            cedula=cedula,
            empresa_id=ctx['empresa_id'],
            abierta=True
        ).order_by(SesionJornada.fecha_entrada.desc()).first()

        if not sesion_abierta:
            db.session.rollback()
            return jsonify({'error': 'No hay entrada activa para esta persona'}), 400

        # Cerrar jornada — puede ser en sucursal distinta a la entrada
        sesion_abierta.movimiento_salida_id = movimiento.id
        sesion_abierta.sucursal_salida_id   = ctx['sucursal_id']
        sesion_abierta.fecha_salida         = movimiento.fecha_hora
        sesion_abierta.abierta              = False
        sesion_jornada = sesion_abierta

    db.session.commit()

    return jsonify({
        'registrado': True,
        'mensaje': f'{tipo.capitalize()} registrada para {persona.nombre}',
        'movimiento': movimiento.to_dict(),
        'jornada': sesion_jornada.to_dict() if sesion_jornada else None
    }), 201


# ─────────────────────────────────────────────
# LISTAR MOVIMIENTOS — filtrados por empresa del token
# ─────────────────────────────────────────────
@movimientos_bp.route('/movimientos', methods=['GET'])
@jwt_required()
def listar_movimientos():
    ctx = get_contexto_actual()

    cedula           = request.args.get('cedula', '').strip() or None
    tipo             = request.args.get('tipo', '').strip().lower() or None
    sucursal_id      = request.args.get('sucursal_id', None)  # opcional: filtrar por sucursal
    fecha_inicio_str = request.args.get('fecha_inicio', '').strip() or None
    fecha_fin_str    = request.args.get('fecha_fin', '').strip() or None
    page             = int(request.args.get('page', 1))
    per_page         = int(request.args.get('per_page', current_app.config.get('ITEMS_PER_PAGE', 20)))

    if tipo and tipo not in TIPOS_VALIDOS:
        return jsonify({'error': f"Tipo invalido: '{tipo}'. Use 'entrada' o 'salida'"}), 400

    # Siempre filtrado por empresa del token
    query = Movimiento.query.filter_by(empresa_id=ctx['empresa_id'])

    # Admin ve toda la empresa, user solo ve su sucursal
    if ctx['rol'] != 'admin_empresa':
        query = query.filter_by(sucursal_id=ctx['sucursal_id'])
    elif sucursal_id:
        query = query.filter_by(sucursal_id=sucursal_id)

    if cedula:
        query = query.filter(Movimiento.cedula == cedula)
    if tipo:
        query = query.filter(Movimiento.tipo == tipo)
    if fecha_inicio_str:
        try:
            query = query.filter(Movimiento.fecha_hora >= parsear_fecha(fecha_inicio_str))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
    if fecha_fin_str:
        try:
            fecha_fin = parsear_fecha(fecha_fin_str)
            if fecha_fin.hour == 0 and fecha_fin.minute == 0:
                fecha_fin = fecha_fin.replace(hour=23, minute=59, second=59)
            query = query.filter(Movimiento.fecha_hora <= fecha_fin)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    query = query.order_by(Movimiento.fecha_hora.desc())

    try:
        paginacion = paginar_query(query, page, per_page)
    except Exception as e:
        return jsonify({'error': f'Error en paginacion: {str(e)}'}), 400

    return jsonify({
        'movimientos': [m.to_dict() for m in paginacion['items']],
        'paginacion': {
            'total':          paginacion['total'],
            'paginas':        paginacion['paginas'],
            'pagina_actual':  paginacion['pagina_actual'],
            'por_pagina':     paginacion['por_pagina'],
            'tiene_siguiente':paginacion['tiene_siguiente'],
            'tiene_anterior': paginacion['tiene_anterior'],
        },
        'filtros_aplicados': {
            'cedula':       cedula,
            'tipo':         tipo,
            'sucursal_id':  sucursal_id,
            'fecha_inicio': fecha_inicio_str,
            'fecha_fin':    fecha_fin_str,
        }
    }), 200


# ─────────────────────────────────────────────
# RESUMEN — del día, por empresa/sucursal
# ─────────────────────────────────────────────
@movimientos_bp.route('/movimientos/resumen', methods=['GET'])
@jwt_required()
def resumen_movimientos():
    ctx = get_contexto_actual()

    hoy       = datetime.utcnow().date()
    inicio_dia = datetime.combine(hoy, datetime.min.time())
    fin_dia    = datetime.combine(hoy, datetime.max.time())

    # Base siempre filtrada por empresa
    base = Movimiento.query.filter(
        Movimiento.empresa_id == ctx['empresa_id'],
        Movimiento.fecha_hora.between(inicio_dia, fin_dia)
    )

    # Admin ve toda la empresa, user solo su sucursal
    if ctx['rol'] != 'admin_empresa':
        base = base.filter(Movimiento.sucursal_id == ctx['sucursal_id'])

    entradas_hoy = base.filter(Movimiento.tipo == 'entrada').count()
    salidas_hoy  = base.filter(Movimiento.tipo == 'salida').count()

    # Jornadas actualmente abiertas (personas dentro)
    jornadas_abiertas = SesionJornada.query.filter_by(
        empresa_id=ctx['empresa_id'],
        abierta=True
    ).count()

    return jsonify({
        'fecha':              hoy.isoformat(),
        'empresa_id':         ctx['empresa_id'],
        'sucursal_id':        ctx['sucursal_id'] if ctx['rol'] != 'admin_empresa' else 'todas',
        'total_entradas_hoy': entradas_hoy,
        'total_salidas_hoy':  salidas_hoy,
        'personas_adentro':   jornadas_abiertas,  # ← nuevo: conteo real
        'balance_estimado':   entradas_hoy - salidas_hoy,
    }), 200


# ─────────────────────────────────────────────
# MOVIMIENTOS POR PERSONA
# ─────────────────────────────────────────────
@movimientos_bp.route('/movimientos/persona', methods=['POST'])
@jwt_required()
def movimientos_por_persona():
    ctx = get_contexto_actual()

    cedula = request.form.get('cedula', '').strip()
    nombre = request.form.get('nombre', '').strip()

    if not cedula and not nombre:
        return jsonify({'error': 'Se requiere cedula o nombre'}), 400

    # Buscar siempre dentro de la empresa del token
    base_query = Persona.query.filter_by(
        empresa_id=ctx['empresa_id'],
        activo=True
    )

    if cedula:
        persona = base_query.filter_by(cedula=cedula).first()
        if not persona:
            return jsonify({'error': f"No se encontró persona con cédula '{cedula}' en la empresa"}), 404
    else:
        personas = base_query.filter(Persona.nombre.ilike(f'%{nombre}%')).all()
        if not personas:
            return jsonify({'error': f"No se encontraron personas con nombre '{nombre}'"}), 404
        if len(personas) > 1:
            return jsonify({
                'multiple_results': True,
                'mensaje': f'Se encontraron {len(personas)} personas',
                'personas': [{'cedula': p.cedula, 'nombre': p.nombre} for p in personas]
            }), 300
        persona = personas[0]

    movimientos = Movimiento.query.filter_by(
        cedula=persona.cedula,
        empresa_id=ctx['empresa_id']
    ).order_by(Movimiento.fecha_hora.desc()).all()

    return jsonify({
        'persona': persona.to_dict(),
        'movimientos': [m.to_dict() for m in movimientos],
        'total_movimientos': len(movimientos),
        'resumen': {
            'entradas': sum(1 for m in movimientos if m.tipo == 'entrada'),
            'salidas':  sum(1 for m in movimientos if m.tipo == 'salida'),
        }
    }), 200
