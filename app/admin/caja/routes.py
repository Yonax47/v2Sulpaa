"""Rutas HTTP del módulo administrativo de Flujo de Caja (Bloque 4).

URLs:

- GET    /admin/caja/                listado con filtros + resumen
- GET    /admin/caja/nuevo-egreso    formulario de egreso manual
- POST   /admin/caja/nuevo-egreso    registra el egreso
- POST   /admin/caja/<id>/anular     anula un movimiento (motivo)

Todo egreso manual queda trazado con su actor (GERENTE/ADMINISTRADOR);
el flujo neto nunca se presenta como utilidad o ganancia.
"""

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.admin.caja.services import (
    ROLES_CAJA,
    ReglaCajaError,
    anular_movimiento,
    listar_movimientos,
    registrar_egreso_manual,
    resumen_caja,
)
from app.admin.caja.repositories import (
    listar_categorias,
    listar_metodos_pago,
)
from app.shared.decorators import login_required, role_required


admin_caja_bp = Blueprint(
    "admin_caja",
    __name__,
    url_prefix="/admin/caja",
    template_folder="../../../templates",
)


@admin_caja_bp.route("/", methods=["GET"])
@login_required
@role_required(*ROLES_CAJA)
def listado():
    """Lista movimientos con filtros y el resumen del período."""
    filtros = {
        "desde": request.args.get("desde", ""),
        "hasta": request.args.get("hasta", ""),
        "tipo": request.args.get("tipo", ""),
        "origen": request.args.get("origen", ""),
        "categoria_id": request.args.get("categoria_id", ""),
    }
    movimientos = listar_movimientos(filtros)
    resumen = resumen_caja(filtros)
    categorias = listar_categorias()
    return render_template(
        "admin/caja/lista.html",
        movimientos=movimientos,
        resumen=resumen,
        categorias=categorias,
        filtros=filtros,
    )


@admin_caja_bp.route("/nuevo-egreso", methods=["GET"])
@login_required
@role_required(*ROLES_CAJA)
def nuevo_egreso():
    """Muestra el formulario de egreso manual."""
    categorias = listar_categorias(tipo="EGRESO")
    metodos = listar_metodos_pago()
    return render_template(
        "admin/caja/nuevo_egreso.html",
        categorias=categorias,
        metodos=metodos,
    )


@admin_caja_bp.route("/nuevo-egreso", methods=["POST"])
@login_required
@role_required(*ROLES_CAJA)
def registrar_egreso():
    """Registra el egreso manual con su actor responsable."""
    try:
        registrar_egreso_manual(
            session.get("usuario_id"),
            session.get("roles"),
            request.form,
        )
    except ReglaCajaError as error:
        flash(str(error), "error")
        return redirect(url_for("admin_caja.nuevo_egreso"))

    flash("Egreso registrado correctamente.", "success")
    return redirect(url_for("admin_caja.listado"))


@admin_caja_bp.route("/<int:movimiento_id>/anular", methods=["POST"])
@login_required
@role_required(*ROLES_CAJA)
def anular(movimiento_id):
    """Anula un movimiento de caja indicando el motivo."""
    try:
        anular_movimiento(
            session.get("usuario_id"),
            session.get("roles"),
            movimiento_id,
            request.form.get("motivo", ""),
        )
    except ReglaCajaError as error:
        flash(str(error), "error")
        return redirect(url_for("admin_caja.listado"))

    flash("Movimiento anulado correctamente.", "success")
    return redirect(url_for("admin_caja.listado"))