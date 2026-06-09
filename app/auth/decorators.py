from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def rol_required(*roles_permitidos):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Debes iniciar sesión para acceder al sistema.", "warning")
                return redirect(url_for("auth.login"))

            if current_user.rol_nombre not in roles_permitidos:
                flash("No tienes permisos para acceder a esta sección.", "danger")
                return redirect(url_for("index"))

            return func(*args, **kwargs)

        return wrapper

    return decorator