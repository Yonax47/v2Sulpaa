"""
Reglas de negocio del módulo administrativo de Contenido de SULPAA V2.

Este Service orquesta el CRUD del contenido educativo administrable
("Aprende") aplicando las reglas del Bloque 3:

- Solo GERENTE y ADMINISTRADOR administran contenido.
- El contenido público es únicamente el PUBLICADO; un borrador jamás
  debe servirse en rutas públicas (Protección también en backend).
- El slug es único; si choca, se desambigua automáticamente.
- Las variantes vinculadas DEBEN ser variantes reales del catálogo.
- No se elimina evidencia de accesos_contenido.
"""

import logging
import re

from app.admin.contenido.repositories import (
    actualizar_contenido,
    agregar_fuente,
    crear_contenido,
    eliminar_contenido,
    eliminar_fuente,
    eliminar_variante_vinculo,
    listar_catalogo_variantes,
    listar_contenidos,
    obtener_contenido,
    validar_tipo_contenido,
    vincular_variante,
)

logger = logging.getLogger(__name__)


ROLES_CONTENIDO = ("GERENTE", "ADMINISTRADOR")

ETIQUETAS_TIPO = {
    "QUE_ES": "¿Qué es la kombucha?",
    "HISTORIA": "Historia",
    "ELABORACION": "Elaboración",
    "SABORES": "Sabores",
    "CONSUMO": "Consumo y consejos",
    "FAQ": "Preguntas frecuentes",
    "SULPAA": "Sobre SULPAA",
    "GENERAL": "General",
}


class ErrorContenido(Exception):
    """Error de negocio seguro para mostrar en la interfaz."""


def _validar_acceso(roles):
    """Fuerza el permiso real antes de administrar contenido."""
    roles = roles or []
    if not (set(ROLES_CONTENIDO) & set(roles)):
        raise ErrorContenido(
            "No tienes permisos para administrar el contenido."
        )


def _validar_titulo(titulo):
    titulo = str(titulo or "").strip()
    if not titulo:
        raise ErrorContenido("El título es obligatorio.")
    if len(titulo) > 150:
        raise ErrorContenido(
            "El título no puede superar los 150 caracteres."
        )
    return titulo


def _generar_slug(texto):
    """
    Genera un slug sencillo y seguro desde un texto libre.
    No captura caracteres especiales; se limita a normalizar.
    """
    texto = str(texto or "").strip().lower()
    texto = re.sub(r"[^a-z0-9\u00e0-\u00ff]+", "-", texto)
    texto = re.sub(r"-{2,}", "-", texto).strip("-")
    if not texto:
        raise ErrorContenido(
            "No fue posible generar un identificador (slug) del título."
        )
    return texto


def _normalizar_resumen(resumen):
    resumen = str(resumen or "").strip()
    return resumen[:500] or None


def listar_para_admin(roles, estado=None):
    """Lista el contenido educativo con su estado de publicación."""
    _validar_acceso(roles)
    if estado not in (None, "BORRADOR", "PUBLICADO"):
        raise ErrorContenido("El estado indicado no es válido.")
    return listar_contenidos(estado=estado)


def obtener_para_admin(roles, contenido_id):
    """Devuelve el contenido completo (con fuentes y variantes)."""
    _validar_acceso(roles)
    return obtener_contenido(contenido_id)


def crear_para_admin(
    actor_id,
    roles,
    titulo,
    tipo,
    estado="BORRADOR",
    resumen=None,
    contenido=None,
    imagen_ruta=None,
    orden=None,
):
    """
    Crea un contenido educativo.

    Reglas:
    - Permiso real obligatorio.
    - Título obligatorio; slug automático y único.
    - Estado PUBLICADO exige contenido mínimo (título + texto).
    """
    _validar_acceso(roles)

    titulo = _validar_titulo(titulo)
    tipo = validar_tipo_contenido(tipo)
    estado = _normalizar_estado(estado)

    if estado == "PUBLICADO" and not str(contenido or "").strip():
        raise ErrorContenido(
            "Un contenido publicado necesita un cuerpo de texto."
        )

    slug_base = _generar_slug(titulo)
    slug = _slug_unico(slug_base)

    try:
        return crear_contenido(
            titulo=titulo,
            slug=slug,
            resumen=_normalizar_resumen(resumen),
            contenido=(str(contenido or "").strip() or None),
            tipo=tipo,
            imagen_ruta=(str(imagen_ruta or "").strip() or None),
            estado=estado,
            autor_usuario_id=actor_id,
            orden=_normalizar_orden(orden),
        )
    except ValueError as error:
        raise ErrorContenido(str(error)) from error
    except Exception:
        logger.exception("Falló la creación de contenido educativo")
        raise ErrorContenido(
            "No se pudo crear el contenido. No se guardaron cambios."
        ) from None


