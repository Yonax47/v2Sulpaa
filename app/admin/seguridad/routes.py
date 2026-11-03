"""Rutas del centro de seguridad, exclusivas para GERENTE."""

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.admin.seguridad.services import (
    desbloquear_acceso,
    listar_centro_seguridad,
    obtener_detalle_bloqueo,
)
from app.shared.decorators import login_required, role_required
from app.shared.network import obtener_ip_cliente


admin_seguridad_bp = Blueprint(
    "admin_seguridad",
    __name__,
    url_prefix="/admin/seguridad",
    template_folder="../../../templates",
)


@admin_seguridad_bp.before_request
def comprobar_centro_habilitado():
    """Responde 404 antes de consultar tablas que todavía no existen.

    La migración 002 se habilitará en otra etapa. Mientras su aprobación no
    esté registrada, ninguna URL de este blueprint llega a Servicios ni a los
    repositorios de bloqueos.
    """

    if not current_app.config.get("CENTRO_SEGURIDAD_HABILITADO", False):
        abort(404)


def _filtros_request():
    """Recoge filtros GET; Servicios valida fechas, IP y estado."""

    filtros = {
        clave: (request.args.get(clave) or "").strip()
        for clave in ("cuenta", "ip", "estado", "desde", "hasta")
    }
    return filtros


@admin_seguridad_bp.route("/accesos", methods=["GET"])
@login_required
@role_required("GERENTE")
def accesos():
    """Muestra indicadores, filtros, bloqueos y desbloqueos recientes."""

    resultado = listar_centro_seguridad(
        session.get("roles"),
        _filtros_request(),
        request.args.get("pagina", 1),
        request.args.get("por_pagina", 25),
    )
    return render_template("admin/seguridad/accesos.html", **resultado)


@admin_seguridad_bp.route("/accesos/<int:bloqueo_id>", methods=["GET"])
@login_required
@role_required("GERENTE")
def detalle(bloqueo_id):
    """Muestra un episodio y la confirmación de desbloqueo."""

    bloqueo = obtener_detalle_bloqueo(session.get("roles"), bloqueo_id)
    if not bloqueo:
        abort(404)
    return render_template(
        "admin/seguridad/detalle.html", bloqueo=bloqueo
    )


@admin_seguridad_bp.route(
    "/accesos/<int:bloqueo_id>/desbloquear", methods=["POST"]
)
@login_required
@role_required("GERENTE")
def desbloquear(bloqueo_id):
    """Finaliza un bloqueo tras CSRF, confirmación y motivo obligatorio."""

    if request.form.get("confirmar") != "1":
        flash("Debes confirmar expresamente el desbloqueo.", "danger")
        return redirect(url_for("admin_seguridad.detalle", bloqueo_id=bloqueo_id))

    resultado = desbloquear_acceso(
        session.get("roles"),
        bloqueo_id,
        session.get("usuario_id"),
        request.form.get("motivo"),
        obtener_ip_cliente(request),
    )
    flash(resultado["mensaje"], "success" if resultado["ok"] else "danger")
    return redirect(url_for("admin_seguridad.detalle", bloqueo_id=bloqueo_id))
