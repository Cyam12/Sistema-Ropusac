import pymysql
from flask import current_app
from flask_login import LoginManager


login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Debes iniciar sesión para acceder al sistema."
login_manager.login_message_category = "warning"


def get_db_connection():
    connection = pymysql.connect(
        host=current_app.config["MYSQL_HOST"],
        user=current_app.config["MYSQL_USER"],
        password=current_app.config["MYSQL_PASSWORD"],
        database=current_app.config["MYSQL_DB"],
        port=current_app.config["MYSQL_PORT"],
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4"
    )

    return connection