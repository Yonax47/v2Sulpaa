"""Gestión segura de imágenes del catálogo SULPAA V2.

Reglas importantes:

1. Nunca se guardan archivos nuevos en el disco temporal del servidor.
   Se usa ``CATALOGO_IMAGENES_DIR``, que en producción debe apuntar a un
   volumen persistente revisado. Si no está configurado, la carga de
   archivos se rechaza con un mensaje claro.
2. Se aceptan únicamente JPG, PNG y WEBP. El tipo real se comprueba por
   la firma binaria del archivo, no solo por su extensión.
3. El nombre original no se reutiliza: se genera un nombre aleatorio.
   Así se evitan rutas con ``..``, caracteres de control o extensiones
   dobles.
4. Las rutas existentes bajo ``img/`` siguen permitidas como respaldo
   estático. La base de datos guarda una ruta lógica, nunca una ruta
   absoluta del servidor.
"""

import os
import tempfile
import uuid
from pathlib import Path

from flask import current_app, has_app_context, url_for

from app.admin.catalogo.validaciones import ErrorCatalogo


# ============================================================
# CONFIGURACIÓN
# ============================================================

PREFIJO_LOGICO = "uploads/catalogo/"
PREFIJO_ESTATICO = "img/"
EXTENSIONES_PERMITIDAS = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".webp": "webp",
}
TAMANO_MAXIMO_POR_DEFECTO = 5 * 1024 * 1024  # 5 MB


def _configuracion(nombre, por_defecto=None):
    """Lee un valor desde la configuración de Flask o del entorno."""

    valor = None
    # ``current_app`` es un proxy y no se puede evaluar fuera de una petición.
    # Esta comprobación permite usar las validaciones también en pruebas puras.
    if has_app_context():
        valor = current_app.config.get(nombre)
    if valor in (None, ""):
        valor = os.getenv(nombre, por_defecto)
    return valor


def maximo_bytes():
    """Tamaño máximo permitido para una imagen cargada."""

    try:
        return int(
            _configuracion(
                "CATALOGO_IMAGENES_MAX_BYTES",
                TAMANO_MAXIMO_POR_DEFECTO,
            )
        )
    except (TypeError, ValueError):
        return TAMANO_MAXIMO_POR_DEFECTO


def directorio_imagenes():
    """Devuelve la carpeta persistente donde se guardan las imágenes.

    Falla cerrado cuando la variable no existe o apunta a una carpeta
    temporal. Es preferible no guardar nada antes que perder las fotos al
    reiniciar el contenedor de Railway.
    """

    valor = _configuracion("CATALOGO_IMAGENES_DIR")

    if not valor:
        raise ErrorCatalogo(
            "La carga de imágenes está desactivada: falta configurar "
            "CATALOGO_IMAGENES_DIR con un volumen persistente."
        )

    ruta = Path(str(valor)).expanduser()

    if not ruta.is_absolute():
        raise ErrorCatalogo(
            "CATALOGO_IMAGENES_DIR debe ser una ruta absoluta."
        )

    try:
        ruta = ruta.resolve()
    except OSError:
        raise ErrorCatalogo(
            "CATALOGO_IMAGENES_DIR no es una ruta válida."
        ) from None

    temporales = {
        Path(tempfile.gettempdir()).resolve(),
        Path("/tmp"),
        Path("/var/tmp"),
    }

    for temporal in temporales:
        try:
            if ruta == temporal or temporal in ruta.parents:
                raise ErrorCatalogo(
                    "CATALOGO_IMAGENES_DIR no puede estar dentro de una "
                    "carpeta temporal. Usa un volumen persistente."
                )
        except OSError:
            continue

    if ruta.exists() and not ruta.is_dir():
        raise ErrorCatalogo(
            "CATALOGO_IMAGENES_DIR existe, pero no es una carpeta."
        )

    try:
        ruta.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ErrorCatalogo(
            "No se pudo crear la carpeta persistente de imágenes."
        ) from None

    return ruta


# ============================================================
# FIRMAS REALES DE ARCHIVO
# ============================================================

def _firma_imagen(contenido):
    """Reconoce el tipo real de una imagen por sus primeros bytes."""

    if contenido.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if (
        len(contenido) >= 12
        and contenido.startswith(b"RIFF")
        and contenido[8:12] == b"WEBP"
    ):
        return "webp"
    return None


def _extension_normalizada(nombre_original):
    """Obtiene una extensión permitida desde el nombre enviado."""

    nombre = str(nombre_original or "")
    if not nombre or "\x00" in nombre:
        raise ErrorCatalogo("El archivo de imagen no tiene un nombre válido.")

    # Se descarta cualquier ruta que intente enviar el navegador.
    nombre = nombre.replace("\\", "/").split("/")[-1]
    if nombre in ("", ".", ".."):
        raise ErrorCatalogo("El archivo de imagen no tiene un nombre válido.")

    extension = Path(nombre).suffix.lower()

    if extension not in EXTENSIONES_PERMITIDAS:
        raise ErrorCatalogo(
            "Formato no permitido. Usa JPG, PNG o WEBP."
        )

    return ".jpg" if extension == ".jpeg" else extension


# ============================================================
# GUARDAR UNA IMAGEN
# ============================================================

