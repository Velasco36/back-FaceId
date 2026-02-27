from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()


# ─────────────────────────────────────────────
# TOKEN BLACKLIST
# ─────────────────────────────────────────────
class TokenBlacklist(db.Model):
    __tablename__ = 'token_blacklist'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)
    blacklisted_on = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Token {self.jti}>'


# ─────────────────────────────────────────────
# EMPRESA
# ─────────────────────────────────────────────
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
    sucursales = db.relationship('Sucursal', backref='empresa', lazy='dynamic',
                                 cascade='all, delete-orphan')
    usuarios = db.relationship('Usuario', backref='empresa', lazy='dynamic',
                               cascade='all, delete-orphan')
    personas = db.relationship('Persona', backref='empresa', lazy='dynamic',
                               cascade='all, delete-orphan')
    movimientos = db.relationship('Movimiento', backref='empresa', lazy='dynamic',
                                  cascade='all, delete-orphan')

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
            'total_usuarios': self.usuarios.count(),

        }

    def __repr__(self):
        return f'<Empresa {self.nombre} - {self.rif}>'


# ─────────────────────────────────────────────
# SUCURSAL
# ─────────────────────────────────────────────
class Sucursal(db.Model):
    __tablename__ = 'sucursales'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(100), nullable=False)
    direccion = db.Column(db.String(255), nullable=True)
    telefono = db.Column(db.String(20), nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    es_matriz = db.Column(db.Boolean, default=False, nullable=False)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    usuarios = db.relationship('Usuario', backref='sucursal', lazy='dynamic')
    movimientos = db.relationship('Movimiento', backref='sucursal', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'direccion': self.direccion,
            'telefono': self.telefono,
            'activo': self.activo,
            'es_matriz': self.es_matriz,
            'empresa_id': self.empresa_id,
            'empresa_nombre': self.empresa.nombre if self.empresa else None,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'total_usuarios': self.usuarios.count(),
            # total_personas eliminado — personas ahora pertenecen a la empresa, no a la sucursal
        }

    def __repr__(self):
        return f'<Sucursal {self.nombre} - Empresa: {self.empresa_id}>'


# ─────────────────────────────────────────────
# USUARIO
# ─────────────────────────────────────────────
class Usuario(db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    # Roles: admin_empresa | user
    rol = db.Column(db.String(20), nullable=False, default='user')
    activo = db.Column(db.Boolean, default=True, nullable=False)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    # sucursal_id es la sucursal BASE del usuario, pero puede operar en cualquiera via JWT
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False, index=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow, nullable=False)

    # Relaciones
    movimientos_registrados = db.relationship('Movimiento', backref='usuario_registro',
                                               lazy='dynamic', foreign_keys='Movimiento.usuario_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def es_admin_empresa(self):
        return self.rol == 'admin_empresa'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'rol': self.rol,
            'activo': self.activo,
            'empresa_id': self.empresa_id,
            'empresa_nombre': self.empresa.nombre if self.empresa else None,
            'sucursal_id': self.sucursal_id,
            'sucursal_nombre': self.sucursal.nombre if self.sucursal else None,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
        }

    def __repr__(self):
        return f'<Usuario {self.username} - {self.rol}>'


# ─────────────────────────────────────────────
# PERSONA
# ─────────────────────────────────────────────
class Persona(db.Model):
    __tablename__ = 'personas'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cedula = db.Column(db.String(20), nullable=False, index=True)
    nombre = db.Column(db.String(100), nullable=False)
    imagen_path = db.Column(db.String(255), nullable=True)
    encoding_facial = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    # Sucursal donde fue registrada originalmente — solo referencial
    sucursal_registro_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'),
                                     nullable=True, index=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow, nullable=False)

    # ✅ Cédula única por empresa
    __table_args__ = (
        db.UniqueConstraint('cedula', 'empresa_id', name='uq_cedula_empresa'),
    )

    # Relaciones
    movimientos = db.relationship('Movimiento', backref='persona', lazy='dynamic',
                                  foreign_keys='Movimiento.persona_id')
    sucursal_registro = db.relationship('Sucursal', foreign_keys=[sucursal_registro_id])

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
        imagen_url = f"{base_url}/uploads/registros/{self.imagen_path}" if self.imagen_path else None

        data = {
            'id': self.id,
            'cedula': self.cedula,
            'nombre': self.nombre,
            'imagen_url': imagen_url,
            'activo': self.activo,
            'tiene_encoding': self.encoding_facial is not None,
            'empresa_id': self.empresa_id,
            'empresa_nombre': self.empresa.nombre if self.empresa else None,
            # Referencial — dónde fue registrada, no dónde opera
            'sucursal_registro_id': self.sucursal_registro_id,
            'sucursal_registro_nombre': self.sucursal_registro.nombre if self.sucursal_registro else None,
            'fecha_registro': self.fecha_registro.isoformat() if self.fecha_registro else None,
        }
        if include_encoding:
            data['encoding'] = self.get_encoding()
        return data

    def __repr__(self):
        return f'<Persona {self.cedula} - {self.nombre}>'


