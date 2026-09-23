"""
Acceso a datos del módulo administrativo de Contenido de SULPAA V2.

Responsabilidades:

- CRUD del contenido educativo administrable (BORRADOR/PUBLICADO).
- Gestión de fuentes de respaldo y de vínculos con variantes
  REALES del catálogo (sin duplicar el catálogo).
- Lectura del uso público (accesos_contenido) para el panel.

Convenciones (patrón de la casa):

- Cada función abre y cierra su propia conexión en ``finally``.
- Las escrituras que deben ser atómicas (contenido + fuentes +
  variantes) se declaran explícitamente aquí con UNA transacción.
- Nunca se eliminan registros de auditoría de accesos.
"""

import os
import re
import uuid

from app.config.database import conexion_comercio

_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")

_TIPOS_CONTENIDO = {
    "QUE_ES",
    "HISTORIA",
    "ELABORACION",
    "SABORES",
    "CONSUMO",
    "FAQ",
    "SULPAA",
    "GENERAL",
}


def _esquema(nombre_variable):
    """Devuelve un nombre de esquema MySQL validado desde entorno."""
    valor = str(os.getenv(nombre_variable) or "").strip()
    if not valor or not _IDENTIFICADOR_SQL.fullmatch(valor):
        raise RuntimeError(
            f"La variable {nombre_variable} no contiene un esquema MySQL válido."
        )
    return valor


def validar_tipo_contenido(tipo):
    """Valida que el tipo pertenezca al catálogo cerrado definido."""
    tipo = str(tipo or "").strip().upper()
    if tipo not in _TIPOS_CONTENIDO:
        raise ValueError("El tipo de contenido indicado no es válido.")
    return tipo


# ============================================================
# LISTADOS
# ============================================================

