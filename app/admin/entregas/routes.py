"""Rutas HTTP del módulo administrativo de Entregas.

URLs (como acciones, nunca como estados libres):

- GET    /admin/entregas/                          listado con filtros
- GET    /admin/entregas/<entrega_id>              detalle operativo
- POST   /admin/entregas/<entrega_id>/listo        entrega preparada
- POST   /admin/entregas/<entrega_id>/recojo       recojo disponible
- POST   /admin/entregas/<entrega_id>/programar    programar (fecha)
- POST   /admin/entregas/<entrega_id>/asignar      asignar repartidor
- POST   /admin/entregas/<entrega_id>/iniciar      iniciar reparto
- POST   /admin/entregas/<entrega_id>/confirmar    confirmar entrega (código)
- POST   /admin/entregas/<entrega_id>/recojo-confirmar  confirmar recojo
- POST   /admin/entregas/<entrega_id>/incidencia   registrar incidencia
- POST   /admin/entregas/<entrega_id>/cancelar     cancelar (motivo)
- POST   /admin/entregas/<entrega_id>/envio        avanzar envío trasportista
- GET    /admin/entregas/repartidores              planilla de repartidores
- POST   /admin/entregas/repartidores/registrar    registrar repartidor

Toda regla de estado y transacción vive en el Service de Operaciones.
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

from app.admin.entregas.services import (
    ROLES_ENTREGAS,
    ReglaEntregaError,
    actualizar_envio,
    asignar,
    cancelar,
    confirmar_entrega,
    confirmar_pago_anticipado,
    confirmar_recojo,
    confirmar_recojo_disponible,
    enriquecer_detalle,
    iniciar,
    listar_entregas,
    listar_repartidores,
    marcar_listo,
    obtener_detalle,
    programar,
    registrar_incidencia,
    registrar_repartidor,
    resolver_incidencia,
)
from app.shared.decorators import login_required, role_required


logger = logging.getLogger(__name__)

admin_entregas_bp = Blueprint(
    "admin_entregas",
    __name__,
    url_prefix="/admin/entregas",
    template_folder="../../../templates",
)


@admin_entregas_bp.route("/", methods=["GET"])
@login_required
@role_required(*ROLES_ENTREGAS)
def listado():
    """Lista entregas reales con filtros validados por Service."""
    filtros = {
        "q": request.args.get("q", ""),
        "estado": request.args.get("estado", ""),
        "tipo": request.args.get("tipo", ""),
    }
    entregas = []
    try:
        entregas = listar_entregas(filtros)
    except ReglaEntregaError as error:
        flash(str(error), "danger")
    return render_template(
        "admin/entregas/lista.html",
        entregas=entregas,
        filtros=filtros,
    )


@admin_entregas_bp.route("/repartidores", methods=["GET"])
@login_required
@role_required(*ROLES_ENTREGAS)
def repartidores():
    """Muestra la planilla real de repartidores registrados."""
    planilla = []
    try:
        planilla = listar_repartidores()
    except ReglaEntregaError as error:
        flash(str(error), "danger")
    return render_template(
        "admin/entregas/repartidores.html",
        repartidores=planilla,
    )


@admin_entregas_bp.route("/repartidores/registrar", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def registrar_repartidor_route():
    """Registra un repartidor (usuario + rol + planilla) atómicamente."""
    try:
        resultado = registrar_repartidor(
            session.get("usuario_id"), session.get("roles"), request.form
        )
        flash(resultado.get("mensaje", "Repartidor registrado."), "success")
    except ReglaEntregaError as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el registro de un repartidor")
        flash("No se pudo registrar el repartidor. No se guardaron cambios.", "danger")
    return redirect(url_for("admin_entregas.repartidores"))


@admin_entregas_bp.route("/<entrega_id>", methods=["GET"])
@login_required
@role_required(*ROLES_ENTREGAS)
def detalle(entrega_id):
    """Muestra el detalle operativo completo de la entrega."""
    entrega = enriquecer_detalle(obtener_detalle(entrega_id))
    if not entrega:
        abort(404)
    repartidores = []
    try:
        repartidores = listar_repartidores()
    except ReglaEntregaError:
        repartidores = []
    return render_template(
        "admin/entregas/detalle.html",
        entrega=entrega,
        repartidores=repartidores,
    )


def _flash_error(error):
    flash(str(error), "danger")


def _ejecutar_y_volver(accion, entrega_id, q="detalle", **opciones):
    """Ejecuta una acción válida y regresa al detalle de la entrega."""
    try:
        resultado = accion(
            session.get("usuario_id"), session.get("roles"), entrega_id, **opciones
        )
        flash(resultado.get("mensaje", "Operación registrada correctamente."), "success")
    except ReglaEntregaError as error:
        _flash_error(error)
    except Exception:
        logger.exception("Falló la operación de entrega %s", entrega_id)
        flash("No se pudo completar la operación. No se guardaron cambios.", "danger")
    return redirect(url_for("admin_entregas.detalle", entrega_id=entrega_id, _anchor=q))


@admin_entregas_bp.route("/<entrega_id>/listo", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_listo(entrega_id):
    """Marca la entrega preparada (LISTO) y emite el código de delivery."""
    return _ejecutar_y_volver(marcar_listo, entrega_id, "acciones")


@admin_entregas_bp.route("/<entrega_id>/recojo", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_recojo(entrega_id):
    """Activa el RECOJO: LISTO_PARA_RECOJO + notificación + código."""
    return _ejecutar_y_volver(confirmar_recojo_disponible, entrega_id, "acciones")


@admin_entregas_bp.route("/<entrega_id>/programar", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_programar(entrega_id):
    """Programa la fecha de entrega (delivery o transportista)."""
    return _ejecutar_y_volver(
        programar, entrega_id, "acciones",
        fecha_programada=request.form.get("fecha_programada"),
    )


@admin_entregas_bp.route("/<entrega_id>/asignar", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_asignar(entrega_id):
    """Asigna el reparto a un repartidor activo y disponible."""
    return _ejecutar_y_volver(
        asignar, entrega_id, "acciones",
        repartidor_id=request.form.get("repartidor_id"),
    )


@admin_entregas_bp.route("/<entrega_id>/iniciar", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_iniciar(entrega_id):
    """Pone la entrega EN_TRANSITO con asignación aceptada."""
    return _ejecutar_y_volver(iniciar, entrega_id, "acciones")


@admin_entregas_bp.route("/<entrega_id>/confirmar", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_confirmar(entrega_id):
    """Confirma la entrega contra el código presentado por el cliente."""
    return _ejecutar_y_volver(
        confirmar_entrega, entrega_id, "acciones",
        codigo_cliente=request.form.get("codigo_cliente"),
    )


@admin_entregas_bp.route("/<entrega_id>/recojo-confirmar", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_confirmar_recojo(entrega_id):
    """Confirma el recojo contra el código presentado por el cliente."""
    return _ejecutar_y_volver(
        confirmar_recojo, entrega_id, "acciones",
        codigo_cliente=request.form.get("codigo_cliente"),
    )


@admin_entregas_bp.route("/<entrega_id>/incidencia", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_incidencia(entrega_id):
    """Registra una incidencia y pone la entrega en INCIDENCIA."""
    return _ejecutar_y_volver(
        registrar_incidencia, entrega_id, "incidencias",
        tipo=request.form.get("tipo"),
        descripcion=request.form.get("descripcion"),
    )


@admin_entregas_bp.route("/<entrega_id>/cancelar", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_cancelar(entrega_id):
    """Cancela la entrega y libera repartidores."""
    return _ejecutar_y_volver(
        cancelar, entrega_id, "acciones",
        motivo=request.form.get("motivo"),
    )


@admin_entregas_bp.route("/<entrega_id>/envio", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_envio(entrega_id):
    """Avanza el envío trasportista y registra el seguimiento."""
    try:
        resultado = actualizar_envio(
            session.get("usuario_id"),
            session.get("roles"),
            entrega_id,
            request.form.get("estado_envio"),
            codigo_seguimiento=request.form.get("codigo_seguimiento"),
            url_seguimiento=request.form.get("url_seguimiento"),
            ubicacion_texto=request.form.get("ubicacion_texto"),
        )
        flash("Envío actualizado correctamente.", "success")
    except ReglaEntregaError as error:
        _flash_error(error)
    except Exception:
        logger.exception("Falló la actualización del envío %s", entrega_id)
        flash("No se pudo actualizar el envío. No se guardaron cambios.", "danger")
    return redirect(url_for("admin_entregas.detalle", entrega_id=entrega_id, _anchor="transportista"))


@admin_entregas_bp.route("/<entrega_id>/pago-anticipado", methods=["POST"])
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_pago_anticipado(entrega_id):
    """Confirma administrativamente un pago anticipado pendiente."""
    detalle = obtener_detalle(entrega_id)
    if not detalle:
        abort(404)
    try:
        resultado = confirmar_pago_anticipado(
            session.get("usuario_id"), session.get("roles"), detalle["pedido_id"]
        )
        flash("Pago anticipado confirmado.", "success")
    except ReglaEntregaError as error:
        _flash_error(error)
    except Exception:
        logger.exception("Falló la confirmación del pago %s", entrega_id)
        flash("No se pudo confirmar el pago. No se guardaron cambios.", "danger")
    return redirect(url_for("admin_entregas.detalle", entrega_id=entrega_id, _anchor="pago"))


@admin_entregas_bp.route(
    "/<entrega_id>/incidencias/<incidencia_id>/resolver", methods=["POST"]
)
@login_required
@role_required(*ROLES_ENTREGAS)
def accion_resolver(entrega_id, incidencia_id):
    """Resuelve una incidencia y restaura el estado previo de la entrega."""
    try:
        resolver_incidencia(
            session.get("usuario_id"), session.get("roles"), incidencia_id
        )
        flash("Incidencia resuelta; la entrega continúa su operativa.", "success")
    except ReglaEntregaError as error:
        _flash_error(error)
    except Exception:
        logger.exception("Falló la resolución de la incidencia %s", incidencia_id)
        flash("No se pudo resolver la incidencia. No se guardaron cambios.", "danger")
    return redirect(url_for("admin_entregas.detalle", entrega_id=entrega_id, _anchor="incidencias"))