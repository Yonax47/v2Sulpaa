"""Acceso a datos del catálogo comercial de SULPAA V2.

Este archivo trabaja con las tablas REALES del esquema de Comercio:

``categorias``, ``sabores``, ``presentaciones``, ``productos``,
``variantes``, ``articulos_venta``, ``precios``, ``imagenes_catalogo``,
``packs``, ``pack_componentes``, ``pack_reglas`` y
``pack_variantes_permitidas``.

Convenciones:

- Los nombres de tablas y columnas son constantes internas.
- Todos los valores llegados desde formularios viajan como parámetros.
- Las escrituras usan una conexión independiente y una transacción por
  operación. Nunca se elimina físicamente un producto, variante, pack o
  precio con historia comercial; se cambia su estado.
- Los packs NO tienen stock propio: solo se leen componentes y variantes.
"""

import uuid
from datetime import datetime, timedelta

from app.config.database import (
    conexion_comercio,
    crear_conexion,
    nombre_esquema,
)
from app.admin.catalogo.validaciones import rangos_se_superponen


# ============================================================
# CONEXIONES
# ============================================================

def _esquema():
    """Esquema de Comercio resuelto por la configuración central."""

    return nombre_esquema("DB_COMERCIO")


def _lectura():
    """Conexión reutilizada dentro de la solicitud para consultas."""

    return conexion_comercio()


def _escritura():
    """Conexión independiente que controla su propio commit/rollback."""

    return crear_conexion(_esquema(), reutilizar=False)


def _es_duplicado(error):
    """Reconoce una clave única repetida sin mostrar detalles internos."""

    texto = str(error).lower()
    return "duplicate" in texto or "1062" in texto


def _existe_id(cursor, esquema, tabla, registro_id):
    """Distingue un registro inexistente de una actualización sin cambios.

    MariaDB devuelve ``rowcount = 0`` cuando se vuelven a guardar exactamente
    los mismos valores. Las tablas admitidas son constantes internas para que
    el nombre nunca proceda de una solicitud HTTP.
    """

    permitidas = {
        "categorias", "sabores", "presentaciones", "productos",
        "variantes", "imagenes_catalogo", "packs",
    }
    if tabla not in permitidas:
        raise ValueError("La tabla indicada no es válida.")
    cursor.execute(
        f"SELECT id FROM {esquema}.{tabla} WHERE id = %s LIMIT 1",
        (registro_id,),
    )
    return cursor.fetchone() is not None


# ============================================================
# CATÁLOGOS SIMPLES
# ============================================================

_SIMPLES = {
    "categorias": {
        "tabla": "categorias",
        "columnas": ("nombre", "slug", "descripcion", "orden", "estado"),
        "orden": "orden ASC, nombre ASC",
    },
    "sabores": {
        "tabla": "sabores",
        "columnas": ("nombre", "descripcion", "estado"),
        "orden": "nombre ASC",
    },
    "presentaciones": {
        "tabla": "presentaciones",
        "columnas": ("nombre", "tipo_unidad", "cantidad", "descripcion", "estado"),
        "orden": "nombre ASC",
    },
}


def _config_simple(recurso):
    """Devuelve la configuración interna de un catálogo simple."""

    configuracion = _SIMPLES.get(recurso)
    if not configuracion:
        raise ValueError("El tipo de catálogo indicado no es válido.")
    return configuracion


