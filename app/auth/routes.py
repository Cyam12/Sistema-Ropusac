from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

from app.auth.models import Usuario
from app.extensions import get_db_connection


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redireccionar_por_rol(current_user.rol_nombre)

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        usuario = Usuario.buscar_por_email(email)

        if not usuario:
            flash("El correo no está registrado.", "danger")
            return redirect(url_for("auth.login"))

        if usuario.estado != "activo":
            flash("El usuario no está activo. Contacta al administrador.", "warning")
            return redirect(url_for("auth.login"))

        if not check_password_hash(usuario.password_hash, password):
            flash("La contraseña es incorrecta.", "danger")
            return redirect(url_for("auth.login"))

        login_user(usuario)

        actualizar_ultimo_login(usuario.id)

        return redireccionar_por_rol(usuario.rol_nombre)

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))


def redireccionar_por_rol(rol_nombre):
    if rol_nombre == "administrador":
        return redirect(url_for("admin.dashboard"))

    if rol_nombre == "vendedor":
        return redirect(url_for("vendedor.dashboard"))

    if rol_nombre == "logistica":
        return redirect(url_for("logistica.dashboard"))

    flash("Rol no reconocido en el sistema.", "danger")
    return redirect(url_for("auth.login"))


def actualizar_ultimo_login(usuario_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql = """
                UPDATE usuarios
                SET ultimo_login = NOW()
                WHERE id = %s
            """
            cursor.execute(sql, (usuario_id,))

        connection.commit()

    finally:
        connection.close()