def listar_contenidos(estado=None):
    """
    Lista el contenido educativo, opcionalmente filtrado por estado.

    Devuelve también el conteo real de accesos públicos (éxitos y
    fallos) para la vista administrativa.
    """

    comercio = _esquema("DB_COMERCIO")

    condiciones = []
    parametros = []

    if estado:
        estados_validos = {"BORRADOR", "PUBLICADO"}
        if estado not in estados_validos:
            raise ValueError("El estado de contenido indicado no es válido.")
        condiciones.append("ce.estado = %s")
        parametros.append(estado)

    where_sql = (
        ("WHERE " + " AND ".join(condiciones))
        if condiciones
        else ""
    )

    consulta = f"""
        SELECT
            ce.id AS contenido_id,
            ce.titulo,
            ce.slug,
            ce.resumen,
            ce.tipo,
            ce.estado,
            ce.orden,
            ce.imagen_ruta,
            ce.autor_usuario_id,
            ce.publicado_en,
            ce.creado_en,
            ce.actualizado_en,
            (SELECT COUNT(*)
             FROM {comercio}.contenido_fuentes AS cf
             WHERE cf.contenido_id = ce.id) AS total_fuentes,
            (SELECT COUNT(*)
             FROM {comercio}.contenido_variantes AS cv
             WHERE cv.contenido_id = ce.id) AS total_variantes,
            (SELECT COUNT(*)
             FROM {comercio}.accesos_contenido AS ac
             WHERE ac.contenido_id = ce.id
               AND ac.resultado = 'EXITO') AS accesos_exitosos
        FROM {comercio}.contenido_educativo AS ce
        {where_sql}
        ORDER BY
            ce.estado DESC,
            COALESCE(ce.orden, 99999) ASC,
            ce.creado_en DESC
    """

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(parametros))
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_contenido(contenido_id):
    """Devuelve un contenido educativo con fuentes y variantes ligadas."""

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
            ce.estado,
            ce.autor_usuario_id,
            ce.orden,
            ce.publicado_en,
            ce.creado_en,
            ce.actualizado_en,
            (SELECT COUNT(*)
             FROM {comercio}.accesos_contenido AS ac
             WHERE ac.contenido_id = ce.id) AS total_accesos
        FROM {comercio}.contenido_educativo AS ce
        WHERE ce.id = %s
        LIMIT 1
    """

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, (contenido_id,))
            fila = cursor.fetchone()
            if not fila:
                return None
            cursor.execute(
                f"""
                SELECT id, nombre, referencia, url, nota, creado_en
                FROM {comercio}.contenido_fuentes
                WHERE contenido_id = %s
                ORDER BY creado_en ASC
                """,
                (contenido_id,),
            )
            fuentes = cursor.fetchall()
            cursor.execute(
                f"""
                SELECT
                    cv.id AS vinculo_id,
                    cv.variante_id,
                    v.sku,
                    v.nombre_comercial,
                    COALESCE(s.nombre, 'Sin sabor') AS sabor,
                    COALESCE(p.nombre, 'Sin presentación') AS presentacion
                FROM {comercio}.contenido_variantes AS cv
                LEFT JOIN {comercio}.variantes AS v
                    ON v.id = cv.variante_id
                LEFT JOIN {comercio}.sabores AS s
                    ON s.id = v.sabor_id
                LEFT JOIN {comercio}.presentaciones AS p
                    ON p.id = v.presentacion_id
                WHERE cv.contenido_id = %s
                ORDER BY v.nombre_comercial ASC
                """,
                (contenido_id,),
            )
            variantes = cursor.fetchall()
            cursor.execute(
                f"""
                SELECT id AS catalogo_variante_id, sku, nombre_comercial
                FROM {comercio}.variantes
                WHERE estado = 'ACTIVO'
                ORDER BY nombre_comercial ASC
                """,
            )
            catalogo = cursor.fetchall()
            return {
                **fila,
                "fuentes": fuentes,
                "variantes": variantes,
                "catalogo_variantes": catalogo,
            }
    finally:
        conexion.close()


def listar_catalogo_variantes():
    """Lista las variantes ACTIVAS reales del catálogo para vincular."""

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DISTINCT
                    v.id AS variante_id,
                    v.sku,
                    v.nombre_comercial
                FROM {comercio}.variantes AS v
                WHERE v.estado = 'ACTIVO'
                ORDER BY v.nombre_comercial ASC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


# ============================================================
# ESCRITURAS (UNA transacción por operación)
# ============================================================

def crear_contenido(
    titulo,
    slug,
    resumen,
    contenido,
    tipo,
    imagen_ruta,
    estado,
    autor_usuario_id,
    orden,
):
    """Crea un contenido educativo y lo persiste de inmediato."""

    comercio = _esquema("DB_COMERCIO")

    contenido_id = str(uuid.uuid4())
    publicado_en = None
    if estado == "PUBLICADO":
        publicado_en = "NOW()"

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO {comercio}.contenido_educativo (
                        id, titulo, slug, resumen, contenido, tipo,
                        imagen_ruta, estado, autor_usuario_id, orden,
                        publicado_en, creado_en, actualizado_en
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        {publicado_en or "NULL"}, NOW(), NOW()
                    )
                    """,
                    (
                        contenido_id,
                        titulo,
                        slug,
                        resumen,
                        contenido,
                        tipo,
                        imagen_ruta,
                        estado,
                        autor_usuario_id,
                        orden,
                    ),
                )
            except Exception as error:
                if "slug" in str(error).lower() or "duplicate" in str(error).lower():
                    raise ValueError(
                        "Ya existe un contenido con ese slug."
                    ) from error
                raise

            conexion.commit()

            return {
                "ok": True,
                "contenido_id": contenido_id,
                "esta_publicado": estado == "PUBLICADO",
            }
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def _fragmento_publicado_en(estado, publicado_en_actual):
    """
    Decide cómo escribir el sello ``publicado_en`` en el UPDATE.

    - Primera publicación: MySQL calcula la fecha (NOW()).
    - Ya publicada o reeditada a BORRADOR: se conserva el sello
      existente como parámetro ``%s`` (nunca se interpola en SQL).

    Devuelve un dict con la clave ``fragmento`` que identifica
    el fragmento SQL seguro a utilizar.
    """

    if estado == "PUBLICADO" and not publicado_en_actual:
        return {"fragmento": "NOW()"}

    return {"fragmento": "%s"}