def listar_simples(recurso, estado=None, busqueda=None):
    """Lista categorías, sabores o presentaciones con filtros opcionales."""

    configuracion = _config_simple(recurso)
    esquema = _esquema()
    tabla = configuracion["tabla"]

    condiciones = []
    parametros = []

    if estado:
        condiciones.append("estado = %s")
        parametros.append(estado)

    if busqueda:
        condiciones.append("nombre LIKE %s")
        parametros.append(f"%{busqueda}%")

    where_sql = (
        "WHERE " + " AND ".join(condiciones)
        if condiciones
        else ""
    )

    consulta = f"""
        SELECT *
        FROM {esquema}.{tabla}
        {where_sql}
        ORDER BY {configuracion['orden']}
    """

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(parametros))
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_simple(recurso, registro_id):
    """Devuelve una fila de un catálogo simple por su identificador."""

    configuracion = _config_simple(recurso)
    esquema = _esquema()
    tabla = configuracion["tabla"]

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM {esquema}.{tabla}
                WHERE id = %s
                LIMIT 1
                """,
                (registro_id,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def crear_simple(recurso, datos):
    """Crea una categoría, sabor o presentación."""

    configuracion = _config_simple(recurso)
    esquema = _esquema()
    tabla = configuracion["tabla"]
    columnas = [
        columna
        for columna in configuracion["columnas"]
        if columna in datos
    ]

    if not columnas:
        raise ValueError("No hay datos para guardar.")

    marcadores = ", ".join(["%s"] * len(columnas))
    lista_columnas = ", ".join(columnas)

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO {esquema}.{tabla} ({lista_columnas})
                    VALUES ({marcadores})
                    """,
                    tuple(datos[columna] for columna in columnas),
                )
            except Exception as error:
                if _es_duplicado(error):
                    raise ValueError(
                        "Ya existe un registro con ese nombre o slug."
                    ) from error
                raise
            nuevo_id = cursor.lastrowid
            conexion.commit()
            return {"ok": True, "id": nuevo_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def actualizar_simple(recurso, registro_id, datos):
    """Actualiza una categoría, sabor o presentación existente."""

    configuracion = _config_simple(recurso)
    esquema = _esquema()
    tabla = configuracion["tabla"]
    columnas = [
        columna
        for columna in configuracion["columnas"]
        if columna in datos
    ]

    if not columnas:
        raise ValueError("No hay datos para guardar.")

    asignaciones = ", ".join(f"{columna} = %s" for columna in columnas)
    parametros = [datos[columna] for columna in columnas]
    parametros.append(registro_id)

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    UPDATE {esquema}.{tabla}
                    SET {asignaciones}
                    WHERE id = %s
                    """,
                    tuple(parametros),
                )
            except Exception as error:
                if _es_duplicado(error):
                    raise ValueError(
                        "Ya existe un registro con ese nombre o slug."
                    ) from error
                raise

            if cursor.rowcount == 0 and not _existe_id(
                cursor, esquema, tabla, registro_id
            ):
                raise ValueError("El registro indicado no existe.")

            conexion.commit()
            return {"ok": True, "id": registro_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def referencias_activas_simple(recurso, registro_id):
    """Cuenta registros ACTIVOS que dependen de un catálogo simple.

    Se usa para impedir que una categoría, sabor o presentación quede
    inactiva mientras todavía publica productos o variantes.
    """

    esquema = _esquema()

    if recurso == "categorias":
        consulta = f"""
            SELECT COUNT(*) AS total
            FROM {esquema}.productos
            WHERE categoria_id = %s AND estado = 'ACTIVO'
        """
    elif recurso == "sabores":
        consulta = f"""
            SELECT COUNT(*) AS total
            FROM {esquema}.variantes
            WHERE sabor_id = %s AND estado = 'ACTIVO'
        """
    elif recurso == "presentaciones":
        consulta = f"""
            SELECT COUNT(*) AS total
            FROM {esquema}.variantes
            WHERE presentacion_id = %s AND estado = 'ACTIVO'
        """
    else:
        raise ValueError("El tipo de catálogo indicado no es válido.")

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, (registro_id,))
            fila = cursor.fetchone()
            return int((fila or {}).get("total") or 0)
    finally:
        conexion.close()


# ============================================================
# PRODUCTOS
# ============================================================

def listar_productos(estado=None, busqueda=None, categoria_id=None):
    """Lista productos con su categoría y conteo real de variantes."""

    esquema = _esquema()
    condiciones = []
    parametros = []

    if estado:
        condiciones.append("p.estado = %s")
        parametros.append(estado)

    if busqueda:
        condiciones.append("(p.nombre LIKE %s OR p.slug LIKE %s)")
        parametros.extend([f"%{busqueda}%", f"%{busqueda}%"])

    if categoria_id:
        condiciones.append("p.categoria_id = %s")
        parametros.append(categoria_id)

    where_sql = (
        "WHERE " + " AND ".join(condiciones)
        if condiciones
        else ""
    )

    consulta = f"""
        SELECT
            p.id AS producto_id,
            p.categoria_id,
            c.nombre AS categoria,
            c.estado AS categoria_estado,
            p.nombre,
            p.slug,
            p.descripcion,
            p.estado,
            p.creado_en,
            p.actualizado_en,
            (SELECT COUNT(*)
             FROM {esquema}.variantes AS v
             WHERE v.producto_id = p.id) AS total_variantes,
            (SELECT COUNT(*)
             FROM {esquema}.variantes AS v
             WHERE v.producto_id = p.id
               AND v.estado = 'ACTIVO') AS variantes_activas,
            (SELECT COUNT(*)
             FROM {esquema}.imagenes_catalogo AS ic
             WHERE ic.producto_id = p.id
               AND ic.estado = 'ACTIVO') AS total_imagenes
        FROM {esquema}.productos AS p
        INNER JOIN {esquema}.categorias AS c
            ON c.id = p.categoria_id
        {where_sql}
        ORDER BY p.nombre ASC
    """

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(parametros))
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_producto(producto_id):
    """Devuelve un producto con sus variantes e imágenes."""

    esquema = _esquema()

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    p.id AS producto_id,
                    p.categoria_id,
                    c.nombre AS categoria,
                    c.estado AS categoria_estado,
                    p.nombre,
                    p.slug,
                    p.descripcion,
                    p.estado,
                    p.creado_en,
                    p.actualizado_en
                FROM {esquema}.productos AS p
                INNER JOIN {esquema}.categorias AS c
                    ON c.id = p.categoria_id
                WHERE p.id = %s
                LIMIT 1
                """,
                (producto_id,),
            )
            producto = cursor.fetchone()

            if not producto:
                return None

            cursor.execute(
                f"""
                SELECT
                    v.id AS variante_id,
                    v.sku,
                    v.nombre_comercial,
                    v.estado,
                    COALESCE(s.nombre, 'Sin sabor') AS sabor,
                    p.nombre AS presentacion
                FROM {esquema}.variantes AS v
                LEFT JOIN {esquema}.sabores AS s
                    ON s.id = v.sabor_id
                INNER JOIN {esquema}.presentaciones AS p
                    ON p.id = v.presentacion_id
                WHERE v.producto_id = %s
                ORDER BY v.nombre_comercial ASC
                """,
                (producto_id,),
            )
            variantes = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT *
                FROM {esquema}.imagenes_catalogo
                WHERE producto_id = %s
                ORDER BY es_principal DESC, orden ASC, creado_en ASC
                """,
                (producto_id,),
            )
            imagenes = cursor.fetchall()

            return {
                **producto,
                "variantes": variantes,
                "imagenes": imagenes,
            }
    finally:
        conexion.close()


def crear_producto(nombre, slug, categoria_id, descripcion, estado):
    """Crea un producto nuevo con un UUID real."""

    esquema = _esquema()
    producto_id = str(uuid.uuid4())

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO {esquema}.productos (
                        id, categoria_id, nombre, slug, descripcion,
                        estado, creado_en, actualizado_en
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                    """,
                    (
                        producto_id,
                        categoria_id,
                        nombre,
                        slug,
                        descripcion,
                        estado,
                    ),
                )
            except Exception as error:
                if _es_duplicado(error):
                    raise ValueError(
                        "Ya existe un producto con ese slug."
                    ) from error
                raise

            conexion.commit()
            return {"ok": True, "producto_id": producto_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def actualizar_producto(
    producto_id,
    nombre,
    slug,
    categoria_id,
    descripcion,
    estado,
):
    """Actualiza los datos comerciales de un producto."""

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    UPDATE {esquema}.productos
                    SET
                        categoria_id = %s,
                        nombre = %s,
                        slug = %s,
                        descripcion = %s,
                        estado = %s,
                        actualizado_en = NOW()
                    WHERE id = %s
                    """,
                    (
                        categoria_id,
                        nombre,
                        slug,
                        descripcion,
                        estado,
                        producto_id,
                    ),
                )
            except Exception as error:
                if _es_duplicado(error):
                    raise ValueError(
                        "Ya existe un producto con ese slug."
                    ) from error
                raise

            if cursor.rowcount == 0 and not _existe_id(
                cursor, esquema, "productos", producto_id
            ):
                raise ValueError("El producto indicado no existe.")

            conexion.commit()
            return {"ok": True, "producto_id": producto_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def cambiar_estado_producto(producto_id, estado):
    """Activa o desactiva lógicamente un producto."""

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {esquema}.productos
                SET estado = %s, actualizado_en = NOW()
                WHERE id = %s
                """,
                (estado, producto_id),
            )
            if cursor.rowcount == 0 and not _existe_id(
                cursor, esquema, "productos", producto_id
            ):
                raise ValueError("El producto indicado no existe.")
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def producto_tiene_variantes_activas(producto_id):
    """Indica si un producto todavía tiene variantes activas."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM {esquema}.variantes
                WHERE producto_id = %s AND estado = 'ACTIVO'
                """,
                (producto_id,),
            )
            return int((cursor.fetchone() or {}).get("total") or 0)
    finally:
        conexion.close()