def guardar_imagen_segura(archivo):
    """Valida y guarda una imagen en el volumen persistente.

    Devuelve la ruta lógica que se guarda en ``imagenes_catalogo.ruta``.
    No se confía en el nombre ni en el tipo declarado por el navegador.
    """

    if archivo is None or not getattr(archivo, "filename", ""):
        raise ErrorCatalogo("Selecciona un archivo de imagen.")

    extension = _extension_normalizada(archivo.filename)

    limite = maximo_bytes()
    contenido = archivo.read(limite + 1)

    if not contenido:
        raise ErrorCatalogo("El archivo de imagen está vacío.")

    if len(contenido) > limite:
        raise ErrorCatalogo(
            "La imagen supera el tamaño máximo permitido "
            f"({limite // (1024 * 1024)} MB)."
        )

    tipo_real = _firma_imagen(contenido)

    if tipo_real is None:
        raise ErrorCatalogo(
            "El archivo no parece una imagen JPG, PNG o WEBP válida."
        )

    tipo_esperado = EXTENSIONES_PERMITIDAS[extension]
    if tipo_real != tipo_esperado:
        raise ErrorCatalogo(
            "La extensión no coincide con el contenido real de la imagen."
        )

    carpeta = directorio_imagenes()
    nombre_archivo = f"{uuid.uuid4().hex}{extension}"
    destino = carpeta / nombre_archivo

    # Se escribe primero un archivo temporal dentro de la misma carpeta
    # persistente y luego se renombra. Así nunca queda una imagen a medias.
    temporal = carpeta / f".{nombre_archivo}.parte"

    try:
        with open(temporal, "wb") as salida:
            salida.write(contenido)
        os.replace(temporal, destino)
    except OSError:
        try:
            temporal.unlink(missing_ok=True)
        except OSError:
            pass
        raise ErrorCatalogo(
            "No se pudo guardar la imagen en el almacenamiento persistente."
        ) from None

    return f"{PREFIJO_LOGICO}{nombre_archivo}"


# ============================================================
# RUTAS LÓGICAS
# ============================================================

def normalizar_ruta_imagen(ruta):
    """Valida una ruta lógica existente del catálogo.

    Se aceptan dos casos:

    - ``img/...``: imagen estática que ya forma parte del proyecto.
    - ``uploads/catalogo/...``: archivo guardado en el volumen persistente.

    No se aceptan URLs externas, rutas absolutas ni ``..``.
    """

    texto = str(ruta or "").strip().replace("\\", "/")

    if not texto:
        raise ErrorCatalogo("La ruta de la imagen es obligatoria.")

    if len(texto) > 500:
        raise ErrorCatalogo("La ruta de la imagen es demasiado larga.")

    if texto.startswith("/") or "://" in texto or ".." in texto.split("/"):
        raise ErrorCatalogo("La ruta de la imagen no es segura.")

    if any(ord(caracter) < 32 for caracter in texto):
        raise ErrorCatalogo("La ruta de la imagen contiene caracteres inválidos.")

    if not (
        texto.startswith(PREFIJO_ESTATICO)
        or texto.startswith(PREFIJO_LOGICO)
    ):
        raise ErrorCatalogo(
            "La ruta debe comenzar con img/ o uploads/catalogo/."
        )

    extension = Path(texto).suffix.lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ErrorCatalogo(
            "La ruta debe terminar en .jpg, .jpeg, .png o .webp."
        )

    return texto


def nombre_archivo_persistente(ruta):
    """Devuelve el nombre del archivo cuando vive en el volumen persistente."""

    ruta = normalizar_ruta_imagen(ruta)

    if not ruta.startswith(PREFIJO_LOGICO):
        return None

    nombre = ruta[len(PREFIJO_LOGICO):]
    if not nombre or "/" in nombre or "\\" in nombre:
        raise ErrorCatalogo("La ruta de la imagen no es segura.")

    return nombre


def eliminar_archivo_no_registrado(ruta):
    """Elimina solo un archivo nuevo cuya fila no pudo guardarse.

    Esta limpieza no se usa para borrar imágenes históricas. Su único objetivo
    es no dejar un archivo huérfano cuando la escritura en la base falla justo
    después de cargarlo al volumen.
    """

    try:
        nombre = nombre_archivo_persistente(ruta)
        if not nombre:
            return
        destino = directorio_imagenes() / nombre
        destino.unlink(missing_ok=True)
    except (ErrorCatalogo, OSError):
        # La operación principal ya falló; la limpieza no debe ocultar su causa.
        return


def url_imagen_catalogo(ruta):
    """Construye la URL pública de una imagen del catálogo.

    Las imágenes estáticas siguen usando ``/static``. Las imágenes
    nuevas se sirven por la ruta controlada ``/media/catalogo/<archivo>``.
    """

    if not ruta:
        return None

    try:
        ruta = normalizar_ruta_imagen(ruta)
    except ErrorCatalogo:
        return None

    if ruta.startswith(PREFIJO_LOGICO):
        return url_for(
            "comercio.media_catalogo",
            filename=ruta[len(PREFIJO_LOGICO):],
        )

    return url_for("static", filename=ruta)


def ruta_para_mostrar(imagen):
    """Devuelve la ruta lógica de una fila de ``imagenes_catalogo``."""

    if not imagen:
        return None
    if isinstance(imagen, dict):
        return imagen.get("ruta")
    return None