def actualizar_contenido(
    contenido_id,
    titulo,
    slug,
    resumen,
    contenido,
    tipo,
    imagen_ruta,
    estado,
    orden,
):
    """
    Actualiza un contenido existente.

    Si el estado cambia a PUBLICADO se sella ``publicado_en`` con la
    fecha actual (una sola vez); si vuelve a BORRADOR se conserva el
    sello histórico, pero el borrador no es visible públicamente.
    """

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            cursor.execute(
                f"""
                SELECT id, estado, publicado_en
                FROM {comercio}.contenido_educativo
                WHERE id = %s
                LIMIT 1
                """,
                (contenido_id,),
            )

            actual = cursor.fetchone()

            if not actual:
                raise ValueError("El contenido indicado no existe.")

            fragmento_publicado = _fragmento_publicado_en(
                estado,
                actual["publicado_en"],
            )

            parametros = [
                titulo,
                slug,
                resumen,
                contenido,
                tipo,
                imagen_ruta,
                estado,
                orden,
            ]

            if fragmento_publicado["fragmento"] == "%s":
                # Conserva el sello real como parámetro. NUNCA se
                # interpola un datetime directamente en el SQL.
                parametros.append(actual["publicado_en"])

            parametros.append(contenido_id)

            try:
                cursor.execute(
                    f"""
                    UPDATE {comercio}.contenido_educativo
                    SET
                        titulo = %s,
                        slug = %s,
                        resumen = %s,
                        contenido = %s,
                        tipo = %s,
                        imagen_ruta = %s,
                        estado = %s,
                        orden = %s,
                        publicado_en = {fragmento_publicado["fragmento"]},
                        actualizado_en = NOW()
                    WHERE id = %s
                    """,
                    tuple(parametros),
                )
            except Exception as error:
                if "slug" in str(error).lower() or "duplicate" in str(error).lower():
                    raise ValueError(
                        "Ya existe un contenido con ese slug."
                    ) from error
                raise

            conexion.commit()

            return {"ok": True, "contenido_id": contenido_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def eliminar_contenido(contenido_id):
    """
    Elimina un contenido educativo y sus dependencias (fuentes y
    vínculos con variantes) por cascada real de la BD.

    NUNCA elimina registros de accesos_contenido (conserva la
    evidencia de auditoría; esos registros no tienen FK de borrado).
    """

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                DELETE FROM {comercio}.contenido_educativo
                WHERE id = %s
                """,
                (contenido_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError("El contenido indicado no existe.")
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def agregar_fuente(contenido_id, nombre, referencia=None, url=None, nota=None):
    """Agrega una fuente de respaldo a un contenido educativo."""

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM {comercio}.contenido_educativo
                WHERE id = %s
                """,
                (contenido_id,),
            )
            if cursor.fetchone()["total"] == 0:
                raise ValueError("El contenido indicado no existe.")

            cursor.execute(
                f"""
                INSERT INTO {comercio}.contenido_fuentes (
                    id, contenido_id, nombre, referencia, url, nota, creado_en
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    str(uuid.uuid4()),
                    contenido_id,
                    nombre,
                    referencia or None,
                    url or None,
                    nota or None,
                ),
            )
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def eliminar_fuente(contenido_id, fuente_id):
    """Elimina una fuente de respaldo de un contenido."""

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                DELETE FROM {comercio}.contenido_fuentes
                WHERE id = %s AND contenido_id = %s
                """,
                (fuente_id, contenido_id),
            )
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def vincular_variante(contenido_id, variante_id):
    """Relaciona un contenido con una variante REAL del catálogo."""

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM {comercio}.variantes AS v
                WHERE v.id = %s AND v.estado = 'ACTIVO'
                """,
                (variante_id,),
            )

            if cursor.fetchone()["total"] == 0:
                raise ValueError(
                    "La variante indicada no existe o está inactiva."
                )

            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM {comercio}.contenido_variantes
                WHERE contenido_id = %s AND variante_id = %s
                """,
                (contenido_id, variante_id),
            )

            if cursor.fetchone()["total"] > 0:
                raise ValueError(
                    "Esa variante ya está vinculada a este contenido."
                )

            cursor.execute(
                f"""
                INSERT INTO {comercio}.contenido_variantes (
                    id, contenido_id, variante_id, creado_en
                )
                VALUES (%s, %s, %s, NOW())
                """,
                (
                    str(uuid.uuid4()),
                    contenido_id,
                    variante_id,
                ),
            )
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def eliminar_variante_vinculo(contenido_id, vinculo_id):
    """Elimina el vínculo entre un contenido y una variante."""

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                DELETE FROM {comercio}.contenido_variantes
                WHERE id = %s AND contenido_id = %s
                """,
                (vinculo_id, contenido_id),
            )
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()