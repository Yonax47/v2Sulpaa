"""Rutas de autoservicio de Mi perfil."""

import logging

from flask import (
    Blueprint,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.perfil.services import (
    ErrorPerfil,
    actualizar_mi_telefono,
    crear_mi_direccion,
    crear_mi_facturacion,
    desactivar_mi_direccion,
    desactivar_mi_facturacion,
    elegir_direccion_principal,
    elegir_facturacion_predeterminada,
    obtener_mi_perfil,
)
from app.shared.decorators import login_required
from app.shared.rate_limit import consumir_limite


logger = logging.getLogger(__name__)
perfil_bp = Blueprint("perfil", __name__, url_prefix="/mi-perfil")


def _usuario_id():
    """El identificador nunca se acepta desde formularios o URL."""
    return session.get("usuario_id")


def _roles():
    return session.get("roles") or []


def _volver(ancla=None):
    return redirect(url_for("perfil.inicio", _anchor=ancla))


def _ejecutar(operacion, mensaje=None, ancla=None, **opciones):
    try:
        resultado = operacion(_usuario_id(), _roles(), **opciones)
        flash(mensaje or resultado.get("mensaje", "Cambios guardados."), "success")
    except ErrorPerfil as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló una operación segura de Mi perfil")
        flash("No se pudo completar la operación.", "danger")
    return _volver(ancla)


@perfil_bp.route("/", methods=["GET"])
@login_required
def inicio():
    try:
        datos = obtener_mi_perfil(_usuario_id(), _roles())
    except ErrorPerfil:
        abort(403)
    respuesta = make_response(render_template("perfil/inicio.html", **datos))
    # La página contiene datos personales y direcciones: no debe quedar en
    # cachés de navegador ni de proxies intermedios.
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@perfil_bp.route("/telefono", methods=["POST"])
@login_required
def actualizar_telefono():
    return _ejecutar(
        actualizar_mi_telefono,
        telefono=request.form.get("telefono"),
        ancla="datos-personales",
    )


@perfil_bp.route("/direcciones", methods=["POST"])
@login_required
def crear_direccion():
    return _ejecutar(
        crear_mi_direccion,
        datos=request.form,
        ancla="direcciones",
    )


@perfil_bp.route("/direcciones/<direccion_id>/principal", methods=["POST"])
@login_required
def direccion_principal(direccion_id):
    return _ejecutar(
        elegir_direccion_principal,
        direccion_id=direccion_id,
        ancla="direcciones",
    )


@perfil_bp.route("/direcciones/<direccion_id>/desactivar", methods=["POST"])
@login_required
def desactivar_direccion(direccion_id):
    return _ejecutar(
        desactivar_mi_direccion,
        direccion_id=direccion_id,
        ancla="direcciones",
    )


@perfil_bp.route("/facturacion", methods=["POST"])
@login_required
def crear_facturacion():
    permitido, _ = consumir_limite(
        f"facturacion:{_usuario_id()}", maximo=5, ventana_segundos=600
    )
    if not permitido:
        flash("Demasiadas consultas. Intenta nuevamente más tarde.", "danger")
        return _volver("facturacion")
    return _ejecutar(
        crear_mi_facturacion,
        tipo=request.form.get("tipo_comprobante"),
        documento=request.form.get("documento"),
        ancla="facturacion",
    )


@perfil_bp.route(
    "/facturacion/<facturacion_id>/predeterminada", methods=["POST"]
)
@login_required
def facturacion_predeterminada(facturacion_id):
    return _ejecutar(
        elegir_facturacion_predeterminada,
        facturacion_id=facturacion_id,
        ancla="facturacion",
    )


@perfil_bp.route("/facturacion/<facturacion_id>/desactivar", methods=["POST"])
@login_required
def desactivar_facturacion(facturacion_id):
    return _ejecutar(
        desactivar_mi_facturacion,
        facturacion_id=facturacion_id,
        ancla="facturacion",
    )
