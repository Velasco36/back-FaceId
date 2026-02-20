import os

class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # En Replit, BASE_DIR ya apunta a /home/runner/tu-proyecto (persistente)
    # La DB se crea junto a config.py
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f"sqlite:///{os.path.join(BASE_DIR, 'facial_recognition.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER_REGISTROS = os.path.join(BASE_DIR, 'uploads', 'registros')
    UPLOAD_FOLDER_MOVIMIENTOS = os.path.join(BASE_DIR, 'uploads', 'movimientos')

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
    FACE_DISTANCE_THRESHOLD = 0.5
    ITEMS_PER_PAGE = 20

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    FACE_DISTANCE_THRESHOLD = 0.45
