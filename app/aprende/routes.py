"""
Rutas públicas de la experiencia "Aprende" de SULPAA V2.

URLs:

- GET /aprende            portada educativa (contenido PUBLICADO)
- GET /aprende/<slug>     detalle educativo administrable

Un borrador o slug inexistente responde 404 público y deja
evidencia de acceso fallido (KPI-10) sin exponer el contenido.
"""

from flask import (
    Blueprint,
    abort,
    render_template,
    session,
)

from app.aprende.services import (
    listar_publico,
    obtener_detalle_publico,
)

aprende_bp = Blueprint(
    "aprende",
    __name__,
)


@aprende_bp.route("/aprende", methods=["GET"])
def portada():
    """Portada de la experiencia educativa con contenido real publicado."""
    contenidos = listar_publico()
    return render_template(
        "aprende/aprende.html",
        contenidos=contenidos,
    )


@aprende_bp.route("/aprende/<slug>", methods=["GET"])
def detalle(slug):
    """
    Detalle educativo público.

    Registra el acceso real (EXITO o FALLO) y responde 404 cuando el
    contenido no existe, es un borrador o aún no se publicó.
    """
    contenido = obtener_detalle_publico(
        slug,
        usuario_id=session.get("usuario_id"),
    )
    if not contenido:
        abort(404)
    return render_template(
        "aprende/detalle.html",
        contenido=contenido,
    )