def slug_disponible(tabla, slug, excluir_id=None):
    """Comprueba si un slug ya existe en la tabla indicada.

    ``tabla`` solo puede ser una de las tablas con slug único conocidas.
    """

    if tabla not in ("categorias", "productos", "packs"):
        raise ValueError("La tabla indicada no admite slug.")

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            if excluir_id:
                cursor.execute(
                    f"""
                    SELECT id
                    FROM {esquema}.{tabla}
                    WHERE slug = %s AND id <> %s
                    LIMIT 1
                    """,
                    (slug, excluir_id),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT id
                    FROM {esquema}.{tabla}
                    WHERE slug = %s
                    LIMIT 1
                    """,
                    (slug,),
                )
            return cursor.fetchone() is None
    finally:
        conexion.close()


# ============================================================
# VARIANTES
# ============================================================

def _sql_precio_actual(alias_articulo="av"):
    """Subconsulta interna del precio normal vigente."""

    return f"""
        (SELECT pr.monto
         FROM {_esquema()}.precios AS pr
         WHERE pr.articulo_venta_id = {alias_articulo}.id
           AND pr.estado = 'ACTIVO'
           AND pr.tipo_precio_id = 1
           AND pr.vigente_desde <= NOW()
           AND (pr.vigente_hasta IS NULL OR pr.vigente_hasta > NOW())
         ORDER BY pr.vigente_desde DESC
         LIMIT 1)
    """


def _sql_imagen_actual():
    """Subconsulta interna de la primera imagen activa de una variante."""

    esquema = _esquema()
    return f"""
        (SELECT ic.ruta
         FROM {esquema}.imagenes_catalogo AS ic
         WHERE ic.variante_id = v.id
           AND ic.estado = 'ACTIVO'
         ORDER BY ic.es_principal DESC, ic.orden ASC, ic.creado_en ASC
         LIMIT 1)
    """


def listar_variantes(estado=None, busqueda=None, producto_id=None):
    """Lista variantes con producto, sabor, presentación, precio e imagen."""

    esquema = _esquema()
    condiciones = []
    parametros = []

    if estado:
        condiciones.append("v.estado = %s")
        parametros.append(estado)

    if busqueda:
        condiciones.append(
            "(v.sku LIKE %s OR v.nombre_comercial LIKE %s)"
        )
        parametros.extend([f"%{busqueda}%", f"%{busqueda}%"])

    if producto_id:
        condiciones.append("v.producto_id = %s")
        parametros.append(producto_id)

    where_sql = (
        "WHERE " + " AND ".join(condiciones)
        if condiciones
        else ""
    )

    precio_actual = _sql_precio_actual("av")
    imagen_actual = _sql_imagen_actual()

    consulta = f"""
        SELECT
            v.id AS variante_id,
            v.producto_id,
            p.nombre AS producto,
            p.estado AS producto_estado,
            v.sabor_id,
            COALESCE(s.nombre, 'Sin sabor') AS sabor,
            COALESCE(s.estado, 'INACTIVO') AS sabor_estado,
            v.presentacion_id,
            pr.nombre AS presentacion,
            pr.estado AS presentacion_estado,
            v.sku,
            v.nombre_comercial,
            v.peso_gramos,
            v.largo_cm,
            v.ancho_cm,
            v.alto_cm,
            v.estado,
            v.creado_en,
            v.actualizado_en,
            av.id AS articulo_venta_id,
            av.estado AS articulo_estado,
            {precio_actual} AS precio_actual,
            {imagen_actual} AS imagen_ruta
        FROM {esquema}.variantes AS v
        INNER JOIN {esquema}.productos AS p
            ON p.id = v.producto_id
        LEFT JOIN {esquema}.sabores AS s
            ON s.id = v.sabor_id
        INNER JOIN {esquema}.presentaciones AS pr
            ON pr.id = v.presentacion_id
        LEFT JOIN {esquema}.articulos_venta AS av
            ON av.variante_id = v.id
        {where_sql}
        ORDER BY p.nombre ASC, v.nombre_comercial ASC
    """

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(parametros))
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_variante(variante_id):
    """Devuelve una variante, sus precios e imágenes."""

    esquema = _esquema()
    precio_actual = _sql_precio_actual("av")
    imagen_actual = _sql_imagen_actual()

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    v.id AS variante_id,
                    v.producto_id,
                    p.nombre AS producto,
                    p.estado AS producto_estado,
                    v.sabor_id,
                    COALESCE(s.nombre, 'Sin sabor') AS sabor,
                    COALESCE(s.estado, 'INACTIVO') AS sabor_estado,
                    v.presentacion_id,
                    pr.nombre AS presentacion,
                    pr.estado AS presentacion_estado,
                    v.sku,
                    v.nombre_comercial,
                    v.peso_gramos,
                    v.largo_cm,
                    v.ancho_cm,
                    v.alto_cm,
                    v.estado,
                    v.creado_en,
                    v.actualizado_en,
                    av.id AS articulo_venta_id,
                    av.estado AS articulo_estado,
                    {precio_actual} AS precio_actual,
                    {imagen_actual} AS imagen_ruta
                FROM {esquema}.variantes AS v
                INNER JOIN {esquema}.productos AS p
                    ON p.id = v.producto_id
                LEFT JOIN {esquema}.sabores AS s
                    ON s.id = v.sabor_id
                INNER JOIN {esquema}.presentaciones AS pr
                    ON pr.id = v.presentacion_id
                LEFT JOIN {esquema}.articulos_venta AS av
                    ON av.variante_id = v.id
                WHERE v.id = %s
                LIMIT 1
                """,
                (variante_id,),
            )
            variante = cursor.fetchone()

            if not variante:
                return None

            cursor.execute(
                f"""
                SELECT
                    ic.*
                FROM {esquema}.imagenes_catalogo AS ic
                WHERE ic.variante_id = %s
                ORDER BY ic.es_principal DESC, ic.orden ASC, ic.creado_en ASC
                """,
                (variante_id,),
            )
            imagenes = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT
                    pr.id AS precio_id,
                    pr.articulo_venta_id,
                    pr.tipo_precio_id,
                    tp.codigo AS tipo_codigo,
                    tp.nombre AS tipo_nombre,
                    pr.monto,
                    pr.moneda,
                    pr.vigente_desde,
                    pr.vigente_hasta,
                    pr.creado_por_usuario_id,
                    pr.estado,
                    pr.creado_en
                FROM {esquema}.precios AS pr
                INNER JOIN {esquema}.tipos_precio AS tp
                    ON tp.id = pr.tipo_precio_id
                WHERE pr.articulo_venta_id = %s
                ORDER BY pr.vigente_desde DESC, pr.creado_en DESC
                """,
                (variante.get("articulo_venta_id"),),
            )
            precios = cursor.fetchall()

            return {
                **variante,
                "imagenes": imagenes,
                "precios": precios,
            }
    finally:
        conexion.close()


def _asegurar_articulo(cursor, esquema, variante_id, estado):
    """Crea el artículo de venta de una variante cuando todavía no existe."""

    cursor.execute(
        f"""
        SELECT id
        FROM {esquema}.articulos_venta
        WHERE variante_id = %s
        LIMIT 1
        """,
        (variante_id,),
    )
    existente = cursor.fetchone()

    if existente:
        cursor.execute(
            f"""
            UPDATE {esquema}.articulos_venta
            SET estado = %s
            WHERE id = %s
            """,
            (estado, existente["id"]),
        )
        return existente["id"]

    articulo_id = str(uuid.uuid4())
    cursor.execute(
        f"""
        INSERT INTO {esquema}.articulos_venta (
            id, tipo, variante_id, pack_id, estado, creado_en
        )
        VALUES (%s, 'VARIANTE', %s, NULL, %s, NOW())
        """,
        (articulo_id, variante_id, estado),
    )
    return articulo_id


def _insertar_precio(
    cursor,
    esquema,
    articulo_id,
    tipo_precio_id,
    monto,
    moneda,
    vigente_desde,
    vigente_hasta,
    actor_id,
):
    """Inserta un precio dentro de una transacción ya abierta."""

    precio_id = str(uuid.uuid4())
    cursor.execute(
        f"""
        INSERT INTO {esquema}.precios (
            id, articulo_venta_id, tipo_precio_id, monto, moneda,
            vigente_desde, vigente_hasta, creado_por_usuario_id,
            estado, creado_en
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVO', NOW())
        """,
        (
            precio_id,
            articulo_id,
            tipo_precio_id,
            monto,
            moneda,
            vigente_desde,
            vigente_hasta,
            actor_id,
        ),
    )
    return precio_id


def crear_variante(
    producto_id,
    sabor_id,
    presentacion_id,
    sku,
    nombre_comercial,
    peso_gramos,
    largo_cm,
    ancho_cm,
    alto_cm,
    estado,
    actor_id=None,
    monto_inicial=None,
    moneda="PEN",
    tipo_precio_id=1,
):
    """Crea una variante y su artículo de venta en una sola transacción.

    Si se recibe ``monto_inicial`` también se crea el primer precio
    vigente. La variante no se publica sin artículo, y el artículo no
    existe sin variante: ambos se guardan juntos o no se guarda nada.
    """

    esquema = _esquema()
    variante_id = str(uuid.uuid4())

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO {esquema}.variantes (
                        id, producto_id, sabor_id, presentacion_id, sku,
                        nombre_comercial, peso_gramos, largo_cm, ancho_cm,
                        alto_cm, estado, creado_en, actualizado_en
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        NOW(), NOW()
                    )
                    """,
                    (
                        variante_id,
                        producto_id,
                        sabor_id,
                        presentacion_id,
                        sku,
                        nombre_comercial,
                        peso_gramos,
                        largo_cm,
                        ancho_cm,
                        alto_cm,
                        estado,
                    ),
                )
            except Exception as error:
                if _es_duplicado(error):
                    raise ValueError(
                        "Ya existe una variante con ese SKU."
                    ) from error
                raise

            articulo_id = _asegurar_articulo(
                cursor,
                esquema,
                variante_id,
                estado,
            )

            precio_id = None
            if monto_inicial is not None:
                precio_id = _insertar_precio(
                    cursor,
                    esquema,
                    articulo_id,
                    tipo_precio_id,
                    monto_inicial,
                    moneda,
                    datetime.now().replace(microsecond=0),
                    None,
                    actor_id,
                )

            conexion.commit()
            return {
                "ok": True,
                "variante_id": variante_id,
                "articulo_venta_id": articulo_id,
                "precio_id": precio_id,
            }
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def actualizar_variante(
    variante_id,
    producto_id,
    sabor_id,
    presentacion_id,
    sku,
    nombre_comercial,
    peso_gramos,
    largo_cm,
    ancho_cm,
    alto_cm,
    estado,
):
    """Actualiza una variante y sincroniza su artículo de venta."""

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    UPDATE {esquema}.variantes
                    SET
                        producto_id = %s,
                        sabor_id = %s,
                        presentacion_id = %s,
                        sku = %s,
                        nombre_comercial = %s,
                        peso_gramos = %s,
                        largo_cm = %s,
                        ancho_cm = %s,
                        alto_cm = %s,
                        estado = %s,
                        actualizado_en = NOW()
                    WHERE id = %s
                    """,
                    (
                        producto_id,
                        sabor_id,
                        presentacion_id,
                        sku,
                        nombre_comercial,
                        peso_gramos,
                        largo_cm,
                        ancho_cm,
                        alto_cm,
                        estado,
                        variante_id,
                    ),
                )
            except Exception as error:
                if _es_duplicado(error):
                    raise ValueError(
                        "Ya existe una variante con ese SKU."
                    ) from error
                raise

            if cursor.rowcount == 0 and not _existe_id(
                cursor, esquema, "variantes", variante_id
            ):
                raise ValueError("La variante indicada no existe.")

            _asegurar_articulo(cursor, esquema, variante_id, estado)

            conexion.commit()
            return {"ok": True, "variante_id": variante_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def cambiar_estado_variante(variante_id, estado):
    """Activa o desactiva una variante y su artículo de venta."""

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {esquema}.variantes
                SET estado = %s, actualizado_en = NOW()
                WHERE id = %s
                """,
                (estado, variante_id),
            )
            if cursor.rowcount == 0 and not _existe_id(
                cursor, esquema, "variantes", variante_id
            ):
                raise ValueError("La variante indicada no existe.")

            _asegurar_articulo(cursor, esquema, variante_id, estado)

            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def variante_en_pack_activo(variante_id):
    """Cuenta packs activos que dependen de una variante."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM (
                    SELECT pc.pack_id
                    FROM {esquema}.pack_componentes AS pc
                    INNER JOIN {esquema}.packs AS pk
                        ON pk.id = pc.pack_id
                    WHERE pc.variante_id = %s
                      AND pk.estado = 'ACTIVO'
                    UNION
                    SELECT pvp.pack_id
                    FROM {esquema}.pack_variantes_permitidas AS pvp
                    INNER JOIN {esquema}.packs AS pk
                        ON pk.id = pvp.pack_id
                    WHERE pvp.variante_id = %s
                      AND pvp.estado = 'ACTIVO'
                      AND pk.estado = 'ACTIVO'
                ) AS dependencias
                """,
                (variante_id, variante_id),
            )
            return int((cursor.fetchone() or {}).get("total") or 0)
    finally:
        conexion.close()


