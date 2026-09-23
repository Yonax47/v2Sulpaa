"""Rutas HTTP del panel del repartidor.

El repartidor autenticado trabaja únicamente sobre SUS asignaciones:
el Service valida posesión y estado dentro de una transacción.

- GET  /repartidor                                     listado de repartos
- GET  /repartidor/<entrega_id>                        detalle de un reparto
- POST /repartidor/<entrega_id>/aceptar               aceptar la asignación
- POST /repartidor/<entrega_id>/iniciar               iniciar el reparto
- POST /repartidor/<entrega_id>/confirmar             confirmar entregado
"""

import logging

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

from app.operaciones.services import (
    ReglaOperativaError,
    aceptar_asignacion,
    confirmar_entrega,
    iniciar_reparto,
    listar_repartos_repartidor,
    obtener_detalle_reparto_repartidor,
)
from app.shared.decorators import login_required, role_required


logger = logging.getLogger(__name__)

repartidor_bp = Blueprint(
    "repartidor",
    __name__,
    url_prefix="/repartidor",
    template_folder="../../templates",
)

ROLES_REPARTIDOR = ("REPARTIDOR",)


@repartidor_bp.route("/", methods=["GET"])
@login_required
@role_required(*ROLES_REPARTIDOR)
def repartos():
    """Lista SOLO los repartos asignados al repartidor autenticado."""
    try:
        datos = listar_repartos_repartidor(session.get("usuario_id"))
    except ReglaOperativaError as error:
        flash(str(error), "danger")
        datos = {"activas": [], "historial": []}
    return render_template(
        "repartidor/repartos.html",
        activas=datos["activas"],
        historial=datos["historial"],
    )


@repartidor_bp.route("/<entrega_id>", methods=["GET"])
@login_required
@role_required(*ROLES_REPARTIDOR)
def detalle_reparto(entrega_id):
    """Muestra el detalle de UNO de los repartos del repartidor."""
    detalle = None
    try:
        detalle = obtener_detalle_reparto_repartidor(
            session.get("usuario_id"), entrega_id
        )
    except ReglaOperativaError as error:
        flash(str(error), "danger")
    if not detalle:
        abort(404)
    return render_template("repartidor/detalle_reparto.html", reparto=detalle)


def _volver_a(entrega_id):
    return redirect(
        url_for("repartidor.detalle_reparto", entrega_id=entrega_id)
    )


@repartidor_bp.route("/<entrega_id>/aceptar", methods=["POST"])
@login_required
@role_required(*ROLES_REPARTIDOR)
def aceptar(entrega_id):
    """El repartidor acepta su propia asignación."""
    try:
        resultado = aceptar_asignacion(
            session.get("usuario_id"),
            entrega_id,
        )
        flash("Asignación aceptada.", "success")
    except ReglaOperativaError as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló la aceptación del reparto %s", entrega_id)
        flash("No se pudo aceptar. No se guardaron cambios.", "danger")
    return _volver_a(entrega_id)


@repartidor_bp.route("/<entrega_id>/iniciar", methods=["POST"])
@login_required
@role_required(*ROLES_REPARTIDOR)
def iniciar(entrega_id):
    """Pone su reparto EN_TRANSITO solo si la asignación está aceptada."""
    try:
        resultado = iniciar_reparto(
            session.get("usuario_id"),
            session.get("roles"),
            entrega_id,
        )
        flash("Reparto iniciado hacia el destino.", "success")
    except ReglaOperativaError as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el inicio del reparto %s", entrega_id)
        flash("No se pudo iniciar. No se guardaron cambios.", "danger")
    return _volver_a(entrega_id)


@repartidor_bp.route("/<entrega_id>/confirmar", methods=["POST"])
@login_required
@role_required(*ROLES_REPARTIDOR)
def confirmar(entrega_id):
    """Confirma la entrega contra el código presentado por el cliente."""
    try:
        resultado = confirmar_entrega(
            session.get("usuario_id"),
            session.get("roles"),
            entrega_id,
            codigo_cliente=request.form.get("codigo_cliente"),
        )
        flash("Entrega confirmada correctamente.", "success")
    except ReglaOperativaError as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló la confirmación del reparto %s", entrega_id)
        flash("No se pudo confirmar. No se guardaron cambios.", "danger")
    return _volver_a(entrega_id)