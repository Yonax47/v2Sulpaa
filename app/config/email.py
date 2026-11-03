"""Configuración central de correo y verificación de cuentas."""

import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cryptography.fernet import Fernet


def _booleano(nombre, predeterminado=False):
    valor = os.getenv(nombre)
    if valor is None:
        return predeterminado
    return valor.strip().lower() in {"1", "true", "yes", "on"}


def _entero(nombre, predeterminado, minimo=1, maximo=None):
    try:
        valor = int(os.getenv(nombre, str(predeterminado)))
    except (TypeError, ValueError):
        valor = predeterminado
    valor = max(minimo, valor)
    return min(valor, maximo) if maximo is not None else valor


def _url_publica(valor):
    valor = str(valor or "").strip().rstrip("/")
    if not valor:
        return ""
    partes = urlsplit(valor)
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        return ""
    if partes.username or partes.password or partes.query or partes.fragment:
        return ""
    return valor


def _fecha_utc_opcional(nombre):
    valor = str(os.getenv(nombre) or "").strip()
    if not valor:
        return None
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(
            f"{nombre} debe ser una fecha ISO-8601 con zona horaria."
        ) from error
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def configurar_email(app):
    """Carga variables sin contactar proveedores ni bases de datos."""

    enabled = _booleano("MAIL_ENABLED", False)
    app.config.update(
        MAIL_ENABLED=enabled,
        RESEND_API_KEY=str(os.getenv("RESEND_API_KEY") or "").strip(),
        MAIL_FROM=str(os.getenv("MAIL_FROM") or "").strip(),
        MAIL_FROM_NAME=str(os.getenv("MAIL_FROM_NAME") or "SULPAA").strip(),
        APP_PUBLIC_URL=_url_publica(os.getenv("APP_PUBLIC_URL")),
        MAIL_PAYLOAD_ENCRYPTION_KEY=str(
            os.getenv("MAIL_PAYLOAD_ENCRYPTION_KEY") or ""
        ).strip(),
        MAIL_RATE_LIMIT_KEY=str(
            os.getenv("MAIL_RATE_LIMIT_KEY") or ""
        ).strip(),
        EMAIL_VERIFICATION_TTL_HOURS=_entero(
            "EMAIL_VERIFICATION_TTL_HOURS", 24, 1, 168
        ),
        EMAIL_RESEND_MIN_SECONDS=_entero(
            "EMAIL_RESEND_MIN_SECONDS", 120, 30, 86400
        ),
        EMAIL_RESEND_MAX_WINDOW=_entero(
            "EMAIL_RESEND_MAX_WINDOW", 5, 1, 50
        ),
        MAIL_OUTBOX_MAX_ATTEMPTS=_entero(
            "MAIL_OUTBOX_MAX_ATTEMPTS", 5, 1, 20
        ),
        MAIL_OUTBOX_LEASE_SECONDS=_entero(
            "MAIL_OUTBOX_LEASE_SECONDS", 300, 30, 3600
        ),
        EMAIL_EXISTING_GRACE_END=_fecha_utc_opcional(
            "EMAIL_EXISTING_GRACE_END"
        ),
    )
    if enabled:
        requeridas = (
            "RESEND_API_KEY",
            "MAIL_FROM",
            "APP_PUBLIC_URL",
            "MAIL_PAYLOAD_ENCRYPTION_KEY",
            "MAIL_RATE_LIMIT_KEY",
        )
        faltantes = [nombre for nombre in requeridas if not app.config.get(nombre)]
        if faltantes:
            raise RuntimeError(
                "Falta configuración obligatoria de correo: "
                + ", ".join(faltantes)
            )
    encryption_key = app.config.get("MAIL_PAYLOAD_ENCRYPTION_KEY")
    if encryption_key:
        try:
            Fernet(encryption_key.encode("ascii"))
        except (ValueError, TypeError) as error:
            raise RuntimeError(
                "MAIL_PAYLOAD_ENCRYPTION_KEY no es una clave Fernet válida."
            ) from error
    rate_key = app.config.get("MAIL_RATE_LIMIT_KEY", "")
    if rate_key and len(rate_key) < 32:
        raise RuntimeError("MAIL_RATE_LIMIT_KEY debe tener al menos 32 caracteres.")