def actualizar_para_admin(
    actor_id,
    roles,
    contenido_id,
    titulo,
    tipo,
    estado="BORRADOR",
    resumen=None,
    contenido=None,
    imagen_ruta=None,
    orden=None,
):
    """Actualiza un contenido educativo existente (permiso real)."""
    _validar_acceso(roles)

    titulo = _validar_titulo(titulo)
    tipo = validar_tipo_contenido(tipo)
    estado = _normalizar_estado(estado)

    actual = obtener_contenido(contenido_id)
    if not actual:
        raise ErrorContenido("El contenido indicado no existe.")

    if estado == "PUBLICADO" and not str(contenido or "").strip():
        # Conserva el cuerpo previo si el formulario no lo envió completo
        # solo cuando ya existía texto.
        if not str(actual.get("contenido") or "").strip():
            raise ErrorContenido(
                "Un contenido publicado necesita un cuerpo de texto."
            )

    slug = _slug_unico(_generar_slug(titulo), excluir=contenido_id)

    try:
        return actualizar_contenido(
            contenido_id=contenido_id,
            titulo=titulo,
            slug=slug,
            resumen=_normalizar_resumen(resumen),
            contenido=(str(contenido or "").strip() or None),
            tipo=tipo,
            imagen_ruta=(str(imagen_ruta or "").strip() or None),
            estado=estado,
            orden=_normalizar_orden(orden),
        )
    except ValueError as error:
        raise ErrorContenido(str(error)) from error
    except Exception:
        logger.exception("Falló la actualización de contenido %s", contenido_id)
        raise ErrorContenido(
            "No se pudo guardar el contenido. No se guardaron cambios."
        ) from None


def eliminar_para_admin(roles, contenido_id):
    """Elimina un contenido educativo (conserva auditoría de accesos)."""
    _validar_acceso(roles)
    try:
        return eliminar_contenido(contenido_id)
    except ValueError as error:
        raise ErrorContenido(str(error)) from error
    except Exception:
        logger.exception("Falló la eliminación de contenido %s", contenido_id)
        raise ErrorContenido(
            "No se pudo eliminar el contenido. No se guardaron cambios."
        ) from None


def agregar_fuente_para_admin(roles, contenido_id, nombre, **opciones):
    """Agrega una fuente de respaldo a un contenido educativo."""
    _validar_acceso(roles)

    nombre = str(nombre or "").strip()
    if not nombre:
        raise ErrorContenido("El nombre de la fuente es obligatorio.")
    if len(nombre) > 150:
        raise ErrorContenido("El nombre de la fuente es demasiado largo.")

    try:
        return agregar_fuente(
            contenido_id=contenido_id,
            nombre=nombre,
            referencia=opciones.get("referencia"),
            url=opciones.get("url"),
            nota=opciones.get("nota"),
        )
    except ValueError as error:
        raise ErrorContenido(str(error)) from error


def eliminar_fuente_para_admin(roles, contenido_id, fuente_id):
    """Elimina una fuente de respaldo de un contenido."""
    _validar_acceso(roles)
    try:
        return eliminar_fuente(contenido_id, fuente_id)
    except Exception:
        logger.exception("Falló la eliminación de la fuente %s", fuente_id)
        raise ErrorContenido(
            "No se pudo eliminar la fuente."
        ) from None


def vincular_variante_para_admin(roles, contenido_id, variante_id):
    """Vincula un contenido con una variante REAL del catálogo."""
    _validar_acceso(roles)
    try:
        return vincular_variante(contenido_id, variante_id)
    except ValueError as error:
        raise ErrorContenido(str(error)) from error
    except Exception:
        logger.exception("Falló el vínculo variante %s", contenido_id)
        raise ErrorContenido(
            "No se pudo vincular la variante al contenido."
        ) from None


def eliminar_variante_para_admin(roles, contenido_id, vinculo_id):
    """Elimina el vínculo de una variante con el contenido."""
    _validar_acceso(roles)
    try:
        return eliminar_variante_vinculo(contenido_id, vinculo_id)
    except Exception:
        logger.exception("Falló la eliminación del vínculo %s", vinculo_id)
        raise ErrorContenido(
            "No se pudo eliminar el vínculo de la variante."
        ) from None


def obtener_catalogo_variantes(roles):
    """Lista variantes reales activas para el formulario de vínculos."""
    _validar_acceso(roles)
    return listar_catalogo_variantes()


# ============================================================
# UTILIDADES INTERNAS
# ============================================================

def _normalizar_estado(estado):
    estado = str(estado or "BORRADOR").strip().upper()
    if estado not in ("BORRADOR", "PUBLICADO"):
        raise ErrorContenido("El estado de publicación no es válido.")
    return estado


def _normalizar_orden(orden):
    try:
        if orden in (None, ""):
            return None
        return int(orden)
    except (TypeError, ValueError):
        raise ErrorContenido("El orden debe ser un número entero.") from None


def _slug_unico(slug, excluir=None):
    """Garantiza unicidad consultando los slugs existentes."""
    existentes = {
        fila["slug"]
        for fila in listar_contenidos(estado=None)
    }
    if slug not in existentes:
        return slug
    if excluir:
        # El propio contenido no debe chocar consigo mismo.
        propio = obtener_contenido(excluir)
        if propio and propio["slug"] == slug:
            return slug
    contador = 2
    while f"{slug}-{contador}" in existentes:
        contador += 1
    return f"{slug}-{contador}"


def etiqueta_tipo(tipo):
    """Etiqueta legible de un tipo de contenido."""
    return ETIQUETAS_TIPO.get(tipo, tipo or "General")


# ============================================================
# EXPOSICIÓN DE ETIQUETAS PARA PLANTILLAS
# ============================================================

TIPOS_CONTENIDO = list(ETIQUETAS_TIPO.keys())
