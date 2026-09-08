"""
Rutas HTTP del módulo Administración de SULPAA V2.
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.shared.decorators import login_required, admin_required

from app.administracion.services import (
    obtener_perfil_admin,
    actualizar_perfil_admin,
)


administracion_bp = Blueprint(
    "administracion",
    __name__,
    url_prefix="/administracion",
)


@administracion_bp.route("/perfil", methods=["GET", "POST"])
@login_required
@admin_required
def perfil():

    usuario_id = session["usuario_id"]

    if request.method == "POST":

        resultado = actualizar_perfil_admin(
            usuario_id=usuario_id,
            nombres=request.form.get("nombres", ""),
            apellido_paterno=request.form.get("apellido_paterno", ""),
            apellido_materno=request.form.get("apellido_materno", ""),
            telefono=request.form.get("telefono", ""),
        )

        flash(resultado["mensaje"], "success" if resultado["ok"] else "danger")

        return redirect(url_for("administracion.perfil"))

    resultado = obtener_perfil_admin(usuario_id)

    if not resultado["ok"]:
        flash(resultado["mensaje"], "danger")
        return redirect(url_for("inicio"))

    return render_template("admin/perfil.html", perfil=resultado["perfil"])