"""
Rutas (blueprint) del m\u00f3dulo Administrativo de SULPAA V2.

Este archivo SOLO coordina requests/responses:
- La capa de datos vive en admin/repositories.py
- La l\u00f3gica de negocio vive en admin/services.py

La Etapa 1 deja listas 3 rutas:

- GET  /admin            -> redirige al dashboard (o 403 sin rol).
- GET  /admin/dashboard  -> panel con los KPI de la Etapa 1.

IMPORTANTE: este m\u00f3dulo permite \u00fanicamente roles
administrativos (GERENTE y ADMINISTRADOR), que son los 2
que el dump de identidad define con acceso total al
panel administrativo.
"""

from flask import Blueprint, redirect, render_template, url_for

from app.shared.decorators import (
    admin_required,
    login_required,
)

from app.admin.services import (
    resumen_dashboard,
)


# ============================================================
# BLUEPRINT
# ============================================================

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="../../templates",
)


# ============================================================
# RUTAS
# ============================================================

@admin_bp.route(
    "/",
    methods=["GET"],
)
@login_required
@admin_required
def indice():
    """
    Redirige /admin a /admin/dashboard.

    Si un usuario no autenticado intenta entrar:
    - login_required lo manda al login.
    Si est\u00e1 autenticado pero no es GERENTE/ADMINISTRADOR:
    - admin_required responde 403 (sin inventar vistas).
    """

    return redirect(
        url_for("admin.dashboard")
    )


@admin_bp.route(
    "/dashboard",
    methods=["GET"],
)
@login_required
@admin_required
def dashboard():
    """
    Muestra el panel administrativo (resumen ejecutivo).

    Consume la MISMA fuente que los indicadores KPI y el reporte
    KPI: resumen_dashboard(). El template solo representa los
    estados recibidos; no inventa cifras ni decide cumplimiento.
    """

    resumen = resumen_dashboard()

    return render_template(
        "admin/dashboard.html",
        kpis=resumen["kpis_funcionales"],
        resumen=resumen["resumen"],
        operativo=resumen["operativo"],
        graficos=resumen["graficos"],
    )


@admin_bp.route(
    "/kpi/",
    methods=["GET"],
)
@login_required
@admin_required
def indicadores():
    """
    Página analítica de los diez KPI funcionales (RF-01 a RF-10).

    Vista dedicada: cada indicador muestra numerador, denominador,
    fórmula, meta, estado y fuente real, y en caso de "PENDIENTE"
    indica qué evidencia concreta necesita el indicador (sin
    instrucciones técnicas).

    Reutiliza resumen_dashboard() como fuente única para que el
    dashboard, esta página y el reporte KPI nunca se contradigan.
    """

    resumen = resumen_dashboard()

    return render_template(
        "admin/kpi.html",
        kpis=resumen["kpis_funcionales"],
        resumen=resumen["resumen"],
    )
