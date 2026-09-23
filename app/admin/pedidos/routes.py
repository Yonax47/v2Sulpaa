"""Rutas HTTP del módulo administrativo de Pedidos.

Las rutas validan sesión, rol y entrada básica. Toda regla de estado y toda
transacción se delegan al Service, manteniendo Route -> Service -> Repository.
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

from app.admin.pedidos.services import (
    ReglaPedidoError,
    confirmar_pedido,
    iniciar_preparacion,
    listar_pedidos_admin,
    obtener_detalle_admin,
)
from app.shared.decorators import login_required, role_required


logger = logging.getLogger(__name__)
ROLES_PEDIDOS = ("GERENTE", "ADMINISTRADOR", "PEDIDOS_LOGISTICA")

admin_pedidos_bp = Blueprint(
    "admin_pedidos",
    __name__,
    url_prefix="/admin/pedidos",
    template_folder="../../../templates",
)


@admin_pedidos_bp.route("/", methods=["GET"])
@login_required
@role_required(*ROLES_PEDIDOS)
def listado():
    """Muestra pedidos reales con búsqueda y filtros validados."""
    filtros = {
        "q": request.args.get("q", ""),
        "estado": request.args.get("estado", ""),
        "fecha_desde": request.args.get("fecha_desde", ""),
        "fecha_hasta": request.args.get("fecha_hasta", ""),
    }
    try:
        pedidos = listar_pedidos_admin(filtros)
    except ReglaPedidoError as error:
        flash(str(error), "danger")
        pedidos = []
    return render_template(
        "admin/pedidos/lista.html", pedidos=pedidos, filtros=filtros
    )


@admin_pedidos_bp.route("/<pedido_id>", methods=["GET"])
@login_required
@role_required(*ROLES_PEDIDOS)
def detalle(pedido_id):
    """Muestra datos, evidencia y acciones calculadas por backend."""
    pedido = obtener_detalle_admin(pedido_id, session.get("roles"))
    if not pedido:
        abort(404)
    return render_template("admin/pedidos/detalle.html", pedido=pedido)


def _ejecutar_accion(servicio, pedido_id, mensaje_exito):
    """Transforma el resultado seguro del Service en flash y redirect."""
    try:
        servicio(
            pedido_id=pedido_id,
            actor_id=session.get("usuario_id"),
            roles=session.get("roles"),
        )
        flash(mensaje_exito, "success")
    except ReglaPedidoError as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló una transición administrativa del pedido %s", pedido_id)
        flash(
            "No se pudo completar la operación. No se guardaron cambios.",
            "danger",
        )
    return redirect(url_for("admin_pedidos.detalle", pedido_id=pedido_id))


@admin_pedidos_bp.route("/<pedido_id>/confirmar", methods=["POST"])
@login_required
@role_required(*ROLES_PEDIDOS)
def confirmar(pedido_id):
    """Solicita la transición CREADO -> CONFIRMADO."""
    return _ejecutar_accion(
        confirmar_pedido, pedido_id, "Pedido confirmado correctamente."
    )


@admin_pedidos_bp.route("/<pedido_id>/iniciar-preparacion", methods=["POST"])
@login_required
@role_required(*ROLES_PEDIDOS)
def preparar(pedido_id):
    """Solicita CONFIRMADO -> EN_PREPARACION y sincroniza la entrega."""
    return _ejecutar_accion(
        iniciar_preparacion, pedido_id, "Preparación iniciada correctamente."
    )