def obtener_articulo_por_variante(variante_id):
    """Devuelve el artículo de venta real de una variante."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id AS articulo_venta_id, tipo, estado
                FROM {esquema}.articulos_venta
                WHERE variante_id = %s
                LIMIT 1
                """,
                (variante_id,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


# ============================================================
# PRECIOS
# ============================================================

def listar_tipos_precio():
    """Lista los tipos de precio activos."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, codigo, nombre, descripcion
                FROM {esquema}.tipos_precio
                WHERE estado = 'ACTIVO'
                ORDER BY id ASC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_tipo_precio(tipo_precio_id):
    """Devuelve un tipo de precio activo o None."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, codigo, nombre
                FROM {esquema}.tipos_precio
                WHERE id = %s AND estado = 'ACTIVO'
                LIMIT 1
                """,
                (tipo_precio_id,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def crear_precio(
    articulo_venta_id,
    tipo_precio_id,
    monto,
    moneda,
    vigente_desde,
    vigente_hasta,
    actor_id,
):
    """Crea un precio evitando vigencias superpuestas.

    Se bloquea la fila del artículo con ``FOR UPDATE`` para que dos
    personas administrando a la vez no puedan insertar rangos cruzados.
    No se modifica ningún precio anterior: se conserva la historia.
    """

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id
                FROM {esquema}.articulos_venta
                WHERE id = %s
                FOR UPDATE
                """,
                (articulo_venta_id,),
            )
            if not cursor.fetchone():
                raise ValueError("El artículo de venta no existe.")

            cursor.execute(
                f"""
                SELECT monto, vigente_desde, vigente_hasta
                FROM {esquema}.precios
                WHERE articulo_venta_id = %s
                  AND tipo_precio_id = %s
                  AND estado = 'ACTIVO'
                """,
                (articulo_venta_id, tipo_precio_id),
            )
            existentes = cursor.fetchall()

            for existente in existentes:
                if rangos_se_superponen(
                    vigente_desde,
                    vigente_hasta,
                    existente["vigente_desde"],
                    existente["vigente_hasta"],
                ):
                    raise ValueError(
                        "La vigencia se cruza con otro precio del mismo "
                        "artículo. Cierra el precio anterior o elige "
                        "otras fechas."
                    )

            precio_id = _insertar_precio(
                cursor,
                esquema,
                articulo_venta_id,
                tipo_precio_id,
                monto,
                moneda,
                vigente_desde,
                vigente_hasta,
                actor_id,
            )

            conexion.commit()
            return {"ok": True, "precio_id": precio_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def cerrar_precio(precio_id, vigente_hasta):
    """Finaliza una vigencia sin borrar el precio histórico."""

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, vigente_desde, vigente_hasta, estado
                FROM {esquema}.precios
                WHERE id = %s
                FOR UPDATE
                """,
                (precio_id,),
            )
            precio = cursor.fetchone()

            if not precio:
                raise ValueError("El precio indicado no existe.")
            if precio["estado"] != "ACTIVO":
                raise ValueError("El precio ya está inactivo.")
            if precio["vigente_hasta"] is not None:
                raise ValueError("El precio ya tiene una fecha de cierre.")
            if vigente_hasta <= precio["vigente_desde"]:
                raise ValueError(
                    "La fecha de cierre debe ser posterior al inicio."
                )

            cursor.execute(
                f"""
                UPDATE {esquema}.precios
                SET vigente_hasta = %s
                WHERE id = %s
                """,
                (vigente_hasta, precio_id),
            )
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def listar_precios_por_vencer(dias=30):
    """Lista precios vigentes que terminan dentro de los próximos días."""

    esquema = _esquema()
    limite = datetime.now() + timedelta(days=int(dias))

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    pr.id AS precio_id,
                    pr.monto,
                    pr.moneda,
                    pr.vigente_hasta,
                    v.id AS variante_id,
                    v.sku,
                    v.nombre_comercial
                FROM {esquema}.precios AS pr
                INNER JOIN {esquema}.articulos_venta AS av
                    ON av.id = pr.articulo_venta_id
                LEFT JOIN {esquema}.variantes AS v
                    ON v.id = av.variante_id
                LEFT JOIN {esquema}.packs AS pk
                    ON pk.id = av.pack_id
                WHERE pr.estado = 'ACTIVO'
                  AND pr.vigente_hasta IS NOT NULL
                  AND pr.vigente_hasta > NOW()
                  AND pr.vigente_hasta <= %s
                ORDER BY pr.vigente_hasta ASC
                """,
                (limite,),
            )
            return cursor.fetchall()
    finally:
        conexion.close()


