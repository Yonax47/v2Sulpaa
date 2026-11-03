"""Validaciones compartidas para preparar un entorno TEST sin escribir.

Este módulo no abre conexiones. Centraliza comprobaciones de archivos,
credenciales y almacenamiento para que los comandos de diagnóstico y
preparación fallen antes de intentar cualquier cambio.
"""

import os
import tempfile
from pathlib import Path


DOMINIOS = ("identidad", "comercio", "inventario", "operaciones")
VARIABLES_TEST = (
    "DB_HOST_TEST", "DB_PORT_TEST", "DB_USER_TEST", "DB_PASSWORD_TEST",
    "DB_TEST_SCHEMA_PREFIX", "DB_IDENTIDAD_TEST", "DB_COMERCIO_TEST",
    "DB_INVENTARIO_TEST", "DB_OPERACIONES_TEST",
)


def es_marcador(valor):
    """Indica si un valor sigue vacío o conserva ``<un-marcador>``."""

    texto = str(valor or "").strip()
    return not texto or (texto.startswith("<") and texto.endswith(">"))


def variables_incompletas(entorno=None):
    """Lista variables TEST ausentes, vacías o sin reemplazar."""

    valores = entorno if entorno is not None else os.environ
    return [
        nombre for nombre in VARIABLES_TEST
        if es_marcador(valores.get(nombre))
    ]


def archivos_sql_requeridos(carpeta):
    """Devuelve las ocho rutas esperadas de estructura y datos."""

    carpeta = Path(carpeta)
    return [
        carpeta / f"{dominio}.{tipo}.sql"
        for dominio in DOMINIOS
        for tipo in ("schema", "data")
    ]


def revisar_directorio_imagenes(valor):
    """Revisa una carpeta de imágenes sin crearla ni escribir en ella."""

    if es_marcador(valor):
        return False, "CATALOGO_IMAGENES_DIR no está configurado."

    ruta = Path(str(valor)).expanduser()
    if not ruta.is_absolute():
        return False, "CATALOGO_IMAGENES_DIR debe ser una ruta absoluta."

    try:
        ruta = ruta.resolve()
        temporal = Path(tempfile.gettempdir()).resolve()
    except OSError:
        return False, "CATALOGO_IMAGENES_DIR no es una ruta válida."

    if ruta == temporal or temporal in ruta.parents:
        return False, "CATALOGO_IMAGENES_DIR no puede estar en una carpeta temporal."
    if not ruta.is_dir():
        return False, "La carpeta persistente de imágenes todavía no existe."
    if not os.access(ruta, os.R_OK | os.W_OK):
        return False, "La carpeta de imágenes no tiene permisos de lectura y escritura."
    return True, str(ruta)


def validar_credenciales_administrativas(entorno=None):
    """Valida credenciales de preparación sin revelar sus valores."""

    valores = entorno if entorno is not None else os.environ
    usuario = valores.get("DB_ADMIN_USER_TEST")
    password = valores.get("DB_ADMIN_PASSWORD_TEST")
    if es_marcador(usuario) or es_marcador(password):
        raise RuntimeError(
            "Faltan credenciales administrativas exclusivas de TEST."
        )

    usuarios_prohibidos = {
        str(valores.get("DB_USER") or "").strip(),
        str(valores.get("DB_ADMIN_USER") or "").strip(),
    }
    if str(usuario).strip() in {item for item in usuarios_prohibidos if item}:
        raise RuntimeError(
            "DB_ADMIN_USER_TEST no puede reutilizar un usuario productivo."
        )

    passwords_prohibidos = {
        valores.get("DB_PASSWORD"), valores.get("DB_ADMIN_PASSWORD"),
    }
    if password in {item for item in passwords_prohibidos if item}:
        raise RuntimeError(
            "DB_ADMIN_PASSWORD_TEST no puede reutilizar una contraseña productiva."
        )

    return str(usuario).strip(), password
