"""Rutas del módulo administrativo de Usuarios y Roles.

- GET  /admin/usuarios/                 -> listado paginado con filtros.
- GET  /admin/usuarios/nuevo            -> formulario de alta.
- POST /admin/usuarios/nuevo            -> crea el usuario (transacción).
- GET  /admin/usuarios/<id>             -> detalle/edición.
- POST /admin/usuarios/<id>/estado      -> activa/desactiva la cuenta.
- POST /admin/usuarios/<id>/roles       -> reemplaza los roles.

Toda la lógica y los permisos viven en el Service.
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

from app.admin.usuarios.services import (
    ErrorUsuarios,
    asignar_roles_usuario_admin,
    cambiar_estado_usuario_admin,
    crear_usuario_admin,
    listar_roles_admin,
    listar_usuarios_admin,
    obtener_usuario_admin,
)
from app.shared.decorators import login_required, role_required

logger = logging.getLogger(__name__)

admin_usuarios_bp = Blueprint(
    "admin_usuarios",
    __name__,
    url_prefix="/admin/usuarios",
    template_folder="../../../templates",
)


def _filtros():
    """Lee los filtros reales del listado desde la URL."""
    filtros = {}
    for clave in ("texto", "estado", "rol"):
        valor = (request.args.get(clave) or "").strip()
        if valor:
            filtros[clave] = valor
    return filtros


@admin_usuarios_bp.route("/", methods=["GET"])
@login_required
@role_required("GERENTE", "ADMINISTRADOR")
def listado():
    """Lista los usuarios reales con sus roles ACTIVOS."""
    try:
        resultado = listar_usuarios_admin(
            session.get("roles"),
            filtros=_filtros(),
            pagina=request.args.get("pagina", 1),
        )
        roles = listar_roles_admin(session.get("roles"))
    except ErrorUsuarios as error:
        flash(str(error), "danger")
        resultado = {"usuarios": [], "total": 0, "pagina": 1, "paginas": 1}
        roles = []
    except Exception:
        logger.exception("Falló el listado de usuarios")
        flash("No se pudo cargar la lista de usuarios.", "danger")
        resultado = {"usuarios": [], "total": 0, "pagina": 1, "paginas": 1}
        roles = []

    return render_template(
        "admin/usuarios/lista.html",
        usuarios=resultado["usuarios"],
        total=resultado["total"],
        pagina=resultado["pagina"],
        paginas=resultado["paginas"],
        roles=roles,
        filtros=_filtros(),
    )


@admin_usuarios_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("GERENTE", "ADMINISTRADOR")
def nuevo():
    """Formulario y creación de un usuario interno."""
    roles = listar_roles_admin(session.get("roles"))
    datos_formulario = request.form.to_dict(flat=True) if request.method == "POST" else {}

    if request.method == "POST":
        try:
            nuevo_id = crear_usuario_admin(
                roles=session.get("roles"),
                actor_id=session.get("usuario_id"),
                actor_roles=session.get("roles"),
                datos={
                    "correo": request.form.get("correo"),
                    "password": request.form.get("password"),
                    "nombres": request.form.get("nombres"),
                    "apellido_paterno": request.form.get("apellido_paterno"),
                    "apellido_materno": request.form.get("apellido_materno"),
                    "dni": request.form.get("dni"),
                    "telefono": request.form.get("telefono"),
                    "roles": request.form.getlist("roles"),
                },
                direccion_ip=request.remote_addr,
            )
            flash("Usuario creado y guardado correctamente.", "success")
            return redirect(
                url_for("admin_usuarios.detalle", usuario_id=nuevo_id)
            )
        except ErrorUsuarios as error:
            flash(str(error), "danger")
        except Exception:
            logger.exception("Falló la creación de usuario")
            flash(
                "No se pudo guardar el usuario. No se registró ningún cambio.",
                "danger",
            )

    return render_template(
        "admin/usuarios/formulario.html",
        usuario=None,
        roles=roles,
        datos=datos_formulario,
        es_gerente="GERENTE" in (session.get("roles") or []),
    )


@admin_usuarios_bp.route("/<usuario_id>", methods=["GET"])
@login_required
@role_required("GERENTE", "ADMINISTRADOR")
def detalle(usuario_id):
    """Detalle/edición de roles y estado de un usuario."""
    usuario = obtener_usuario_admin(session.get("roles"), usuario_id)
    if not usuario:
        abort(404)

    roles = listar_roles_admin(session.get("roles"))
    codigos_actuales = [fila["codigo"] for fila in usuario["roles"]]

    return render_template(
        "admin/usuarios/formulario.html",
        usuario=usuario,
        roles=roles,
        codigos_actuales=codigos_actuales,
        datos={},
        es_gerente="GERENTE" in (session.get("roles") or []),
    )


@admin_usuarios_bp.route("/<usuario_id>/estado", methods=["POST"])
@login_required
@role_required("GERENTE", "ADMINISTRADOR")
def cambiar_estado(usuario_id):
    """Activa o desactiva la cuenta indicada."""
    try:
        cambiar_estado_usuario_admin(
            roles=session.get("roles"),
            actor_id=session.get("usuario_id"),
            actor_roles=session.get("roles"),
            usuario_id=usuario_id,
            nuevo_estado=request.form.get("estado"),
            direccion_ip=request.remote_addr,
        )
        flash("Estado del usuario actualizado.", "success")
    except ErrorUsuarios as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el cambio de estado de %s", usuario_id)
        flash("No se pudo cambiar el estado. No se guardaron cambios.", "danger")
    return redirect(url_for("admin_usuarios.detalle", usuario_id=usuario_id))


@admin_usuarios_bp.route("/<usuario_id>/roles", methods=["POST"])
@login_required
@role_required("GERENTE", "ADMINISTRADOR")
def asignar_roles(usuario_id):
    """Reemplaza los roles del usuario por los enviados."""
    try:
        asignar_roles_usuario_admin(
            roles=session.get("roles"),
            actor_id=session.get("usuario_id"),
            actor_roles=session.get("roles"),
            usuario_id=usuario_id,
            codigos=request.form.getlist("roles"),
            direccion_ip=request.remote_addr,
        )
        flash("Roles actualizados y guardados.", "success")
    except ErrorUsuarios as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló la asignación de roles de %s", usuario_id)
        flash("No se pudieron guardar los roles. No se guardaron cambios.", "danger")
    return redirect(url_for("admin_usuarios.detalle", usuario_id=usuario_id))