# ─────────────────────────────────────────────
# MOVIMIENTO
# ─────────────────────────────────────────────
class Movimiento(db.Model):
    __tablename__ = 'movimientos'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cedula = db.Column(db.String(20), nullable=False, index=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('personas.id'), nullable=True, index=True)
    tipo = db.Column(db.String(10), nullable=False)  # entrada | salida
    observacion = db.Column(db.String(255), nullable=True)
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    confianza_verificacion = db.Column(db.Float, nullable=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)
    # ✅ Sucursal donde físicamente se registró el movimiento
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False, index=True)
    # ✅ Usuario que operó el sistema en ese momento
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True, index=True)

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
            'sucursal_id': self.sucursal_id,
            'sucursal_nombre': self.sucursal.nombre if self.sucursal else None,
            'usuario_id': self.usuario_id,
            'usuario_nombre': self.usuario_registro.username if self.usuario_registro else None,
        }

    def __repr__(self):
        return f'<Movimiento {self.tipo} - {self.cedula} - {self.fecha_hora}>'


# ─────────────────────────────────────────────
# SESION DE JORNADA
# ─────────────────────────────────────────────
class SesionJornada(db.Model):
    """
    Agrupa la entrada y salida de una persona en una jornada.
    Permite que la entrada sea en una sucursal y la salida en otra.
    """
    __tablename__ = 'sesiones_jornada'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cedula = db.Column(db.String(20), nullable=False, index=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('personas.id'), nullable=False, index=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False, index=True)

    # Entrada
    movimiento_entrada_id = db.Column(db.Integer, db.ForeignKey('movimientos.id'), nullable=True)
    sucursal_entrada_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True)
    fecha_entrada = db.Column(db.DateTime, nullable=True, index=True)

    # Salida
    movimiento_salida_id = db.Column(db.Integer, db.ForeignKey('movimientos.id'), nullable=True)
    sucursal_salida_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True)
    fecha_salida = db.Column(db.DateTime, nullable=True)

    # Estado
    abierta = db.Column(db.Boolean, default=True, nullable=False, index=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    persona = db.relationship('Persona', foreign_keys=[persona_id])
    movimiento_entrada = db.relationship('Movimiento', foreign_keys=[movimiento_entrada_id])
    movimiento_salida = db.relationship('Movimiento', foreign_keys=[movimiento_salida_id])
    sucursal_entrada = db.relationship('Sucursal', foreign_keys=[sucursal_entrada_id])
    sucursal_salida = db.relationship('Sucursal', foreign_keys=[sucursal_salida_id])

    def duracion_minutos(self):
        if self.fecha_entrada and self.fecha_salida:
            return round((self.fecha_salida - self.fecha_entrada).total_seconds() / 60, 2)
        return None

    def to_dict(self):
        return {
            'id': self.id,
            'cedula': self.cedula,
            'persona_id': self.persona_id,
            'nombre_persona': self.persona.nombre if self.persona else None,
            'empresa_id': self.empresa_id,
            # Entrada
            'sucursal_entrada_id': self.sucursal_entrada_id,
            'sucursal_entrada_nombre': self.sucursal_entrada.nombre if self.sucursal_entrada else None,
            'fecha_entrada': self.fecha_entrada.isoformat() if self.fecha_entrada else None,
            # Salida
            'sucursal_salida_id': self.sucursal_salida_id,
            'sucursal_salida_nombre': self.sucursal_salida.nombre if self.sucursal_salida else None,
            'fecha_salida': self.fecha_salida.isoformat() if self.fecha_salida else None,
            # Estado
            'abierta': self.abierta,
            'duracion_minutos': self.duracion_minutos(),
        }

    def __repr__(self):
        return f'<SesionJornada {self.cedula} - {"abierta" if self.abierta else "cerrada"}>'
