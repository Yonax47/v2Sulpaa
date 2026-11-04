"""Procesador acotado del outbox; no se ejecuta durante peticiones web."""

import json
import logging
import uuid

from flask import current_app

from app.shared.email.crypto import EmailCryptoError, decrypt_payload
from app.shared.email.provider import EmailMessage
from app.shared.email.repositories import (
    marcar_enviado,
    marcar_fallo,
    reclamar_lote,
)
from app.shared.email.resend import ResendProvider
from app.shared.email.templates import render_email
from app.config.email import verificacion_correo_requerida


logger = logging.getLogger(__name__)


def _provider_from_config():
    return ResendProvider(
        current_app.config.get("RESEND_API_KEY"),
        current_app.config.get("MAIL_FROM"),
        current_app.config.get("MAIL_FROM_NAME"),
    )


def _backoff(intentos):
    return min(21600, 60 * (2 ** max(0, int(intentos) - 1)))


def _preparar_datos(fila):
    if fila["plantilla"] == "verificacion_correo" and not verificacion_correo_requerida():
        raise ValueError("Verificación de correo desactivada")
    datos = json.loads(fila["datos_json"])
    if not isinstance(datos, dict):
        raise ValueError("datos_json inválido")
    secreto = fila.get("secreto_cifrado")
    if secreto:
        datos.update(
            decrypt_payload(
                secreto,
                current_app.config.get("MAIL_PAYLOAD_ENCRYPTION_KEY"),
            )
        )
    if fila["plantilla"] == "pedido_confirmado":
        public_url = current_app.config.get("APP_PUBLIC_URL", "")
        path = str(datos.pop("order_path", ""))
        if not public_url or not path.startswith("/pedidos/"):
            raise ValueError("URL pública de pedido no configurada")
        datos["order_url"] = public_url + path
    return datos


def procesar_outbox(limite=10, provider=None):
    """Procesa un lote y devuelve métricas sin incluir destinatarios."""

    if not current_app.config.get("MAIL_ENABLED"):
        return {"reclamados": 0, "enviados": 0, "fallidos": 0, "deshabilitado": True}

    lease_token = str(uuid.uuid4())
    max_intentos = current_app.config.get("MAIL_OUTBOX_MAX_ATTEMPTS", 5)
    filas = reclamar_lote(
        max(1, min(int(limite), 50)),
        lease_token,
        current_app.config.get("MAIL_OUTBOX_LEASE_SECONDS", 300),
        max_intentos,
    )
    provider = provider or _provider_from_config()
    resumen = {"reclamados": len(filas), "enviados": 0, "fallidos": 0}

    for fila in filas:
        try:
            datos = _preparar_datos(fila)
            contenido = render_email(fila["plantilla"], datos)
            resultado = provider.send(EmailMessage(
                to=fila["destinatario"],
                subject=contenido["subject"],
                html=contenido["html"],
                text=contenido["text"],
                idempotency_key=fila["clave_idempotencia"],
            ))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, EmailCryptoError):
            resultado = None

        if resultado and resultado.ok:
            marcar_enviado(
                fila["id"], lease_token, resultado.provider_id
            )
            resumen["enviados"] += 1
            continue

        intentos = int(fila.get("intentos") or 1)
        temporal = bool(resultado and resultado.temporary)
        permanente = not temporal or intentos >= max_intentos
        espera = (
            resultado.retry_after
            if resultado and resultado.retry_after
            else _backoff(intentos)
        )
        marcar_fallo(
            fila["id"],
            lease_token,
            permanente=permanente,
            error_code=(resultado.error_code if resultado else "PAYLOAD_INVALID"),
            proximo_intento_segundos=espera,
        )
        resumen["fallidos"] += 1

    return resumen
