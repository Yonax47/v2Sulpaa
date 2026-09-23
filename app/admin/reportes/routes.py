"""Rutas HTTP del módulo administrativo de Reportes Gerenciales (Bloque 4).

URLs:

- GET  /admin/reportes/            panel con los tipos de reporte.
- POST /admin/reportes/generar     genera el archivo (PDF/XLSX/CSV).

Cada POST de generación es la ÚNICA fuente de solicitudes del KPI-05:
visitar el panel no genera reportes.
"""

import io

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from app.admin.reportes.services import (
    FORMATOS,
    ROLES_REPORTES,
    ReglaReporteError,
    generar_reporte,
    tipos_reportes,
)
from app.shared.decorators import login_required, role_required


admin_reportes_bp = Blueprint(
    "admin_reportes",
    __name__,
    url_prefix="/admin/reportes",
    template_folder="../../../templates",
)


@admin_reportes_bp.route("/", methods=["GET"])
@login_required
@role_required(*ROLES_REPORTES)
def panel():
    """Muestra los reportes disponibles y sus formatos."""
    return render_template(
        "admin/reportes/panel.html",
        tipos=tipos_reportes(),
        formatos=FORMATOS,
    )


@admin_reportes_bp.route("/generar", methods=["POST"])
@login_required
@role_required(*ROLES_REPORTES)
def generar():
    """Genera el reporte solicitado y lo entrega como descarga."""
    tipo = request.form.get("tipo", "")
    formato = request.form.get("formato", "")
    filtros = {
        "desde": request.form.get("desde", ""),
        "hasta": request.form.get("hasta", ""),
    }
    try:
        resultado = generar_reporte(
            tipo, formato, session.get("usuario_id"), filtros
        )
    except ReglaReporteError as error:
        flash(str(error), "error")
        return redirect(url_for("admin_reportes.panel"))

    return send_file(
        io.BytesIO(resultado["contenido"]),
        mimetype=resultado["mimetype"],
        as_attachment=True,
        download_name=resultado["nombre_archivo"],
    )