"""Portal público de encuestas de satisfacción de SULPAA V2.

El enlace de la encuesta se entrega al cliente en el detalle de su
pedido (canal PORTAL). El token viaja en la URL, pero nunca en claro
dentro de la base de datos: se persiste su hash (búsqueda) y su forma
cifrada (reconstrucción del enlace).

Toda regla de estado y transacción vive en el Service:
``app/encuestas/services.py``.
"""

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.encuestas.services import (
    ReglaEncuestaError,
    obtener_encuesta_publica,
    responder_encuesta,
)
from app.shared.decorators import login_required


encuesta_bp = Blueprint(
    "encuesta",
    __name__,
    template_folder="../../templates",
)


@encuesta_bp.route("/encuesta/<token>", methods=["GET"])
@login_required
def respuesta(token):
    """Muestra el formulario de la encuesta o el agradecimiento final."""
    try:
        encuesta = obtener_encuesta_publica(token)
    except ReglaEncuestaError as error:
        flash(str(error), "error")
        return redirect(url_for("inicio"))

    ya_respondida = encuesta["estado"] == "RESPONDIDA"

    return render_template(
        "encuesta/respuesta.html",
        token=token,
        numero_pedido=encuesta.get("numero_pedido"),
        estado=encuesta["estado"],
        ya_respondida=ya_respondida,
        anterior=getattr(request, "form", None),
    )


@encuesta_bp.route("/encuesta/<token>", methods=["POST"])
@login_required
def procesar(token):
    """Valida y registra la respuesta de la encuesta."""
    try:
        responder_encuesta(token, request.form)
    except ReglaEncuestaError as error:
        flash(str(error), "error")
        return redirect(url_for("encuesta.respuesta", token=token))

    flash("¡Gracias por compartir tu experiencia!", "success")
    return redirect(url_for("encuesta.respuesta", token=token))