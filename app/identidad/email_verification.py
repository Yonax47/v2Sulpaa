"""Reglas de tokens, transición y reenvío de verificación."""

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.identidad import email_repositories
from app.shared.email.crypto import encrypt_payload
from app.shared.email.repositories import consumir_limites_persistentes
from app.shared.validators import validar_correo


logger = logging.getLogger(__name__)
MENSAJE_REENVIO = (
    "Si la cuenta puede verificarse, recibirás un mensaje con los próximos pasos."
)


def token_hash(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).digest()


def _hmac_clave(valor):
    clave = current_app.config.get("MAIL_RATE_LIMIT_KEY", "")
    if not clave:
        raise RuntimeError("MAIL_RATE_LIMIT_KEY no está configurada.")
    return hmac.new(
        clave.encode("utf-8"), str(valor or "").encode("utf-8"), hashlib.sha256
    ).digest()


def preparar_solicitud(usuario_id, correo, nombre):
    """Genera token CSPRNG, conserva hash y cifra el valor para el outbox."""

    public_url = current_app.config.get("APP_PUBLIC_URL", "")
    encryption_key = current_app.config.get("MAIL_PAYLOAD_ENCRYPTION_KEY", "")
    if not public_url or not encryption_key:
        raise RuntimeError("La verificación de correo no está configurada.")
    token = secrets.token_urlsafe(32)
    token_id = str(uuid.uuid4())
    ttl = int(current_app.config.get("EMAIL_VERIFICATION_TTL_HOURS", 24))
    return {
        "token_id": token_id,
        "evento_id": str(uuid.uuid4()),
        "usuario_id": usuario_id,
        "correo": correo,
        "token_hash": token_hash(token),
        "expira_en": (
            datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=ttl)
        ),
        "clave_idempotencia": f"VERIFICAR_CORREO:{token_id}",
        "datos": {
            "nombre": str(nombre or "cliente").strip()[:120],
            "expires_hours": ttl,
        },
        "secreto_cifrado": encrypt_payload(
            {
                "verification_url": (
                    f"{public_url}/identidad/verificacion#token={token}"
                ),
                "verification_code": token,
            },
            encryption_key,
        ),
    }


def inspeccionar(token):
    if not token or len(token) > 200:
        return {"estado": "INVALIDO"}
    registro = email_repositories.inspeccionar_token(token_hash(token))
    if not registro or registro["estado"] != "ACTIVO" or registro["invalidado_en"]:
        return {"estado": "INVALIDO"}
    if registro["consumido_en"] or registro["correo_verificado"]:
        return {"estado": "CONSUMIDO"}
    if not registro["vigente"]:
        return {"estado": "EXPIRADO"}
    return {"estado": "VALIDO"}


def confirmar(token):
    if not token or len(token) > 200:
        return {"estado": "INVALIDO"}
    return email_repositories.consumir_token(token_hash(token))


def solicitar_reenvio(correo, direccion_ip):
    """Respuesta no enumerable; limita antes de consultar si existe cuenta."""

    correo = str(correo or "").strip().lower()[:150]
    valido, _ = validar_correo(correo)
    clave_correo = correo if valido else "correo-invalido"
    try:
        permitido = consumir_limites_persistentes(
            [
                ("REENVIO_IP", _hmac_clave(direccion_ip or "sin-ip")),
                ("REENVIO_CORREO", _hmac_clave(clave_correo)),
            ],
            maximo=current_app.config.get("EMAIL_RESEND_MAX_WINDOW", 5),
            ventana_segundos=86400,
            minimo_intervalo_segundos=current_app.config.get(
                "EMAIL_RESEND_MIN_SECONDS", 120
            ),
        )
    except Exception:
        logger.error("No se pudo aplicar el límite persistente de correo")
        return {"ok": False, "mensaje": MENSAJE_REENVIO}
    if not permitido or not valido:
        return {"ok": True, "mensaje": MENSAJE_REENVIO}

    cuenta = email_repositories.buscar_cuenta_para_verificacion(correo)
    if (
        not cuenta
        or cuenta["estado"] != "ACTIVO"
        or cuenta["correo_verificado"]
    ):
        return {"ok": True, "mensaje": MENSAJE_REENVIO}
    try:
        solicitud = preparar_solicitud(
            cuenta["id"], cuenta["correo"], cuenta.get("nombres")
        )
        email_repositories.reemplazar_solicitud(solicitud)
    except Exception:
        logger.error("No se pudo crear una solicitud de verificación")
    return {"ok": True, "mensaje": MENSAJE_REENVIO}


def estado_cuenta(correo_verificado, requiere_verificacion, roles=None):
    if correo_verificado:
        return "VERIFICADO"
    if requiere_verificacion:
        return "PENDIENTE_OBLIGATORIO"
    # Históricos permanecen en transición. La fecha de gracia no se activa si
    # la variable está ausente y nunca bloquea roles administrativos de golpe.
    fin = current_app.config.get("EMAIL_EXISTING_GRACE_END")
    administrativos = {"GERENTE", "ADMINISTRADOR"}.intersection(roles or [])
    if fin and datetime.now(fin.tzinfo) >= fin and not administrativos:
        return "PENDIENTE_OBLIGATORIO"
    return "PENDIENTE_TRANSICION"
