from flask import Flask, redirect, url_for
from flask_login import current_user

from app.config import Config
from app.extensions import login_manager, get_db_connection
from app.auth.models import Usuario


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(usuario_id):
        return Usuario.buscar_por_id(usuario_id)

    from app.auth.routes import auth_bp
    from app.admin.routes import admin_bp
    from app.vendedor.routes import vendedor_bp
    from app.logistica.routes import logistica_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(vendedor_bp)
    app.register_blueprint(logistica_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.rol_nombre == "administrador":
                return redirect(url_for("admin.dashboard"))

            if current_user.rol_nombre == "vendedor":
                return redirect(url_for("vendedor.dashboard"))

            if current_user.rol_nombre == "logistica":
                return redirect(url_for("logistica.dashboard"))

        return redirect(url_for("auth.login"))

    @app.route("/test-db")
    def test_db():
        try:
            connection = get_db_connection()

            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total_roles FROM roles")
                resultado = cursor.fetchone()

            connection.close()

            return f"Conexión exitosa a Clever Cloud. Roles registrados: {resultado['total_roles']}"

        except Exception as e:
            return f"Error de conexión a la base de datos: {str(e)}"

    return app