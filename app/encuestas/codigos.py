"""Emisión y verificación del token de encuesta de satisfacción.

El token se genera con una fuente criptográficamente segura y NUNCA se
almacena en texto plano en la base de datos:

- token_hash:     SHA-256 en hexadecimal (columna ``encuestas.token_hash``).
- token_cifrado:  el token cifrado con Fernet (columna
  ``encuestas.token_cifrado``) para que la aplicación pueda reconstruir el
  enlace público de la encuesta sin persistir el token en claro.

Reutiliza el mismo patrón de ``app/operaciones/codigos_cliente.py`` pero
con un contexto propio y un token más largo, porque la encuesta viaja en
una URL pública y necesita mayor entropía.
"""

import base64
import hashlib
import hmac
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken


# Alfabeto sin caracteres ambiguos (sin 0/O/1/I/l).
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LARGO_TOKEN = 32
_CLAVE_CONTEXTO = b"sulpaa-encuesta-satisfaccion-v1"


def _clave_fernet():
    """Deriva la clave Fernet de la SECRET_KEY sin exponer llaves nuevas."""
    secreto = os.getenv(
        "SECRET_KEY", "clave-desarrollo-no-segura"
    ).encode("utf-8")
    digest = hashlib.sha256(secreto + _CLAVE_CONTEXTO).digest()
    return base64.urlsafe_b64encode(digest)


def generar_token():
    """Genera un token URL-safe usando una fuente criptográficamente segura."""
    return "".join(secrets.choice(_ALFABETO) for _ in range(_LARGO_TOKEN))


def hash_token(token):
    """Devuelve el hash SHA-256 del token (únicamente para buscar sin plano)."""
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def cifrar_token(token):
    """Devuelve el token cifrado con Fernet (para persistir sin plano)."""
    return Fernet(_clave_fernet()).encrypt(
        str(token).encode("utf-8")
    ).decode("utf-8")


def descifrar_token(token_cifrado):
    """Descifra el token solo si corresponde a esta aplicación."""
    if not token_cifrado:
        return None
    try:
        return Fernet(_clave_fernet()).decrypt(
            str(token_cifrado).encode("utf-8")
        ).decode("utf-8")
    except (InvalidToken, TypeError, ValueError):
        return None


def verificar_token(token_cifrado, token_ingresado):
    """Compara el token ingresado con el cifrado en tiempo constante."""
    esperado = descifrar_token(token_cifrado)
    ingresado = str(token_ingresado or "").strip()
    if not esperado or not ingresado:
        return False
    return hmac.compare_digest(esperado, ingresado)