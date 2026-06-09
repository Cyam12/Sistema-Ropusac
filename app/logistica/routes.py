from flask import Blueprint
from flask_login import login_required, current_user

from app.auth.decorators import rol_required


logistica_bp = Blueprint("logistica", __name__, url_prefix="/logistica")


@logistica_bp.route("/dashboard")
@login_required
@rol_required("logistica")
def dashboard():
    return f"Dashboard Logística / Compras - Bienvenido {current_user.nombres}"