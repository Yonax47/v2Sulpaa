"""Infraestructura reemplazable de correo transaccional."""

from app.shared.email.provider import EmailMessage, EmailResult
from app.shared.email.resend import ResendProvider

__all__ = ["EmailMessage", "EmailResult", "ResendProvider"]
