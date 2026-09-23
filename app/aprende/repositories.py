"""
Acceso a datos públicos de la experiencia "Aprende" de SULPAA V2.

Este repositorio lee EXCLUSIVAMENTE contenido PUBLICADO desde el
cliente y registra la evidencia real de accesos (KPI-10):

- Los borradores jamás se sirven públicamente (validado también en
  el Service, no solo en el template).
- Los accesos fallidos (slug inexistente o contenido no publicado)
  quedan registrados con resultado='FALLO'.
- Nunca se registran assets ni navegación general como accesos.

Convenciones (patrón de la casa): conexiones abiertas y cerradas
SIEMPRE en ``finally``; esquemas validados desde variables de entorno.
"""

import os
import re

from app.config.database import conexion_comercio

_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")


def _esquema(nombre_variable):
    """Devuelve un nombre de esquema MySQL validado desde entorno."""
    valor = str(os.getenv(nombre_variable) or "").strip()
    if not valor or not _IDENTIFICADOR_SQL.fullmatch(valor):
        raise RuntimeError(
            f"La variable {nombre_variable} no contiene un esquema MySQL válido."
        )
    return valor


def listar_contenido_publicado():
    """
    Lista el contenido educativo PUBLICADO, ordenado y enriquecido.

    Devuelve el total de fuentes por contenido (mostrado solo si hay).
    """

    comercio = _esquema("DB_COMERCIO")

    consulta = f"""
        SELECT
            ce.id AS contenido_id,
            ce.titulo,
            ce.slug,
            ce.resumen,
            ce.tipo,
            ce.imagen_ruta,
            ce.orden,
            ce.publicado_en,
            (SELECT COUNT(*)
             FROM {comercio}.contenido_fuentes AS cf
             WHERE cf.contenido_id = ce.id) AS total_fuentes
        FROM {comercio}.contenido_educativo AS ce
        WHERE ce.estado = 'PUBLICADO'
          AND ce.publicado_en IS NOT NULL
        ORDER BY
            COALESCE(ce.orden, 99999) ASC,
            ce.publicado_en DESC
    """

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta)
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_contenido_publicado(slug):
    """
    Devuelve un contenido PUBLICADO por slug, con fuentes y variantes
    REALES del catálogo vinculadas. Retorna None si no existe o no
    está publicado.
    """

    comercio = _esquema("DB_COMERCIO")

    consulta = f"""
        SELECT
            ce.id AS contenido_id,
            ce.titulo,
            ce.slug,
            ce.resumen,
            ce.contenido,
            ce.tipo,
            ce.imagen_ruta,
            ce.orden,
            ce.publicado_en,
            ce.actualizado_en
        FROM {comercio}.contenido_educativo AS ce
        WHERE
            ce.slug = %s
            AND ce.estado = 'PUBLICADO'
            AND ce.publicado_en IS NOT NULL
        LIMIT 1
    """

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, (slug,))
            fila = cursor.fetchone()
            if not fila:
                return None

            cursor.execute(
                f"""
                SELECT nombre, referencia, url, nota
                FROM {comercio}.contenido_fuentes
                WHERE contenido_id = %s
                ORDER BY creado_en ASC
                """,
                (fila["contenido_id"],),
            )
            fila["fuentes"] = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT
                    v.id AS variante_id,
                    v.sku,
                    v.nombre_comercial,
                    COALESCE(s.nombre, 'Sin sabor') AS sabor,
                    COALESCE(p.nombre, 'Sin presentación') AS presentacion
                FROM {comercio}.contenido_variantes AS cv
                INNER JOIN {comercio}.variantes AS v
                    ON v.id = cv.variante_id
                LEFT JOIN {comercio}.sabores AS s
                    ON s.id = v.sabor_id
                LEFT JOIN {comercio}.presentaciones AS p
                    ON p.id = v.presentacion_id
                WHERE
                    cv.contenido_id = %s
                    AND v.estado = 'ACTIVO'
                ORDER BY v.nombre_comercial ASC
                """,
                (fila["contenido_id"],),
            )
            fila["variantes"] = cursor.fetchall()

            return fila
    finally:
        conexion.close()


def registrar_acceso(slug_solicitado, contenido_id, usuario_id, resultado):
    """
    Registra UN acceso real de contenido educativo (KPI-10).

    Args:
        slug_solicitado: Recurso solicitado (aunque no exista).
        contenido_id: ID del contenido, None si no se resolvió.
        usuario_id: Usuario de sesión, None si no hay sesión.
        resultado: 'EXITO' o 'FALLO'.
    """

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {comercio}.accesos_contenido (
                    contenido_id,
                    slug_solicitado,
                    usuario_id,
                    resultado,
                    creado_en
                )
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (
                    contenido_id,
                    slug_solicitado,
                    usuario_id,
                    resultado,
                ),
            )
            conexion.commit()
            return True
    finally:
        conexion.close()