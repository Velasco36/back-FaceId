

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import json

db = SQLAlchemy()


class Persona(db.Model):
    __tablename__ = 'personas'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cedula = db.Column(db.String(20), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(100), nullable=False)
    imagen_path = db.Column(db.String(255), nullable=True)
    encoding_facial = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow, nullable=False)

    movimientos = db.relationship('Movimiento', backref='persona', lazy='dynamic')

    def set_encoding(self, encoding_array):
        if encoding_array is not None:
            self.encoding_facial = json.dumps(encoding_array.tolist())

    def get_encoding(self):
        if self.encoding_facial:
            return json.loads(self.encoding_facial)
        return None

    def to_dict(self, include_encoding=False):
        data = {
            'id': self.id,
            'cedula': self.cedula,
            'nombre': self.nombre,
            'imagen_path': self.imagen_path,
            'activo': self.activo,
            'tiene_encoding': self.encoding_facial is not None,
            'fecha_registro': self.fecha_registro.isoformat() if self.fecha_registro else None,
            'fecha_actualizacion': self.fecha_actualizacion.isoformat() if self.fecha_actualizacion else None,
        }
        if include_encoding:
            data['encoding'] = self.get_encoding()
        return data

    def __repr__(self):
        return f'<Persona {self.cedula} - {self.nombre}>'


class Movimiento(db.Model):
    __tablename__ = 'movimientos'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cedula = db.Column(db.String(20), db.ForeignKey('personas.cedula'), nullable=False, index=True)
    tipo = db.Column(db.String(10), nullable=False)
    imagen_path = db.Column(db.String(255), nullable=True)
    observacion = db.Column(db.String(255), nullable=True)
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    confianza_verificacion = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'cedula': self.cedula,
            'nombre_persona': self.persona.nombre if self.persona else None,
            'tipo': self.tipo,
            'imagen_path': self.imagen_path,
            'observacion': self.observacion,
            'confianza_verificacion': self.confianza_verificacion,
            'fecha_hora': self.fecha_hora.isoformat() if self.fecha_hora else None,
        }

    def __repr__(self):
        return f'<Movimiento {self.tipo} - {self.cedula} - {self.fecha_hora}>'

