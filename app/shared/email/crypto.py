"""Cifrado autenticado de secretos temporales del outbox."""

import json

from cryptography.fernet import Fernet, InvalidToken


class EmailCryptoError(RuntimeError):
    pass


def encrypt_payload(payload, key):
    try:
        cipher = Fernet(str(key or "").encode("ascii"))
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return cipher.encrypt(raw.encode("utf-8")).decode("ascii")
    except (ValueError, TypeError) as error:
        raise EmailCryptoError("La clave de cifrado de correo no es válida.") from error


def decrypt_payload(value, key):
    try:
        cipher = Fernet(str(key or "").encode("ascii"))
        raw = cipher.decrypt(str(value or "").encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as error:
        raise EmailCryptoError("No se pudo descifrar el payload temporal.") from error
    if not isinstance(data, dict):
        raise EmailCryptoError("El payload temporal no es un objeto.")
    return data
