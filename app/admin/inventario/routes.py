"""
Rutas HTTP del módulo administrativo de Inventario de SULPAA V2.

URLs (acciones, no estados):

- GET  /admin/inventario/                         listado con filtros
- GET  /admin/inventario/<existencia_id>          detalle de existencia
- POST /admin/inventario/<existencia_id>/verificar  registra verificación
- POST /admin/inventario/<existencia_id>/entrada    registra ENTRADA
- POST /admin/inventario/<existencia_id>/ajuste     registra AJUSTE

Toda la lógica y los permisos reales viven en el Service.
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

from app.admin.inventario.services import (
    ErrorInventario,
    listar_existencias,
    obtener_detalle_existencia,
    registrar_ajuste,
    registrar_entrada,
    registrar_verificacion,
)
from app.shared.decorators import login_required, role_required

logger = logging.getLogger(__name__)

admin_inventario_bp = Blueprint(
    "admin_inventario",
    __name__,
    url_prefix="/admin/inventario",
    template_folder="../../../templates",
)


@admin_inventario_bp.route("/", methods=["GET"])
@login_required
@role_required("GERENTE", "ADMINISTRADOR", "INVENTARIO")
def listado():
    """Lista el inventario real con filtros opcionales."""
    filtros = {
        "q": request.args.get("q", ""),
        "bajo_minimo": request.args.get("bajo_minimo") == "1",
    }
    existencias = []
    try:
        existencias = listar_existencias(
            session.get("roles"),
            busqueda=filtros["q"],
            solo_bajo_minimo=filtros["bajo_minimo"],
        )
    except ErrorInventario as error:
        flash(str(error), "danger")
    return render_template(
        "admin/inventario/lista.html",
        existencias=existencias,
        filtros=filtros,
    )


@admin_inventario_bp.route("/<existencia_id>", methods=["GET"])
@login_required
@role_required("GERENTE", "ADMINISTRADOR", "INVENTARIO")
def detalle(existencia_id):
    """Muestra el detalle de una existencia, movimientos y verificaciones."""
    try:
        detalle = obtener_detalle_existencia(
            session.get("roles"), existencia_id
        )
    except ErrorInventario as error:
        flash(str(error), "danger")
        return redirect(url_for("admin_inventario.listado"))
    if not detalle:
        abort(404)
    return render_template(
        "admin/inventario/detalle.html",
        existencia=detalle,
    )


@admin_inventario_bp.route(
    "/<existencia_id>/verificar", methods=["POST"]
)
@login_required
@role_required("GERENTE", "ADMINISTRADOR", "INVENTARIO")
def accion_verificar(existencia_id):
    """Registra una verificación física con su fotografía histórica."""
    try:
        resultado = registrar_verificacion(
            session.get("usuario_id"),
            session.get("roles"),
            existencia_id,
            request.form.get("conteo_fisico"),
            observacion=request.form.get("observacion"),
        )
        flash(resultado["mensaje"], "success")
    except ErrorInventario as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló la verificación de %s", existencia_id)
        flash("No se pudo registrar la verificación. No se guardaron cambios.", "danger")
    return redirect(
        url_for(
            "admin_inventario.detalle",
            existencia_id=existencia_id,
            _anchor="verificaciones",
        )
    )


@admin_inventario_bp.route(
    "/<existencia_id>/entrada", methods=["POST"]
)
@login_required
@role_required("GERENTE", "ADMINISTRADOR", "INVENTARIO")
def accion_entrada(existencia_id):
    """Registra una ENTRADA de stock con motivo real y trazabilidad."""
    try:
        resultado = registrar_entrada(
            session.get("usuario_id"),
            session.get("roles"),
            existencia_id,
            request.form.get("motivo"),
            request.form.get("cantidad"),
            observacion=request.form.get("observacion"),
        )
        flash(resultado["mensaje"], "success")
    except ErrorInventario as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló la entrada de stock de %s", existencia_id)
        flash("No se pudo registrar la entrada. No se guardaron cambios.", "danger")
    return redirect(
        url_for(
            "admin_inventario.detalle",
            existencia_id=existencia_id,
            _anchor="movimientos",
        )
    )


@admin_inventario_bp.route(
    "/<existencia_id>/ajuste", methods=["POST"]
)
@login_required
@role_required("GERENTE", "ADMINISTRADOR", "INVENTARIO")
def accion_ajuste(existencia_id):
    """Registra un AJUSTE explícito (nunca automático) con trazabilidad."""
    try:
        resultado = registrar_ajuste(
            session.get("usuario_id"),
            session.get("roles"),
            existencia_id,
            request.form.get("motivo"),
            request.form.get("tipo_ajuste"),
            request.form.get("cantidad"),
            observacion=request.form.get("observacion"),
            verificacion_id=request.form.get("verificacion_id"),
        )
        flash(resultado["mensaje"], "success")
    except ErrorInventario as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el ajuste de stock de %s", existencia_id)
        flash("No se pudo registrar el ajuste. No se guardaron cambios.", "danger")
    return redirect(
        url_for(
            "admin_inventario.detalle",
            existencia_id=existencia_id,
            _anchor="movimientos",
        )
    )