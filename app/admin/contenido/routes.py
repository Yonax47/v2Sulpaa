"""
Rutas HTTP del módulo administrativo de Contenido de SULPAA V2.

URLs (acciones, no estados):

- GET  /admin/contenido/                          listado
- GET  /admin/contenido/nuevo                     formulario de alta
- POST /admin/contenido/nuevo                     crea contenido
- GET  /admin/contenido/<contenido_id>            detalle/edición
- POST /admin/contenido/<contenido_id>            guarda cambios
- POST /admin/contenido/<contenido_id>/eliminar   elimina contenido
- POST /admin/contenido/<contenido_id>/fuentes    agrega fuente
- POST /admin/contenido/<contenido_id>/fuentes/<fuente_id>/eliminar
- POST /admin/contenido/<contenido_id>/variantes  vincula variante
- POST /admin/contenido/<contenido_id>/variantes/<vinculo_id>/eliminar

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

from app.admin.contenido.services import (
    ErrorContenido,
    TIPOS_CONTENIDO,
    agregar_fuente_para_admin,
    actualizar_para_admin,
    crear_para_admin,
    eliminar_fuente_para_admin,
    eliminar_para_admin,
    eliminar_variante_para_admin,
    etiqueta_tipo,
    listar_para_admin,
    obtener_para_admin,
    vincular_variante_para_admin,
)
from app.shared.decorators import login_required, role_required

logger = logging.getLogger(__name__)

admin_contenido_bp = Blueprint(
    "admin_contenido",
    __name__,
    url_prefix="/admin/contenido",
    template_folder="../../../templates",
)


@admin_contenido_bp.route("/", methods=["GET"])
@login_required
@role_required(*("GERENTE", "ADMINISTRADOR"))
def listado():
    """Lista el contenido educativo administrable."""
    estado = request.args.get("estado", "")
    if estado not in ("", "BORRADOR", "PUBLICADO"):
        estado = ""
    try:
        contenidos = listar_para_admin(
            session.get("roles"), estado=estado or None
        )
        for contenido in contenidos:
            contenido["tipo_label"] = etiqueta_tipo(contenido["tipo"])
    except ErrorContenido as error:
        flash(str(error), "danger")
        contenidos = []
    return render_template(
        "admin/contenido/lista.html",
        contenidos=contenidos,
        estado=estado,
        tipos=TIPOS_CONTENIDO,
    )


@admin_contenido_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required(*("GERENTE", "ADMINISTRADOR"))
def nuevo():
    """Formulario de alta de contenido educativo."""
    if request.method == "POST":
        try:
            resultado = crear_para_admin(
                session.get("usuario_id"),
                session.get("roles"),
                titulo=request.form.get("titulo"),
                tipo=request.form.get("tipo"),
                estado=request.form.get("estado", "BORRADOR"),
                resumen=request.form.get("resumen"),
                contenido=request.form.get("contenido"),
                imagen_ruta=request.form.get("imagen_ruta"),
                orden=request.form.get("orden"),
            )
            flash("Contenido educativo creado correctamente.", "success")
            return redirect(
                url_for(
                    "admin_contenido.detalle",
                    contenido_id=resultado["contenido_id"],
                )
            )
        except ErrorContenido as error:
            flash(str(error), "danger")
    return render_template(
        "admin/contenido/formulario.html",
        contenido=None,
        tipos=TIPOS_CONTENIDO,
    )


@admin_contenido_bp.route(
    "/<contenido_id>", methods=["GET", "POST"]
)
@login_required
@role_required(*("GERENTE", "ADMINISTRADOR"))
def detalle(contenido_id):
    """Edición de contenido: campos + fuentes + variantes vinculadas."""
    contenido = obtener_para_admin(
        session.get("roles"), contenido_id
    )
    if not contenido:
        abort(404)
    contenido["tipo_label"] = etiqueta_tipo(contenido["tipo"])

    if request.method == "POST":
        try:
            actualizar_para_admin(
                session.get("usuario_id"),
                session.get("roles"),
                contenido_id,
                titulo=request.form.get("titulo"),
                tipo=request.form.get("tipo"),
                estado=request.form.get("estado", "BORRADOR"),
                resumen=request.form.get("resumen"),
                contenido=request.form.get("contenido"),
                imagen_ruta=request.form.get("imagen_ruta"),
                orden=request.form.get("orden"),
            )
            flash("Contenido educativo actualizado.", "success")
            return redirect(
                url_for(
                    "admin_contenido.detalle",
                    contenido_id=contenido_id,
                )
            )
        except ErrorContenido as error:
            flash(str(error), "danger")

    # Releer para reflejar cualquier cambio, incluidas las fuentes.
    contenido = obtener_para_admin(
        session.get("roles"), contenido_id
    )
    contenido["tipo_label"] = etiqueta_tipo(contenido["tipo"])

    return render_template(
        "admin/contenido/formulario.html",
        contenido=contenido,
        tipos=TIPOS_CONTENIDO,
        catalogo_variantes=contenido.get("catalogo_variantes") or [],
    )


@admin_contenido_bp.route(
    "/<contenido_id>/eliminar", methods=["POST"]
)
@login_required
@role_required(*("GERENTE", "ADMINISTRADOR"))
def eliminar(contenido_id):
    """Elimina el contenido (conserva la auditoría de accesos)."""
    try:
        eliminar_para_admin(session.get("roles"), contenido_id)
        flash("Contenido educativo eliminado.", "success")
    except ErrorContenido as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló la eliminación de %s", contenido_id)
        flash("No se pudo eliminar el contenido. No se guardaron cambios.", "danger")
    return redirect(url_for("admin_contenido.listado"))


@admin_contenido_bp.route(
    "/<contenido_id>/fuentes", methods=["POST"]
)
@login_required
@role_required(*("GERENTE", "ADMINISTRADOR"))
def agregar_fuente_ruta(contenido_id):
    """Agrega una fuente de respaldo al contenido."""
    try:
        agregar_fuente_para_admin(
            session.get("roles"),
            contenido_id,
            request.form.get("nombre"),
            referencia=request.form.get("referencia"),
            url=request.form.get("url"),
            nota=request.form.get("nota"),
        )
        flash("Fuente de respaldo agregada.", "success")
    except ErrorContenido as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el alta de fuente en %s", contenido_id)
        flash("No se pudo agregar la fuente. No se guardaron cambios.", "danger")
    return redirect(
        url_for("admin_contenido.detalle", contenido_id=contenido_id, _anchor="fuentes")
    )


@admin_contenido_bp.route(
    "/<contenido_id>/fuentes/<fuente_id>/eliminar", methods=["POST"]
)
@login_required
@role_required(*("GERENTE", "ADMINISTRADOR"))
def eliminar_fuente_ruta(contenido_id, fuente_id):
    """Elimina una fuente de respaldo del contenido."""
    try:
        eliminar_fuente_para_admin(
            session.get("roles"), contenido_id, fuente_id
        )
        flash("Fuente eliminada.", "success")
    except ErrorContenido as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló la baja de fuente %s", fuente_id)
        flash("No se pudo eliminar la fuente. No se guardaron cambios.", "danger")
    return redirect(
        url_for("admin_contenido.detalle", contenido_id=contenido_id, _anchor="fuentes")
    )


@admin_contenido_bp.route(
    "/<contenido_id>/variantes", methods=["POST"]
)
@login_required
@role_required(*("GERENTE", "ADMINISTRADOR"))
def vincular_variante_ruta(contenido_id):
    """Vincula el contenido con una variante REAL del catálogo."""
    try:
        vincular_variante_para_admin(
            session.get("roles"),
            contenido_id,
            request.form.get("variante_id"),
        )
        flash("Variante vinculada al contenido.", "success")
    except ErrorContenido as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el vínculo en %s", contenido_id)
        flash("No se pudo vincular la variante. No se guardaron cambios.", "danger")
    return redirect(
        url_for("admin_contenido.detalle", contenido_id=contenido_id, _anchor="variantes")
    )


@admin_contenido_bp.route(
    "/<contenido_id>/variantes/<vinculo_id>/eliminar", methods=["POST"]
)
@login_required
@role_required(*("GERENTE", "ADMINISTRADOR"))
def eliminar_variante_ruta(contenido_id, vinculo_id):
    """Elimina el vínculo entre el contenido y una variante."""
    try:
        eliminar_variante_para_admin(
            session.get("roles"), contenido_id, vinculo_id
        )
        flash("Vínculo con la variante eliminado.", "success")
    except ErrorContenido as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló la baja del vínculo %s", vinculo_id)
        flash("No se pudo eliminar el vínculo. No se guardaron cambios.", "danger")
    return redirect(
        url_for("admin_contenido.detalle", contenido_id=contenido_id, _anchor="variantes")
    )