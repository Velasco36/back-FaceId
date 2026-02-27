import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # Database - Render usa DATABASE_URL automáticamente
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f"sqlite:///{os.path.join(BASE_DIR, 'facial_recognition.db')}"
    )

    # Render puede dar DATABASE_URL con postgres:// pero SQLAlchemy necesita postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads - en Render necesitarás usar un servicio como Cloudinary o AWS S3
    # Por ahora usaremos rutas temporales
    UPLOAD_FOLDER_REGISTROS = '/tmp/uploads/registros'
    UPLOAD_FOLDER_MOVIMIENTOS = '/tmp/uploads/movimientos'

    # General
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
    FACE_DISTANCE_THRESHOLD = float(os.environ.get('FACE_DISTANCE_THRESHOLD', 0.5))
    ITEMS_PER_PAGE = int(os.environ.get('ITEMS_PER_PAGE', 20))
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback-dev-key')

    # JWT
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'fallback-jwt-key')
    JWT_ACCESS_TOKEN_EXPIRES = 2592000
    JWT_REFRESH_TOKEN_EXPIRES = 2592000
    JWT_TOKEN_LOCATION = 'headers'
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'


class DevelopmentConfig(Config):
    DEBUG = True
    UPLOAD_FOLDER_REGISTROS = os.path.join(Config.BASE_DIR, 'uploads', 'registros')
    UPLOAD_FOLDER_MOVIMIENTOS = os.path.join(Config.BASE_DIR, 'uploads', 'movimientos')


class ProductionConfig(Config):
    DEBUG = False
    FACE_DISTANCE_THRESHOLD = 0.45
