"""Smoke público no destructivo: no usa cuentas, documentos válidos ni compras."""

from html.parser import HTMLParser
import json

import requests


BASE = "https://v2sulpaa-production.up.railway.app"


class TokenParser(HTMLParser):
    token = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("name") == "csrf-token":
            self.token = values.get("content")


def main():
    session = requests.Session()
    result = {}
    for path, expected in (
        ("/identidad/login", 200), ("/identidad/registro", 200),
        ("/identidad/verificacion", 404), ("/identidad/verificacion/pendiente", 404),
        ("/admin/dashboard", 302), ("/mi-perfil/", 302),
        ("/checkout", 302), ("/pedidos", 302),
        ("/pedidos/smoke-sin-pedido/constancia.pdf", 302),
    ):
        r = session.get(BASE + path, timeout=45, allow_redirects=False)
        result[path] = r.status_code
        if r.status_code != expected:
            raise RuntimeError(f"Smoke inesperado {path}: HTTP {r.status_code}")
        if "Traceback (most recent call last)" in r.text:
            raise RuntimeError("Se expuso un error interno.")
    r = session.get(BASE + "/identidad/login", timeout=30)
    if "Reenviar verificación" in r.text:
        raise RuntimeError("Interfaz de correo sigue activa.")
    parser = TokenParser()
    parser.feed(r.text)
    if not parser.token:
        raise RuntimeError("Falta CSRF en página de login.")
    r = session.post(BASE + "/identidad/api/registro/verificar-dni",
                     json={"dni": "abc"}, headers={"X-CSRF-Token": parser.token}, timeout=30)
    if r.status_code != 400:
        raise RuntimeError("Validación de formato DNI inesperada.")
    result["DNI_invalido_sin_consumir_APISPERU"] = r.status_code
    r = session.post(BASE + "/identidad/logout", timeout=30)
    if r.status_code != 400:
        raise RuntimeError("CSRF sin token no fue rechazado.")
    result["CSRF_sin_token"] = r.status_code
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
