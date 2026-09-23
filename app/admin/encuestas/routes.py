"""Rutas HTTP del módulo administrativo de Encuestas (Bloque 4).

URLs:

- GET  /admin/encuestas/             listado con filtros
- GET  /admin/encuestas/<id>         detalle con respuesta y eventos
- POST /admin/encuestas/<id>/reenviar   rehabilita la invitación

El panel nunca altera respuestas: solo lista y rehabilita el canal
PORTAL cuando corresponde (auditable con evento REINTENTO).
"""

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.admin.encuestas.services import (
    ROLES_ENCUESTAS_ADMIN,
    ReglaEncuestaError,
    listar_encuestas,
    obtener_detalle,
    reenviar,
)
from app.shared.decorators import login_required, role_required


admin_encuestas_bp = Blueprint(
    "admin_encuestas",
    __name__,
    url_prefix="/admin/encuestas",
    template_folder="../../../templates",
)


@admin_encuestas_bp.route("/", methods=["GET"])
@login_required
@role_required(*ROLES_ENCUESTAS_ADMIN)
def listado():
    """Lista encuestas con filtros de estado y período."""
    filtros = {
        "estado": request.args.get("estado", ""),
        "desde": request.args.get("desde", ""),
        "hasta": request.args.get("hasta", ""),
    }
    encuestas = listar_encuestas(filtros)
    return render_template(
        "admin/encuestas/lista.html",
        encuestas=encuestas,
        filtros=filtros,
    )


@admin_encuestas_bp.route("/<int:encuesta_id>", methods=["GET"])
@login_required
@role_required(*ROLES_ENCUESTAS_ADMIN)
def detalle(encuesta_id):
    """Muestra la encuesta con su respuesta y sus eventos."""
    try:
        encuesta = obtener_detalle(encuesta_id)
    except ReglaEncuestaError:
        abort(404)
    return render_template(
        "admin/encuestas/detalle.html",
        encuesta=encuesta,
    )


@admin_encuestas_bp.route("/<int:encuesta_id>/reenviar", methods=["POST"])
@login_required
@role_required(*ROLES_ENCUESTAS_ADMIN)
def regenerar(encuesta_id):
    """Rehabilita la invitación PORTAL de la encuesta (evento REINTENTO)."""
    try:
        reenviar(session.get("usuario_id"), session.get("roles"), encuesta_id)
    except ReglaEncuestaError as error:
        flash(str(error), "error")
        return redirect(url_for("admin_encuestas.detalle",
                                encuesta_id=encuesta_id))
    flash("Invitación rehabilitada correctamente.", "success")
    return redirect(url_for("admin_encuestas.detalle",
                            encuesta_id=encuesta_id))