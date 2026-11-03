"""Protección CSRF compartida para todas las rutas de SULPAA V2.

CSRF es un ataque donde otro sitio intenta enviar una acción usando la
sesión abierta del usuario. Este módulo crea un valor aleatorio por sesión y
exige que cada petición que modifica datos lo devuelva. De esta manera, una
página externa no puede construir una solicitud válida aunque el navegador
conserve la cookie de SULPAA.
"""

import hmac
import secrets

from flask import current_app, jsonify, render_template, request, session

from app.config.testing import seguridad_puede_omitirse


METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
CLAVE_SESION_CSRF = "_csrf_token"


class ErrorCSRF(Exception):
    """Indica que una acción fue rechazada por no tener un token válido."""


def generar_token_csrf():
    """Devuelve el token CSRF de la sesión y lo crea cuando aún no existe.

    El token no contiene datos del usuario. Se guarda dentro de la sesión
    firmada de Flask y se compara de forma segura cuando llega un POST.
    """

    token = session.get(CLAVE_SESION_CSRF)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CLAVE_SESION_CSRF] = token
    return token


def _token_recibido():
    """Busca el token enviado por formulario o por una solicitud JavaScript."""

    return (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRF-Token")
        or request.headers.get("X-CSRFToken")
        or ""
    )


def validar_csrf():
    """Rechaza toda petición que modifica datos si el token no coincide.

    La regla se aplica de forma global para no depender de que cada ruta
    recuerde agregar un decorador. Solo una aplicación con ``TESTING=True``
    puede apagarla de manera explícita; fuera de pruebas siempre queda activa.
    """

    if current_app.testing and not current_app.config.get("CSRF_ENABLED", True):
        return None
    # Una prueba de negocio puede pedir la excepción de forma explícita. La
    # función central comprueba también TESTING, por lo que esta salida no se
    # puede activar en producción mediante una bandera accidental.
    if seguridad_puede_omitirse(current_app):
        return None
    if request.method.upper() in METODOS_SEGUROS:
        return None

    esperado = session.get(CLAVE_SESION_CSRF, "")
    recibido = _token_recibido()
    if not esperado or not recibido or not hmac.compare_digest(
        str(esperado), str(recibido)
    ):
        raise ErrorCSRF()
    return None


def responder_error_csrf(_error):
    """Muestra un error entendible sin ejecutar la acción solicitada.

    Las API reciben JSON para que JavaScript pueda informar el problema. Los
    formularios reciben una página responsive con un enlace seguro para
    volver; no se repite automáticamente el POST porque podría duplicar una
    operación.
    """

    mensaje = (
        "La página venció o la solicitud no es segura. "
        "Vuelve a cargarla e intenta nuevamente."
    )
    acepta_json = (
        request.is_json
        or request.path.startswith("/api/")
        or request.accept_mimetypes.best == "application/json"
    )
    if acepta_json:
        return jsonify({"ok": False, "mensaje": mensaje}), 400
    return render_template("errors/csrf.html", mensaje=mensaje), 400


def inicializar_csrf(app):
    """Conecta la validación, el manejador y el token con la aplicación."""

    app.config.setdefault("CSRF_ENABLED", True)
    app.before_request(validar_csrf)
    app.register_error_handler(ErrorCSRF, responder_error_csrf)
    app.jinja_env.globals["csrf_token"] = generar_token_csrf
