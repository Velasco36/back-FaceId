
import os
from flask import Flask
from flask_cors import CORS
from config import Config
from models import db
from routes.personas import personas_bp
from routes.verificacion import verificacion_bp
from routes.movimientos import movimientos_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializar extensiones
    db.init_app(app)
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Registrar blueprints
    app.register_blueprint(personas_bp)
    app.register_blueprint(verificacion_bp)
    app.register_blueprint(movimientos_bp)

    # Crear tablas y carpetas necesarias
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER_REGISTROS'], exist_ok=True)
        os.makedirs(app.config['UPLOAD_FOLDER_MOVIMIENTOS'], exist_ok=True)

    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Endpoint no encontrado"}, 404

    @app.errorhandler(500)
    def server_error(e):
        return {"error": "Error interno del servidor"}, 500

    @app.route('/health', methods=['GET'])
    def health():
        return {"status": "ok", "mensaje": "API de Reconocimiento Facial activa"}

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
