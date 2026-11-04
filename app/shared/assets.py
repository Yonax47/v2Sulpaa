"""Versionado de CSS/JS para no mezclar HTML nuevo con estilos cacheados."""

import hashlib
from pathlib import Path


def registrar_versionado_assets(app):
    versiones = {}
    raiz = Path(app.static_folder).resolve()

    @app.url_defaults
    def versionar(endpoint, values):
        if endpoint != "static" or "v" in values:
            return
        nombre = values.get("filename", "")
        ruta = (raiz / nombre).resolve()
        if not ruta.is_relative_to(raiz) or ruta.suffix not in {".css", ".js"}:
            return
        if nombre not in versiones and ruta.is_file():
            versiones[nombre] = hashlib.sha256(ruta.read_bytes()).hexdigest()[:12]
        if nombre in versiones:
            values["v"] = versiones[nombre]
