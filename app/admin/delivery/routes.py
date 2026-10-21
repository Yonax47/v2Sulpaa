"""Rutas del módulo administrativo de Configuración de Delivery.

Route -> Service -> Repository. Las rutas no calculan nada por su
cuenta: delegan en el servicio y solo representan el resultado.
"""
import logging

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.admin.delivery.services import (
    ErrorDelivery,
    actualizar_tarifa_delivery_admin,
    obtener_configuracion_delivery,
    simular_cotizacion,
)
from app.shared.decorators import login_required, role_required

logger = logging.getLogger(__name__)

admin_delivery_bp = Blueprint(
    "admin_delivery",
    __name__,
    url_prefix="/admin/delivery",
    template_folder="../../../templates",
)

ROLES_ACCESO = ("GERENTE", "ADMINISTRADOR")


@admin_delivery_bp.route("", methods=["GET"], strict_slashes=False)
@admin_delivery_bp.route("/", methods=["GET"])
@login_required
@role_required(*ROLES_ACCESO)
def configuracion():
    """Muestra la configuración de delivery y la fórmula vigente."""
    roles = session.get("roles") or []
    configuracion = obtener_configuracion_delivery(roles)
    return render_template(
        "admin/delivery/configuracion.html",
        **configuracion
    )


@admin_delivery_bp.route("/tarifa", methods=["POST"])
@login_required
@role_required(*ROLES_ACCESO)
def actualizar_tarifa():
    """Actualiza la tarifa real de delivery (solo GERENTE)."""
    roles = session.get("roles") or []
    tarifa_id = (request.form.get("tarifa_id") or "").strip()

    try:
        actualizar_tarifa_delivery_admin(
            roles=roles,
            actor_id=session.get("usuario_id"),
            actor_roles=session.get("roles"),
            tarifa_id=tarifa_id,
            datos=request.form.to_dict(),
            direccion_ip=request.remote_addr,
        )
    except PermissionError as error:
        flash(str(error), "error")
    except ErrorDelivery as error:
        flash(str(error), "error")
    else:
        flash("Tarifa de delivery actualizada correctamente.", "success")

    return redirect(url_for("admin_delivery.configuracion"))


@admin_delivery_bp.route("/simular", methods=["POST"])
@login_required
@role_required(*ROLES_ACCESO)
def simular():
    """Simulación de costo con la fórmula real (respuesta JSON)."""
    datos = request.get_json(silent=True) or request.form

    try:
        resultado = simular_cotizacion(
            session.get("roles"),
            datos.get("distancia_km"),
            datos.get("peso_kg"),
            datos.get("subtotal"),
        )
    except PermissionError as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 403
    except ErrorDelivery as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400

    return jsonify(resultado)
