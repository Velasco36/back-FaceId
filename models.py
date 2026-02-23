from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

class TokenBlacklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(500), unique=True, nullable=False)
    blacklisted_on = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Token {self.id}>'


class Empresa(db.Model):
    __tablename__ = 'empresas'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(100), nullable=False, index=True)
    rif = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    sucursales = db.relationship('Sucursal', backref='empresa', lazy='dynamic', cascade='all, delete-orphan')
    usuarios = db.relationship('Usuario', backref='empresa', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'rif': self.rif,
            'activo': self.activo,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'total_sucursales': self.sucursales.count(),
            'total_usuarios': self.usuarios.count()
        }

    def __repr__(self):
        return f'<Empresa {self.nombre} - {self.rif}>'


class Sucursal(db.Model):
    __tablename__ = 'sucursales'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(100), nullable=False)
    direccion = db.Column(db.String(255), nullable=True)
    telefono = db.Column(db.String(20), nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    # Foreign Keys
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)

    # Campos de auditoría
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    usuarios = db.relationship('Usuario', backref='sucursal', lazy='dynamic')
    personas = db.relationship('Persona', backref='sucursal', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'direccion': self.direccion,
            'telefono': self.telefono,
            'activo': self.activo,
            'empresa_id': self.empresa_id,
            'empresa_nombre': self.empresa.nombre if self.empresa else None,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'total_usuarios': self.usuarios.count(),
            'total_personas': self.personas.count()
        }

    def __repr__(self):
        return f'<Sucursal {self.nombre} - Empresa: {self.empresa_id}>'


class Usuario(db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(10), nullable=False, default='user')  # admin, user, etc.
    activo = db.Column(db.Boolean, default=True, nullable=False)

    # Foreign Keys
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True, index=True)

    # Campos de auditoría
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def es_admin(self):
        return self.rol == 'admin'

    def es_admin_empresa(self):
        return self.rol == 'admin_empresa'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'rol': self.rol,
            'es_admin': self.es_admin(),
            'es_admin_empresa': self.es_admin_empresa(),
            'activo': self.activo,
            'empresa_id': self.empresa_id,
            'empresa_nombre': self.empresa.nombre if self.empresa else None,
            'sucursal_id': self.sucursal_id,
            'sucursal_nombre': self.sucursal.nombre if self.sucursal else None,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
        }

    def __repr__(self):
        return f'<Usuario {self.username} - {self.rol} - Empresa: {self.empresa_id}>'


class Persona(db.Model):
    __tablename__ = 'personas'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cedula = db.Column(db.String(20), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(100), nullable=False)
    imagen_path = db.Column(db.String(255), nullable=True)
    encoding_facial = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    # Foreign Keys
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True, index=True)

    # Campos de auditoría
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    movimientos = db.relationship('Movimiento', backref='persona', lazy='dynamic')

    def set_encoding(self, encoding_array):
        if encoding_array is not None:
            self.encoding_facial = json.dumps(encoding_array.tolist())

    def get_encoding(self):
        if self.encoding_facial:
            return json.loads(self.encoding_facial)
        return None

    def to_dict(self, include_encoding=False):
        from flask import request
        base_url = request.host_url.rstrip('/')

        imagen_url = None
        if self.imagen_path:
            imagen_url = f"{base_url}/uploads/registros/{self.imagen_path}"

        data = {
            'id': self.id,
            'cedula': self.cedula,
            'nombre': self.nombre,
            'imagen_path': self.imagen_path,
            'imagen_url': imagen_url,
            'activo': self.activo,
            'tiene_encoding': self.encoding_facial is not None,
            'empresa_id': self.empresa_id,
            'empresa_nombre': self.empresa.nombre if hasattr(self, 'empresa') and self.empresa else None,
            'sucursal_id': self.sucursal_id,
            'sucursal_nombre': self.sucursal.nombre if hasattr(self, 'sucursal') and self.sucursal else None,
            'fecha_registro': self.fecha_registro.isoformat() if self.fecha_registro else None,
            'fecha_actualizacion': self.fecha_actualizacion.isoformat() if self.fecha_actualizacion else None,
        }
        if include_encoding:
            data['encoding'] = self.get_encoding()
        return data

    def __repr__(self):
        return f'<Persona {self.cedula} - {self.nombre} - Empresa: {self.empresa_id}>'


class Movimiento(db.Model):
    __tablename__ = 'movimientos'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cedula = db.Column(db.String(20), db.ForeignKey('personas.cedula'), nullable=False, index=True)
    tipo = db.Column(db.String(10), nullable=False)
    observacion = db.Column(db.String(255), nullable=True)
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    confianza_verificacion = db.Column(db.Float, nullable=True)

    # Foreign Keys adicionales para mejor filtrado
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'cedula': self.cedula,
            'nombre_persona': self.persona.nombre if self.persona else None,
            'tipo': self.tipo,
            'observacion': self.observacion,
            'fecha_hora': self.fecha_hora.isoformat(),
            'confianza_verificacion': self.confianza_verificacion,
            'empresa_id': self.empresa_id,
            'empresa_nombre': self.persona.empresa.nombre if self.persona and hasattr(self.persona, 'empresa') else None,
            'sucursal_id': self.sucursal_id,
            'sucursal_nombre': self.persona.sucursal.nombre if self.persona and hasattr(self.persona, 'sucursal') and self.persona.sucursal else None,
        }

    def __repr__(self):
        return f'<Movimiento {self.tipo} - {self.cedula} - {self.fecha_hora}>'