# ============================================================
# IMÁGENES DEL CATÁLOGO
# ============================================================

def listar_imagenes(estado=None, busqueda=None, producto_id=None, variante_id=None):
    """Lista imágenes con el nombre del producto o variante asociado."""

    esquema = _esquema()
    condiciones = []
    parametros = []

    if estado:
        condiciones.append("ic.estado = %s")
        parametros.append(estado)

    if producto_id:
        condiciones.append("ic.producto_id = %s")
        parametros.append(producto_id)

    if variante_id:
        condiciones.append("ic.variante_id = %s")
        parametros.append(variante_id)

    if busqueda:
        condiciones.append(
            "(ic.ruta LIKE %s OR ic.texto_alternativo LIKE %s "
            "OR p.nombre LIKE %s OR v.nombre_comercial LIKE %s)"
        )
        patron = f"%{busqueda}%"
        parametros.extend([patron, patron, patron, patron])

    where_sql = (
        "WHERE " + " AND ".join(condiciones)
        if condiciones
        else ""
    )

    consulta = f"""
        SELECT
            ic.*,
            COALESCE(p.nombre, pv.nombre) AS producto_nombre,
            v.nombre_comercial AS variante_nombre,
            v.sku
        FROM {esquema}.imagenes_catalogo AS ic
        LEFT JOIN {esquema}.productos AS p
            ON p.id = ic.producto_id
        LEFT JOIN {esquema}.variantes AS v
            ON v.id = ic.variante_id
        LEFT JOIN {esquema}.productos AS pv
            ON pv.id = v.producto_id
        {where_sql}
        ORDER BY ic.es_principal DESC, ic.orden ASC, ic.creado_en DESC
    """

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(parametros))
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_imagen(imagen_id):
    """Devuelve una imagen del catálogo por su identificador."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM {esquema}.imagenes_catalogo
                WHERE id = %s
                LIMIT 1
                """,
                (imagen_id,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def crear_imagen(
    producto_id,
    variante_id,
    ruta,
    texto_alternativo,
    es_principal,
    orden,
    estado,
):
    """Inserta una imagen y deja una sola principal por destino."""

    esquema = _esquema()
    imagen_id = str(uuid.uuid4())

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            if es_principal:
                cursor.execute(
                    f"""
                    UPDATE {esquema}.imagenes_catalogo
                    SET es_principal = 0
                    WHERE producto_id <=> %s
                      AND variante_id <=> %s
                      AND estado = 'ACTIVO'
                    """,
                    (producto_id, variante_id),
                )

            cursor.execute(
                f"""
                INSERT INTO {esquema}.imagenes_catalogo (
                    id, producto_id, variante_id, ruta, texto_alternativo,
                    es_principal, orden, estado, creado_en
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    imagen_id,
                    producto_id,
                    variante_id,
                    ruta,
                    texto_alternativo,
                    1 if es_principal else 0,
                    orden,
                    estado,
                ),
            )
            conexion.commit()
            return {"ok": True, "imagen_id": imagen_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def actualizar_imagen(
    imagen_id,
    ruta,
    texto_alternativo,
    es_principal,
    orden,
    estado,
):
    """Actualiza una imagen existente conservando su destino."""

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT producto_id, variante_id
                FROM {esquema}.imagenes_catalogo
                WHERE id = %s
                FOR UPDATE
                """,
                (imagen_id,),
            )
            actual = cursor.fetchone()
            if not actual:
                raise ValueError("La imagen indicada no existe.")

            if es_principal:
                cursor.execute(
                    f"""
                    UPDATE {esquema}.imagenes_catalogo
                    SET es_principal = 0
                    WHERE id <> %s
                      AND producto_id <=> %s
                      AND variante_id <=> %s
                      AND estado = 'ACTIVO'
                    """,
                    (
                        imagen_id,
                        actual["producto_id"],
                        actual["variante_id"],
                    ),
                )

            cursor.execute(
                f"""
                UPDATE {esquema}.imagenes_catalogo
                SET
                    ruta = %s,
                    texto_alternativo = %s,
                    es_principal = %s,
                    orden = %s,
                    estado = %s
                WHERE id = %s
                """,
                (
                    ruta,
                    texto_alternativo,
                    1 if es_principal else 0,
                    orden,
                    estado,
                    imagen_id,
                ),
            )
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def cambiar_estado_imagen(imagen_id, estado):
    """Activa o desactiva una imagen sin borrar el archivo físico."""

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {esquema}.imagenes_catalogo
                SET estado = %s, es_principal = 0
                WHERE id = %s
                """,
                (estado, imagen_id),
            )
            if cursor.rowcount == 0 and not _existe_id(
                cursor, esquema, "imagenes_catalogo", imagen_id
            ):
                raise ValueError("La imagen indicada no existe.")
            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


# ============================================================
# PACKS
# ============================================================

def listar_packs(estado=None, busqueda=None):
    """Lista packs con su artículo, precio vigente y conteos."""

    esquema = _esquema()
    condiciones = []
    parametros = []

    if estado:
        condiciones.append("pk.estado = %s")
        parametros.append(estado)

    if busqueda:
        condiciones.append("(pk.nombre LIKE %s OR pk.slug LIKE %s)")
        parametros.extend([f"%{busqueda}%", f"%{busqueda}%"])

    where_sql = (
        "WHERE " + " AND ".join(condiciones)
        if condiciones
        else ""
    )

    precio_actual = _sql_precio_actual("av")

    consulta = f"""
        SELECT
            pk.id AS pack_id,
            pk.nombre,
            pk.slug,
            pk.tipo,
            pk.cantidad_unidades,
            pk.descripcion,
            pk.peso_embalaje_gramos,
            pk.estado,
            pk.creado_en,
            pk.actualizado_en,
            av.id AS articulo_venta_id,
            av.estado AS articulo_estado,
            {precio_actual} AS precio_actual,
            (SELECT COUNT(*)
             FROM {esquema}.pack_componentes AS pc
             WHERE pc.pack_id = pk.id) AS total_componentes,
            (SELECT COUNT(*)
             FROM {esquema}.pack_reglas AS prg
             WHERE prg.pack_id = pk.id) AS total_reglas,
            (SELECT COUNT(*)
             FROM {esquema}.pack_variantes_permitidas AS pvp
             WHERE pvp.pack_id = pk.id) AS total_permitidas
        FROM {esquema}.packs AS pk
        LEFT JOIN {esquema}.articulos_venta AS av
            ON av.pack_id = pk.id
        {where_sql}
        ORDER BY pk.nombre ASC
    """

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(parametros))
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_pack(pack_id):
    """Devuelve un pack con componentes, reglas, permitidas y precios."""

    esquema = _esquema()
    precio_actual = _sql_precio_actual("av")

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    pk.id AS pack_id,
                    pk.nombre,
                    pk.slug,
                    pk.tipo,
                    pk.cantidad_unidades,
                    pk.descripcion,
                    pk.peso_embalaje_gramos,
                    pk.estado,
                    pk.creado_en,
                    pk.actualizado_en,
                    av.id AS articulo_venta_id,
                    av.estado AS articulo_estado,
                    {precio_actual} AS precio_actual
                FROM {esquema}.packs AS pk
                LEFT JOIN {esquema}.articulos_venta AS av
                    ON av.pack_id = pk.id
                WHERE pk.id = %s
                LIMIT 1
                """,
                (pack_id,),
            )
            pack = cursor.fetchone()
            if not pack:
                return None

            cursor.execute(
                f"""
                SELECT
                    pc.id AS componente_id,
                    pc.variante_id,
                    pc.cantidad,
                    v.sku,
                    v.nombre_comercial,
                    v.estado AS variante_estado,
                    COALESCE(s.nombre, 'Sin sabor') AS sabor,
                    p.nombre AS presentacion
                FROM {esquema}.pack_componentes AS pc
                INNER JOIN {esquema}.variantes AS v
                    ON v.id = pc.variante_id
                LEFT JOIN {esquema}.sabores AS s
                    ON s.id = v.sabor_id
                INNER JOIN {esquema}.presentaciones AS p
                    ON p.id = v.presentacion_id
                WHERE pc.pack_id = %s
                ORDER BY v.nombre_comercial ASC
                """,
                (pack_id,),
            )
            componentes = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT id AS regla_id, numero_sabores, unidades_por_sabor, estado
                FROM {esquema}.pack_reglas
                WHERE pack_id = %s
                ORDER BY numero_sabores ASC, unidades_por_sabor ASC
                """,
                (pack_id,),
            )
            reglas = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT
                    pvp.id AS permitida_id,
                    pvp.variante_id,
                    pvp.estado,
                    v.sku,
                    v.nombre_comercial,
                    COALESCE(s.nombre, 'Sin sabor') AS sabor,
                    p.nombre AS presentacion
                FROM {esquema}.pack_variantes_permitidas AS pvp
                INNER JOIN {esquema}.variantes AS v
                    ON v.id = pvp.variante_id
                LEFT JOIN {esquema}.sabores AS s
                    ON s.id = v.sabor_id
                INNER JOIN {esquema}.presentaciones AS p
                    ON p.id = v.presentacion_id
                WHERE pvp.pack_id = %s
                ORDER BY v.nombre_comercial ASC
                """,
                (pack_id,),
            )
            permitidas = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT
                    pr.id AS precio_id,
                    pr.tipo_precio_id,
                    tp.nombre AS tipo_nombre,
                    pr.monto,
                    pr.moneda,
                    pr.vigente_desde,
                    pr.vigente_hasta,
                    pr.estado
                FROM {esquema}.precios AS pr
                INNER JOIN {esquema}.tipos_precio AS tp
                    ON tp.id = pr.tipo_precio_id
                WHERE pr.articulo_venta_id = %s
                ORDER BY pr.vigente_desde DESC
                """,
                (pack.get("articulo_venta_id"),),
            )
            precios = cursor.fetchall()

            return {
                **pack,
                "componentes": componentes,
                "reglas": reglas,
                "permitidas": permitidas,
                "precios": precios,
            }
    finally:
        conexion.close()


def _insertar_componentes(cursor, esquema, pack_id, componentes):
    """Inserta las filas de ``pack_componentes`` ya validadas."""

    for componente in componentes:
        cursor.execute(
            f"""
            INSERT INTO {esquema}.pack_componentes (
                id, pack_id, variante_id, cantidad
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                pack_id,
                componente["variante_id"],
                componente["cantidad"],
            ),
        )


