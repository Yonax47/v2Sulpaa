"""Proveedor determinista para pruebas; no realiza tráfico de red."""

from app.shared.email.provider import EmailProvider, EmailResult


class FakeEmailProvider(EmailProvider):
    def __init__(self, results=None):
        self.results = list(results or [EmailResult(True, provider_id="fake-1")])
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        if self.results:
            return self.results.pop(0)
        return EmailResult(True, provider_id=f"fake-{len(self.messages)}")
