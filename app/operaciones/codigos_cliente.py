"""Emisión y verificación del código de entrega/recojo del cliente.

El código se genera con una fuente criptográficamente segura y NUNCA se
almacena en texto plano: se persiste únicamente su forma cifrada (Fernet)
derivada de la SECRET_KEY de la aplicación. El cliente lo ve descifrado
exclusivamente cuando su entrega sigue en curso, y el flujo de confirmación
lo verifica sin volver a persistirlo.
"""

import base64
import hashlib
import hmac
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken


# Alfabeto sin caracteres ambiguos (sin 0/O/1/I).
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LARGO_CODIGO = 8
_CLAVE_CONTEXTO = b"sulpaa-codigo-cliente-v1"


def _clave_fernet():
    """Deriva la clave Fernet de la SECRET_KEY sin exponer llaves nuevas."""
    secreto = os.getenv(
        "SECRET_KEY", "clave-desarrollo-no-segura"
    ).encode("utf-8")
    digest = hashlib.sha256(secreto + _CLAVE_CONTEXTO).digest()
    return base64.urlsafe_b64encode(digest)


def generar_codigo():
    """Genera un código legible usando una fuente criptográficamente segura."""
    return "".join(secrets.choice(_ALFABETO) for _ in range(_LARGO_CODIGO))


def cifrar_codigo(codigo):
    """Devuelve el token cifrado del código (nunca el texto plano)."""
    return Fernet(_clave_fernet()).encrypt(codigo.encode("utf-8")).decode("utf-8")


def descifrar_codigo(token):
    """Descifra el token solo si corresponde a esta aplicación."""
    if not token:
        return None
    try:
        return Fernet(_clave_fernet()).decrypt(
            token.encode("utf-8")
        ).decode("utf-8")
    except (InvalidToken, TypeError, ValueError):
        return None


def verificar_codigo(token, codigo_ingresado):
    """Compara el código ingresado con el cifrado en tiempo constante."""
    esperado = descifrar_codigo(token)
    ingresado = str(codigo_ingresado or "").strip().upper()
    if not esperado or not ingresado:
        return False
    return hmac.compare_digest(esperado, ingresado)