def _insertar_reglas(cursor, esquema, pack_id, reglas):
    """Inserta las filas de ``pack_reglas`` ya validadas."""

    for regla in reglas:
        cursor.execute(
            f"""
            INSERT INTO {esquema}.pack_reglas (
                id, pack_id, numero_sabores, unidades_por_sabor, estado
            )
            VALUES (%s, %s, %s, %s, 'ACTIVO')
            """,
            (
                str(uuid.uuid4()),
                pack_id,
                regla["numero_sabores"],
                regla["unidades_por_sabor"],
            ),
        )


def _insertar_permitidas(cursor, esquema, pack_id, permitidas):
    """Inserta las variantes permitidas de un pack personalizable."""

    for variante_id in permitidas:
        cursor.execute(
            f"""
            INSERT INTO {esquema}.pack_variantes_permitidas (
                id, pack_id, variante_id, estado
            )
            VALUES (%s, %s, %s, 'ACTIVO')
            """,
            (str(uuid.uuid4()), pack_id, variante_id),
        )


def _asegurar_articulo_pack(cursor, esquema, pack_id, estado):
    """Crea o sincroniza el artículo de venta de un pack."""

    cursor.execute(
        f"""
        SELECT id
        FROM {esquema}.articulos_venta
        WHERE pack_id = %s
        LIMIT 1
        """,
        (pack_id,),
    )
    existente = cursor.fetchone()

    if existente:
        cursor.execute(
            f"""
            UPDATE {esquema}.articulos_venta
            SET estado = %s
            WHERE id = %s
            """,
            (estado, existente["id"]),
        )
        return existente["id"]

    articulo_id = str(uuid.uuid4())
    cursor.execute(
        f"""
        INSERT INTO {esquema}.articulos_venta (
            id, tipo, variante_id, pack_id, estado, creado_en
        )
        VALUES (%s, 'PACK', NULL, %s, %s, NOW())
        """,
        (articulo_id, pack_id, estado),
    )
    return articulo_id


