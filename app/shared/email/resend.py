"""Adaptador HTTPS para Resend; nunca registra claves ni cuerpos."""

import requests

from app.shared.email.provider import EmailProvider, EmailResult


class ResendProvider(EmailProvider):
    ENDPOINT = "https://api.resend.com/emails"
    TIMEOUT = (3.05, 10)

    def __init__(self, api_key, from_email, from_name="SULPAA", session=None):
        self._api_key = str(api_key or "").strip()
        self._from_email = str(from_email or "").strip()
        self._from_name = str(from_name or "SULPAA").strip()
        self._session = session or requests

    def send(self, message):
        if (
            not self._api_key
            or not self._from_email
            or any("\n" in value or "\r" in value for value in (
                self._from_email, self._from_name, message.to, message.subject
            ))
        ):
            return EmailResult(False, temporary=False, error_code="CONFIG")

        remitente = (
            f"{self._from_name} <{self._from_email}>"
            if self._from_name else self._from_email
        )
        try:
            response = self._session.post(
                self.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": message.idempotency_key,
                },
                json={
                    "from": remitente,
                    "to": [message.to],
                    "subject": message.subject,
                    "html": message.html,
                    "text": message.text,
                },
                timeout=self.TIMEOUT,
                allow_redirects=False,
            )
        except requests.Timeout:
            return EmailResult(False, temporary=True, error_code="TIMEOUT")
        except requests.RequestException:
            return EmailResult(False, temporary=True, error_code="NETWORK")

        if 200 <= response.status_code < 300:
            try:
                data = response.json()
            except ValueError:
                data = {}
            return EmailResult(True, provider_id=str(data.get("id") or "") or None)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after = max(1, min(int(retry_after), 86400))
            except (TypeError, ValueError):
                retry_after = None
            return EmailResult(
                False, temporary=True, error_code="RATE_LIMIT", retry_after=retry_after
            )
        if response.status_code >= 500:
            return EmailResult(False, temporary=True, error_code="PROVIDER_5XX")
        return EmailResult(
            False,
            temporary=False,
            error_code=f"PROVIDER_{response.status_code}",
        )
