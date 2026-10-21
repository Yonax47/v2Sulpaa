"""Rutas del módulo administrativo de Auditoría (solo lectura).

- GET /admin/auditoria/            -> listado paginado con filtros.
- GET /admin/auditoria/<id>        -> detalle de un evento.

El acceso está restringido al rol GERENTE (rol gerencial real).
La auditoría es de solo lectura: no existen rutas de edición ni
de eliminación.
"""

from flask import (
    Blueprint,
    abort,
    render_template,
    request,
    session,
)

from app.admin.auditoria.services import (
    listar_eventos_admin,
    obtener_evento_admin,
    opciones_filtros,
)
from app.shared.decorators import login_required, role_required

admin_auditoria_bp = Blueprint(
    "admin_auditoria",
    __name__,
    url_prefix="/admin/auditoria",
    template_folder="../../../templates",
)


def _filtros_desde_request():
    """Construye el filtro con los parámetros GET reales."""
    filtros = {}
    for clave in ("usuario_id", "modulo", "accion", "entidad"):
        valor = (request.args.get(clave) or "").strip()
        if valor:
            filtros[clave] = valor
    desde = (request.args.get("desde") or "").strip()
    hasta = (request.args.get("hasta") or "").strip()
    if desde:
        filtros["desde"] = desde + " 00:00:00"
    if hasta:
        filtros["hasta"] = hasta + " 23:59:59"
    return filtros


@admin_auditoria_bp.route("/", methods=["GET"])
@login_required
@role_required("GERENTE")
def listado():
    """Lista los eventos de auditoría realmente registrados."""
    filtros = _filtros_desde_request()

    resultado = listar_eventos_admin(
        session.get("roles"),
        filtros=filtros,
        pagina=request.args.get("pagina", 1),
        por_pagina=request.args.get("por_pagina", 25),
    )

    opciones = opciones_filtros(session.get("roles"))

    return render_template(
        "admin/auditoria/lista.html",
        eventos=resultado["eventos"],
        total=resultado["total"],
        pagina=resultado["pagina"],
        paginas=resultado["paginas"],
        por_pagina=resultado["por_pagina"],
        filtros=filtros,
        modulos=opciones["modulos"],
        acciones=opciones["acciones"],
    )


@admin_auditoria_bp.route("/<int:evento_id>", methods=["GET"])
@login_required
@role_required("GERENTE")
def detalle(evento_id):
    """Detalle de un único evento."""
    evento = obtener_evento_admin(session.get("roles"), evento_id)
    if not evento:
        abort(404)
    return render_template(
        "admin/auditoria/detalle.html",
        evento=evento,
    )