def crear_pack(
    nombre,
    slug,
    tipo,
    cantidad_unidades,
    descripcion,
    peso_embalaje_gramos,
    estado,
    componentes,
    reglas,
    permitidas,
):
    """Crea un pack con sus componentes o reglas en una transacción."""

    esquema = _esquema()
    pack_id = str(uuid.uuid4())

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO {esquema}.packs (
                        id, nombre, slug, tipo, cantidad_unidades,
                        descripcion, peso_embalaje_gramos, estado,
                        creado_en, actualizado_en
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                    )
                    """,
                    (
                        pack_id,
                        nombre,
                        slug,
                        tipo,
                        cantidad_unidades,
                        descripcion,
                        peso_embalaje_gramos,
                        estado,
                    ),
                )
            except Exception as error:
                if _es_duplicado(error):
                    raise ValueError(
                        "Ya existe un pack con ese slug."
                    ) from error
                raise

            articulo_id = _asegurar_articulo_pack(
                cursor, esquema, pack_id, estado
            )
            _insertar_componentes(cursor, esquema, pack_id, componentes)
            _insertar_reglas(cursor, esquema, pack_id, reglas)
            _insertar_permitidas(cursor, esquema, pack_id, permitidas)

            conexion.commit()
            return {
                "ok": True,
                "pack_id": pack_id,
                "articulo_venta_id": articulo_id,
            }
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def actualizar_pack(
    pack_id,
    nombre,
    slug,
    tipo,
    cantidad_unidades,
    descripcion,
    peso_embalaje_gramos,
    estado,
    componentes,
    reglas,
    permitidas,
    reemplazar_composicion=True,
):
    """Actualiza un pack y reemplaza sus relaciones internas.

    No se toca el artículo de venta ni sus precios: la historia de precios
    y los pedidos ya confirmados se conservan.
    """

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    UPDATE {esquema}.packs
                    SET
                        nombre = %s,
                        slug = %s,
                        tipo = %s,
                        cantidad_unidades = %s,
                        descripcion = %s,
                        peso_embalaje_gramos = %s,
                        estado = %s,
                        actualizado_en = NOW()
                    WHERE id = %s
                    """,
                    (
                        nombre,
                        slug,
                        tipo,
                        cantidad_unidades,
                        descripcion,
                        peso_embalaje_gramos,
                        estado,
                        pack_id,
                    ),
                )
            except Exception as error:
                if _es_duplicado(error):
                    raise ValueError(
                        "Ya existe un pack con ese slug."
                    ) from error
                raise

            if cursor.rowcount == 0 and not _existe_id(
                cursor, esquema, "packs", pack_id
            ):
                raise ValueError("El pack indicado no existe.")

            # Las relaciones solo se reemplazan cuando el Service confirmó
            # que la composición cambió y que el pack no tiene pedidos. Una
            # edición de nombre o descripción nunca toca estas filas.
            if reemplazar_composicion:
                cursor.execute(
                    f"DELETE FROM {esquema}.pack_componentes WHERE pack_id = %s",
                    (pack_id,),
                )
                cursor.execute(
                    f"DELETE FROM {esquema}.pack_reglas WHERE pack_id = %s",
                    (pack_id,),
                )
                cursor.execute(
                    f"""
                    DELETE FROM {esquema}.pack_variantes_permitidas
                    WHERE pack_id = %s
                    """,
                    (pack_id,),
                )

                _insertar_componentes(cursor, esquema, pack_id, componentes)
                _insertar_reglas(cursor, esquema, pack_id, reglas)
                _insertar_permitidas(cursor, esquema, pack_id, permitidas)

            _asegurar_articulo_pack(cursor, esquema, pack_id, estado)

            conexion.commit()
            return {"ok": True, "pack_id": pack_id}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def cambiar_estado_pack(pack_id, estado):
    """Activa o desactiva un pack y su artículo de venta."""

    esquema = _esquema()

    conexion = _escritura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {esquema}.packs
                SET estado = %s, actualizado_en = NOW()
                WHERE id = %s
                """,
                (estado, pack_id),
            )
            if cursor.rowcount == 0 and not _existe_id(
                cursor, esquema, "packs", pack_id
            ):
                raise ValueError("El pack indicado no existe.")

            _asegurar_articulo_pack(cursor, esquema, pack_id, estado)

            conexion.commit()
            return {"ok": True}
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def obtener_articulo_por_pack(pack_id):
    """Devuelve el artículo de venta de un pack."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id AS articulo_venta_id, tipo, estado
                FROM {esquema}.articulos_venta
                WHERE pack_id = %s
                LIMIT 1
                """,
                (pack_id,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def pack_tiene_pedidos(pack_id):
    """Indica si el artículo del pack aparece en un pedido histórico."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM {esquema}.articulos_venta AS av
                INNER JOIN {esquema}.pedido_detalles AS pd
                    ON pd.articulo_venta_id = av.id
                WHERE av.pack_id = %s
                """,
                (pack_id,),
            )
            return int((cursor.fetchone() or {}).get("total") or 0) > 0
    finally:
        conexion.close()


# ============================================================
# SELECTORES
# ============================================================

def listar_categorias_activas():
    """Categorías activas para los formularios de producto."""

    return listar_simples("categorias", estado="ACTIVO")


def listar_sabores_activos():
    """Sabores activos para los formularios de variante."""

    return listar_simples("sabores", estado="ACTIVO")


def listar_presentaciones_activas():
    """Presentaciones activas para los formularios de variante."""

    return listar_simples("presentaciones", estado="ACTIVO")


def listar_variantes_selector():
    """Variantes reales con datos legibles para selectores."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    v.id AS variante_id,
                    v.sku,
                    v.nombre_comercial,
                    v.estado,
                    COALESCE(s.nombre, 'Sin sabor') AS sabor,
                    p.nombre AS presentacion
                FROM {esquema}.variantes AS v
                LEFT JOIN {esquema}.sabores AS s
                    ON s.id = v.sabor_id
                INNER JOIN {esquema}.presentaciones AS p
                    ON p.id = v.presentacion_id
                ORDER BY v.nombre_comercial ASC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def listar_productos_selector():
    """Productos reales para el selector de imágenes."""

    esquema = _esquema()
    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id AS producto_id, nombre, estado
                FROM {esquema}.productos
                ORDER BY nombre ASC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


