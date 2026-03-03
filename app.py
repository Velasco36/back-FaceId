import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from datetime import timedelta
from config import Config
from models import db, TokenBlacklist
from routes.personas import personas_bp
from routes.verificacion import verificacion_bp
from routes.movimientos import movimientos_bp
from routes.auth import auth_bp
from routes.branches import sucursal_bp
from routes.company import empresa_bp
from routes.usuarios import usuarios_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── JWT ───────────────────────────────────────────────────────────────
    app.config['JWT_SECRET_KEY'] = os.environ.get(
        'JWT_SECRET_KEY', 'tu-clave-jwt-secreta-cambiar-en-produccion'
    )
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False

    # ── Extensiones ───────────────────────────────────────────────────────
    jwt = JWTManager(app)
    db.init_app(app)
    Migrate(app, db)

    # CORS — sin credentials ya que usamos Bearer token, no cookies
    CORS(app,
         resources={r"/*": {"origins": "*"}},
         expose_headers=["Authorization", "Content-Type"],
    )

    # ── JWT Handlers ──────────────────────────────────────────────────────
    @jwt.token_in_blocklist_loader
    def verificar_blacklist(jwt_header, jwt_payload):
        return TokenBlacklist.query.filter_by(
            jti=jwt_payload['jti']
        ).first() is not None

    @jwt.revoked_token_loader
    def token_revocado(jwt_header, jwt_payload):
        return jsonify({'error': 'Token revocado, inicie sesión nuevamente'}), 401

    @jwt.expired_token_loader
    def token_expirado(jwt_header, jwt_payload):
        return jsonify({'error': 'Token expirado, inicie sesión nuevamente'}), 401

    @jwt.invalid_token_loader
    def token_invalido(error):
        return jsonify({'error': 'Token inválido'}), 401

    @jwt.unauthorized_loader
    def sin_token(error):
        return jsonify({'error': 'Token requerido'}), 401

    # ── Blueprints ────────────────────────────────────────────────────────
    app.register_blueprint(auth_bp,          url_prefix='/api/auth')
    app.register_blueprint(empresa_bp,       url_prefix='/api')
    app.register_blueprint(sucursal_bp,      url_prefix='/api')
    app.register_blueprint(usuarios_bp,      url_prefix='/api')
    app.register_blueprint(personas_bp,      url_prefix='/api')
    app.register_blueprint(verificacion_bp,  url_prefix='/api')
    app.register_blueprint(movimientos_bp,   url_prefix='/api')

    # ── Inicializar carpetas y tablas ─────────────────────────────────────
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER_REGISTROS'],   exist_ok=True)
        os.makedirs(app.config['UPLOAD_FOLDER_MOVIMIENTOS'], exist_ok=True)

    # ── Error handlers ────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint no encontrado"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Error interno del servidor"}), 500

    # ── Rutas utilitarias ─────────────────────────────────────────────────
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "ok", "mensaje": "API de Reconocimiento Facial activa"}), 200

    @app.route('/uploads/registros/<filename>')
    def serve_registro_image(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER_REGISTROS'], filename)

    @app.route('/uploads/movimientos/<filename>')
    def serve_movimiento_image(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER_MOVIMIENTOS'], filename)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
