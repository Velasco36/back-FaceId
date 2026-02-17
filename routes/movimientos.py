
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from models import db, Persona, Movimiento
from utils.helpers import guardar_imagen, paginar_query, parsear_fecha

movimientos_bp = Blueprint('movimientos', __name__)

TIPOS_VALIDOS = {'entrada', 'salida'}


@movimientos_bp.route('/movimiento', methods=['POST'])
def registrar_movimiento():
    cedula = request.form.get('cedula', '').strip()
    tipo = request.form.get('tipo', '').strip().lower()
    observacion = request.form.get('observacion', '').strip() or None

    errores = {}
    if not cedula:
        errores['cedula'] = 'La cedula es requerida'
    if not tipo:
        errores['tipo'] = "El tipo es requerido ('entrada' o 'salida')"
    elif tipo not in TIPOS_VALIDOS:
        errores['tipo'] = f"Tipo invalido: '{tipo}'. Use 'entrada' o 'salida'"

    if errores:
        return jsonify({'error': 'Datos invalidos', 'detalles': errores}), 400

    persona = Persona.query.filter_by(cedula=cedula, activo=True).first()
    if not persona:
        return jsonify({'error': f"No se encontro persona activa con cedula '{cedula}'"}), 404

    nombre_imagen = None
    if 'imagen' in request.files and request.files['imagen'].filename != '':
        archivo = request.files['imagen']
        carpeta = current_app.config['UPLOAD_FOLDER_MOVIMIENTOS']
        try:
            nombre_imagen = guardar_imagen(archivo, carpeta, prefijo=f'mov_{cedula}_{tipo}')
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    movimiento = Movimiento(
        cedula=cedula,
        tipo=tipo,
        imagen_path=nombre_imagen,
        observacion=observacion,
        fecha_hora=datetime.utcnow()
    )

    db.session.add(movimiento)
    db.session.commit()

    return jsonify({
        'registrado': True,
        'mensaje': f'{tipo.capitalize()} registrada para {persona.nombre}',
        'movimiento': movimiento.to_dict()
    }), 201


@movimientos_bp.route('/movimientos', methods=['GET'])
def listar_movimientos():
    cedula = request.args.get('cedula', '').strip() or None
    tipo = request.args.get('tipo', '').strip().lower() or None
    fecha_inicio_str = request.args.get('fecha_inicio', '').strip() or None
    fecha_fin_str = request.args.get('fecha_fin', '').strip() or None
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', current_app.config.get('ITEMS_PER_PAGE', 20)))

    if tipo and tipo not in TIPOS_VALIDOS:
        return jsonify({'error': f"Tipo invalido: '{tipo}'. Use 'entrada' o 'salida'"}), 400

    query = Movimiento.query

    if cedula:
        query = query.filter(Movimiento.cedula == cedula)
    if tipo:
        query = query.filter(Movimiento.tipo == tipo)
    if fecha_inicio_str:
        try:
            fecha_inicio = parsear_fecha(fecha_inicio_str)
            query = query.filter(Movimiento.fecha_hora >= fecha_inicio)
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
            'total': paginacion['total'],
            'paginas': paginacion['paginas'],
            'pagina_actual': paginacion['pagina_actual'],
            'por_pagina': paginacion['por_pagina'],
            'tiene_siguiente': paginacion['tiene_siguiente'],
            'tiene_anterior': paginacion['tiene_anterior'],
        },
        'filtros_aplicados': {
            'cedula': cedula,
            'tipo': tipo,
            'fecha_inicio': fecha_inicio_str,
            'fecha_fin': fecha_fin_str,
        }
    }), 200


@movimientos_bp.route('/movimientos/resumen', methods=['GET'])
def resumen_movimientos():
    hoy = datetime.utcnow().date()
    inicio_dia = datetime.combine(hoy, datetime.min.time())
    fin_dia = datetime.combine(hoy, datetime.max.time())

    entradas_hoy = Movimiento.query.filter(
        Movimiento.tipo == 'entrada',
        Movimiento.fecha_hora.between(inicio_dia, fin_dia)
    ).count()

    salidas_hoy = Movimiento.query.filter(
        Movimiento.tipo == 'salida',
        Movimiento.fecha_hora.between(inicio_dia, fin_dia)
    ).count()

    return jsonify({
        'fecha': hoy.isoformat(),
        'total_entradas_hoy': entradas_hoy,
        'total_salidas_hoy': salidas_hoy,
        'balance_estimado': entradas_hoy - salidas_hoy,
    }), 200

@movimientos_bp.route('/movimientos/persona', methods=['POST'])
def movimientos_por_persona():
    """
    Endpoint POST para obtener todos los movimientos de una persona por su cédula
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Se esperaba un JSON en el body'}), 400

    cedula = data.get('cedula', '').strip()

    # Validar que la cédula sea proporcionada
    if not cedula:
        return jsonify({'error': 'La cédula es requerida'}), 400

    # Buscar la persona
    persona = Persona.query.filter_by(cedula=cedula, activo=True).first()
    if not persona:
        return jsonify({'error': f"No se encontró persona activa con cédula '{cedula}'"}), 404

    # Obtener todos los movimientos de la persona (entradas y salidas)
    movimientos = Movimiento.query.filter_by(cedula=cedula)\
                                 .order_by(Movimiento.fecha_hora.desc())\
                                 .all()

    # Preparar respuesta
    return jsonify({
        'success': True,
        'mensaje': f'Movimientos encontrados para {persona.nombre}',
        'persona': {
            'cedula': persona.cedula,
            'nombre': persona.nombre,
            'imagen_path': persona.imagen_path,
            'activo': persona.activo
        },
        'movimientos': [m.to_dict() for m in movimientos],
        'total_movimientos': len(movimientos),
        'resumen': {
            'entradas': sum(1 for m in movimientos if m.tipo == 'entrada'),
            'salidas': sum(1 for m in movimientos if m.tipo == 'salida')
        }
    }), 200
