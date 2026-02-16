

import os


class Config:
    # Base de datos
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'facial_recognition.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads
    UPLOAD_FOLDER_REGISTROS = os.path.join(BASE_DIR, 'uploads', 'registros')
    UPLOAD_FOLDER_MOVIMIENTOS = os.path.join(BASE_DIR, 'uploads', 'movimientos')

    # Limite de tamano: 10MB
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # Formatos de imagen permitidos
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

    # Umbral minimo de similitud facial
    # 0.5 = estricto, 0.6 = moderado, 0.7 = permisivo
    FACE_DISTANCE_THRESHOLD = 0.5

    # Paginacion por defecto
    ITEMS_PER_PAGE = 20


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    FACE_DISTANCE_THRESHOLD = 0.45

