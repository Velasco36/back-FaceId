
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app


def archivo_permitido(nombre_archivo: str) -> bool:
    if '.' not in nombre_archivo:
        return False
    extension = nombre_archivo.rsplit('.', 1)[1].lower()
    return extension in current_app.config['ALLOWED_EXTENSIONS']


def guardar_imagen(archivo, carpeta: str, prefijo: str = '') -> str:
    if not archivo_permitido(archivo.filename):
        extensiones = ', '.join(current_app.config['ALLOWED_EXTENSIONS'])
        raise ValueError(f"Formato no permitido. Use: {extensiones}")

    extension = archivo.filename.rsplit('.', 1)[1].lower()
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    nombre_unico = f"{prefijo}_{timestamp}_{uuid.uuid4().hex[:8]}.{extension}"
    nombre_seguro = secure_filename(nombre_unico)

    ruta_completa = os.path.join(carpeta, nombre_seguro)
    archivo.save(ruta_completa)

    return nombre_seguro


def paginar_query(query, page: int, per_page: int):
    page = max(1, page)
    per_page = min(100, max(1, per_page))

    paginacion = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'items': paginacion.items,
        'total': paginacion.total,
        'paginas': paginacion.pages,
        'pagina_actual': paginacion.page,
        'por_pagina': paginacion.per_page,
        'tiene_siguiente': paginacion.has_next,
        'tiene_anterior': paginacion.has_prev,
    }


def parsear_fecha(fecha_str: str) -> datetime:
    formatos = [
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%d/%m/%Y',
    ]
    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato de fecha no reconocido: '{fecha_str}'. Use YYYY-MM-DD")

