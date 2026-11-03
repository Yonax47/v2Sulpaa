"""Contrato independiente del proveedor de correo."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str
    idempotency_key: str


@dataclass(frozen=True)
class EmailResult:
    ok: bool
    provider_id: str | None = None
    temporary: bool = False
    error_code: str | None = None
    retry_after: int | None = None


class EmailProvider:
    """Interfaz mínima para permitir sustituir Resend."""

    def send(self, message: EmailMessage) -> EmailResult:
        raise NotImplementedError