# ============================================================
# RESUMEN DEL PANEL
# ============================================================

def contar_catalogo():
    """Cuenta los elementos principales del catálogo para el panel."""

    esquema = _esquema()

    consultas = {
        "productos": f"SELECT COUNT(*) AS total FROM {esquema}.productos",
        "productos_activos": (
            f"SELECT COUNT(*) AS total FROM {esquema}.productos "
            "WHERE estado = 'ACTIVO'"
        ),
        "categorias": f"SELECT COUNT(*) AS total FROM {esquema}.categorias",
        "sabores": f"SELECT COUNT(*) AS total FROM {esquema}.sabores",
        "presentaciones": (
            f"SELECT COUNT(*) AS total FROM {esquema}.presentaciones"
        ),
        "variantes": f"SELECT COUNT(*) AS total FROM {esquema}.variantes",
        "variantes_activas": (
            f"SELECT COUNT(*) AS total FROM {esquema}.variantes "
            "WHERE estado = 'ACTIVO'"
        ),
        "packs": f"SELECT COUNT(*) AS total FROM {esquema}.packs",
        "packs_activos": (
            f"SELECT COUNT(*) AS total FROM {esquema}.packs "
            "WHERE estado = 'ACTIVO'"
        ),
        "imagenes": (
            f"SELECT COUNT(*) AS total FROM {esquema}.imagenes_catalogo "
            "WHERE estado = 'ACTIVO'"
        ),
        "precios_vigentes": f"""
            SELECT COUNT(*) AS total
            FROM {esquema}.precios
            WHERE estado = 'ACTIVO'
              AND tipo_precio_id = 1
              AND vigente_desde <= NOW()
              AND (vigente_hasta IS NULL OR vigente_hasta > NOW())
        """,
        "variantes_sin_precio": f"""
            SELECT COUNT(*) AS total
            FROM {esquema}.variantes AS v
            INNER JOIN {esquema}.articulos_venta AS av
                ON av.variante_id = v.id
            WHERE v.estado = 'ACTIVO'
              AND av.estado = 'ACTIVO'
              AND NOT EXISTS (
                  SELECT 1
                  FROM {esquema}.precios AS pr
                  WHERE pr.articulo_venta_id = av.id
                    AND pr.estado = 'ACTIVO'
                    AND pr.tipo_precio_id = 1
                    AND pr.vigente_desde <= NOW()
                    AND (pr.vigente_hasta IS NULL OR pr.vigente_hasta > NOW())
              )
        """,
    }

    resultado = {}

    conexion = _lectura()
    try:
        with conexion.cursor() as cursor:
            for clave, consulta in consultas.items():
                cursor.execute(consulta)
                resultado[clave] = int(
                    (cursor.fetchone() or {}).get("total") or 0
                )
    finally:
        conexion.close()

    return resultado
