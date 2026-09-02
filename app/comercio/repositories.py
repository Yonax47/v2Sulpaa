"""
Acceso a datos del módulo Comercio de SULPAA V2.

Responsabilidades:

- catálogo;
- variantes;
- packs;
- precios;
- reglas comerciales;
- carrito persistente.

IMPORTANTE:

El stock NO pertenece a este repositorio.
El stock se consulta exclusivamente mediante Inventario.
"""

import uuid

from app.config.database import conexion_comercio


# ============================================================
# 1. VARIANTES INDIVIDUALES
# ============================================================

def obtener_variantes_comerciales_tienda():

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            consulta = """
                SELECT
                    v.id AS variante_id,
                    v.sku,
                    v.nombre_comercial,

                    s.id AS sabor_id,
                    s.nombre AS sabor,

                    p.id AS presentacion_id,
                    p.nombre AS presentacion,

                    av.id AS articulo_venta_id,

                    pr.monto AS precio,
                    pr.moneda

                FROM variantes AS v

                INNER JOIN sabores AS s
                    ON s.id = v.sabor_id

                INNER JOIN presentaciones AS p
                    ON p.id = v.presentacion_id

                INNER JOIN articulos_venta AS av
                    ON av.variante_id = v.id

                INNER JOIN precios AS pr
                    ON pr.articulo_venta_id = av.id

                WHERE
                    v.estado = 'ACTIVO'
                    AND s.estado = 'ACTIVO'
                    AND av.estado = 'ACTIVO'
                    AND av.tipo = 'VARIANTE'

                    AND pr.estado = 'ACTIVO'
                    AND pr.tipo_precio_id = 1

                    AND pr.vigente_desde <= NOW()

                    AND (
                        pr.vigente_hasta IS NULL
                        OR pr.vigente_hasta >= NOW()
                    )

                    AND s.nombre IN (
                        'Café',
                        'Jamaica',
                        'Limón',
                        'Kion'
                    )

                    AND p.nombre IN (
                        'Botella 1 L',
                        'Barril 30 L',
                        'Barril 50 L'
                    )

                ORDER BY
                    FIELD(
                        s.nombre,
                        'Café',
                        'Jamaica',
                        'Limón',
                        'Kion'
                    ),
                    FIELD(
                        p.nombre,
                        'Botella 1 L',
                        'Barril 30 L',
                        'Barril 50 L'
                    )
            """

            cursor.execute(consulta)

            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# 2. VARIANTES 330 ML
# ============================================================

def obtener_variantes_330ml_tienda():

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            consulta = """
                SELECT
                    v.id AS variante_id,
                    v.sku,
                    v.nombre_comercial,

                    s.id AS sabor_id,
                    s.nombre AS sabor,

                    p.id AS presentacion_id,
                    p.nombre AS presentacion

                FROM variantes AS v

                INNER JOIN sabores AS s
                    ON s.id = v.sabor_id

                INNER JOIN presentaciones AS p
                    ON p.id = v.presentacion_id

                WHERE
                    v.estado = 'ACTIVO'
                    AND s.estado = 'ACTIVO'

                    AND s.nombre IN (
                        'Café',
                        'Jamaica',
                        'Limón',
                        'Kion'
                    )

                    AND p.nombre = 'Botella 330 ml'

                ORDER BY
                    FIELD(
                        s.nombre,
                        'Café',
                        'Jamaica',
                        'Limón',
                        'Kion'
                    )
            """

            cursor.execute(consulta)

            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# 3. PACKS COMERCIALES
# ============================================================

def obtener_packs_comerciales_tienda():

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            consulta = """
                SELECT
                    pk.id AS pack_id,
                    pk.nombre AS pack_nombre,
                    pk.slug,
                    pk.tipo,
                    pk.cantidad_unidades,
                    pk.descripcion,

                    av.id AS articulo_venta_id,

                    pr.monto AS precio,
                    pr.moneda

                FROM packs AS pk

                INNER JOIN articulos_venta AS av
                    ON av.pack_id = pk.id

                INNER JOIN precios AS pr
                    ON pr.articulo_venta_id = av.id

                WHERE
                    pk.estado = 'ACTIVO'

                    AND pk.cantidad_unidades IN (
                        6,
                        12,
                        24
                    )

                    AND av.estado = 'ACTIVO'
                    AND av.tipo = 'PACK'

                    AND pr.estado = 'ACTIVO'
                    AND pr.tipo_precio_id = 1

                    AND pr.vigente_desde <= NOW()

                    AND (
                        pr.vigente_hasta IS NULL
                        OR pr.vigente_hasta >= NOW()
                    )

                ORDER BY
                    pk.cantidad_unidades,
                    pk.nombre
            """

            cursor.execute(consulta)

            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# 4. COMPONENTES DE PACKS
# ============================================================

def obtener_componentes_packs(pack_ids):

    if not pack_ids:
        return []

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            placeholders = ", ".join(
                ["%s"] * len(pack_ids)
            )

            consulta = f"""
                SELECT
                    pc.pack_id,
                    pc.variante_id,
                    pc.cantidad

                FROM pack_componentes AS pc

                WHERE
                    pc.pack_id IN ({placeholders})

                ORDER BY
                    pc.pack_id,
                    pc.variante_id
            """

            cursor.execute(
                consulta,
                tuple(pack_ids),
            )

            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# 5. REGLAS DE PACKS
# ============================================================

def obtener_reglas_packs(pack_ids):

    if not pack_ids:
        return []

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            placeholders = ", ".join(
                ["%s"] * len(pack_ids)
            )

            consulta = f"""
                SELECT
                    pr.id,
                    pr.pack_id,
                    pr.numero_sabores,
                    pr.unidades_por_sabor,
                    pr.estado

                FROM pack_reglas AS pr

                WHERE
                    pr.pack_id IN ({placeholders})
                    AND pr.estado = 'ACTIVO'

                ORDER BY
                    pr.pack_id,
                    pr.numero_sabores
            """

            cursor.execute(
                consulta,
                tuple(pack_ids),
            )

            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# 6. VARIANTES PERMITIDAS
# ============================================================

def obtener_variantes_permitidas_packs(pack_ids):

    if not pack_ids:
        return []

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            placeholders = ", ".join(
                ["%s"] * len(pack_ids)
            )

            consulta = f"""
                SELECT
                    pvp.id,
                    pvp.pack_id,
                    pvp.variante_id,
                    pvp.estado

                FROM pack_variantes_permitidas AS pvp

                WHERE
                    pvp.pack_id IN ({placeholders})
                    AND pvp.estado = 'ACTIVO'

                ORDER BY
                    pvp.pack_id,
                    pvp.variante_id
            """

            cursor.execute(
                consulta,
                tuple(pack_ids),
            )

            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# 7. ARTÍCULO DE VENTA
# ============================================================

def obtener_articulo_venta_por_id(articulo_venta_id):
    """
    Obtiene un artículo activo junto con su variante o pack.

    También devuelve su precio NORMAL actualmente vigente.
    """

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            consulta = """
                SELECT
                    av.id AS articulo_venta_id,
                    av.tipo,
                    av.variante_id,
                    av.pack_id,

                    v.nombre_comercial,
                    v.sku,

                    pk.nombre AS pack_nombre,
                    pk.tipo AS pack_tipo,
                    pk.cantidad_unidades,

                    pr.monto AS precio,
                    pr.moneda

                FROM articulos_venta AS av

                LEFT JOIN variantes AS v
                    ON v.id = av.variante_id

                LEFT JOIN packs AS pk
                    ON pk.id = av.pack_id

                INNER JOIN precios AS pr
                    ON pr.articulo_venta_id = av.id

                WHERE
                    av.id = %s
                    AND av.estado = 'ACTIVO'

                    AND pr.estado = 'ACTIVO'
                    AND pr.tipo_precio_id = 1

                    AND pr.vigente_desde <= NOW()

                    AND (
                        pr.vigente_hasta IS NULL
                        OR pr.vigente_hasta >= NOW()
                    )

                ORDER BY
                    pr.vigente_desde DESC

                LIMIT 1
            """

            cursor.execute(
                consulta,
                (articulo_venta_id,),
            )

            return cursor.fetchone()

    finally:
        conexion.close()


# ============================================================
# 8. CARRITO ACTIVO
# ============================================================

def obtener_carrito_activo_usuario(usuario_id):

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            consulta = """
                SELECT
                    id,
                    usuario_id,
                    estado,
                    creado_en,
                    actualizado_en

                FROM carritos

                WHERE
                    usuario_id = %s
                    AND estado = 'ACTIVO'

                ORDER BY
                    creado_en DESC

                LIMIT 1
            """

            cursor.execute(
                consulta,
                (usuario_id,),
            )

            return cursor.fetchone()

    finally:
        conexion.close()


# ============================================================
# 9. DETALLES DEL CARRITO
# ============================================================

def obtener_detalles_carrito_usuario(usuario_id):
    """
    Devuelve el carrito activo con sus artículos.

    El precio se obtiene nuevamente desde precios.
    No guardamos un precio inventado en frontend.
    """

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            consulta = """
                SELECT
                    cd.id AS carrito_detalle_id,
                    cd.carrito_id,
                    cd.articulo_venta_id,
                    cd.cantidad,

                    av.tipo,
                    av.variante_id,
                    av.pack_id,

                    v.nombre_comercial,
                    v.sku,

                    pk.nombre AS pack_nombre,
                    pk.tipo AS pack_tipo,
                    pk.cantidad_unidades,

                    (
                        SELECT pr.monto

                        FROM precios AS pr

                        WHERE
                            pr.articulo_venta_id = av.id
                            AND pr.estado = 'ACTIVO'
                            AND pr.tipo_precio_id = 1
                            AND pr.vigente_desde <= NOW()

                            AND (
                                pr.vigente_hasta IS NULL
                                OR pr.vigente_hasta >= NOW()
                            )

                        ORDER BY
                            pr.vigente_desde DESC

                        LIMIT 1
                    ) AS precio,

                    (
                        SELECT pr.moneda

                        FROM precios AS pr

                        WHERE
                            pr.articulo_venta_id = av.id
                            AND pr.estado = 'ACTIVO'
                            AND pr.tipo_precio_id = 1
                            AND pr.vigente_desde <= NOW()

                            AND (
                                pr.vigente_hasta IS NULL
                                OR pr.vigente_hasta >= NOW()
                            )

                        ORDER BY
                            pr.vigente_desde DESC

                        LIMIT 1
                    ) AS moneda

                FROM carritos AS c

                INNER JOIN carrito_detalles AS cd
                    ON cd.carrito_id = c.id

                INNER JOIN articulos_venta AS av
                    ON av.id = cd.articulo_venta_id

                LEFT JOIN variantes AS v
                    ON v.id = av.variante_id

                LEFT JOIN packs AS pk
                    ON pk.id = av.pack_id

                WHERE
                    c.usuario_id = %s
                    AND c.estado = 'ACTIVO'

                ORDER BY
                    cd.creado_en ASC
            """

            cursor.execute(
                consulta,
                (usuario_id,),
            )

            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# 10. COMPOSICIONES DE DETALLES
# ============================================================

def obtener_composiciones_carrito(detalle_ids):

    if not detalle_ids:
        return []

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:

            placeholders = ", ".join(
                ["%s"] * len(detalle_ids)
            )

            consulta = f"""
                SELECT
                    cc.id,
                    cc.carrito_detalle_id,
                    cc.variante_id,
                    cc.cantidad

                FROM carrito_composiciones AS cc

                WHERE
                    cc.carrito_detalle_id
                    IN ({placeholders})

                ORDER BY
                    cc.carrito_detalle_id,
                    cc.variante_id
            """

            cursor.execute(
                consulta,
                tuple(detalle_ids),
            )

            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# 11. GUARDAR PRODUCTO EN CARRITO
# ============================================================

def guardar_item_carrito(
    usuario_id,
    articulo_venta_id,
    cantidad,
    composicion=None,
    acumular=True,
):
    """
    Guarda un artículo en el carrito.

    Para productos y packs fijos:
        acumular = True

    Para packs personalizados:
        acumular = False

    Esto permite mantener composiciones distintas
    del mismo tipo de pack personalizado.
    """

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            # ------------------------------------------------
            # 1. Buscar carrito activo
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT id

                FROM carritos

                WHERE
                    usuario_id = %s
                    AND estado = 'ACTIVO'

                ORDER BY
                    creado_en DESC

                LIMIT 1

                FOR UPDATE
                """,
                (usuario_id,),
            )

            carrito = cursor.fetchone()

            # ------------------------------------------------
            # 2. Crear carrito si todavía no existe
            # ------------------------------------------------

            if carrito:

                carrito_id = carrito["id"]

            else:

                carrito_id = str(uuid.uuid4())

                cursor.execute(
                    """
                    INSERT INTO carritos (
                        id,
                        usuario_id,
                        estado
                    )
                    VALUES (
                        %s,
                        %s,
                        'ACTIVO'
                    )
                    """,
                    (
                        carrito_id,
                        usuario_id,
                    ),
                )

            # ------------------------------------------------
            # 3. Productos individuales y packs fijos
            #    pueden acumular cantidad.
            # ------------------------------------------------

            detalle_id = None

            if acumular:

                cursor.execute(
                    """
                    SELECT
                        id,
                        cantidad

                    FROM carrito_detalles

                    WHERE
                        carrito_id = %s
                        AND articulo_venta_id = %s

                    ORDER BY
                        creado_en ASC

                    LIMIT 1

                    FOR UPDATE
                    """,
                    (
                        carrito_id,
                        articulo_venta_id,
                    ),
                )

                detalle = cursor.fetchone()

                if detalle:

                    detalle_id = detalle["id"]

                    nueva_cantidad = (
                        int(detalle["cantidad"])
                        + int(cantidad)
                    )

                    cursor.execute(
                        """
                        UPDATE carrito_detalles

                        SET cantidad = %s

                        WHERE id = %s
                        """,
                        (
                            nueva_cantidad,
                            detalle_id,
                        ),
                    )

            # ------------------------------------------------
            # 4. Crear nuevo detalle
            # ------------------------------------------------

            if detalle_id is None:

                detalle_id = str(uuid.uuid4())

                cursor.execute(
                    """
                    INSERT INTO carrito_detalles (
                        id,
                        carrito_id,
                        articulo_venta_id,
                        cantidad
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        detalle_id,
                        carrito_id,
                        articulo_venta_id,
                        cantidad,
                    ),
                )

            # ------------------------------------------------
            # 5. Composición del pack personalizado
            # ------------------------------------------------

            if composicion:

                for item in composicion:

                    cursor.execute(
                        """
                        INSERT INTO carrito_composiciones (
                            id,
                            carrito_detalle_id,
                            variante_id,
                            cantidad
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        """,
                        (
                            str(uuid.uuid4()),
                            detalle_id,
                            item["variante_id"],
                            item["cantidad"],
                        ),
                    )

            conexion.commit()

            return {
                "carrito_id": carrito_id,
                "carrito_detalle_id": detalle_id,
            }

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()

# ============================================================
# 12. ACTUALIZAR CANTIDAD DE UN DETALLE DEL CARRITO
# ============================================================

def actualizar_cantidad_detalle_carrito(
    usuario_id,
    carrito_detalle_id,
    cantidad,
):
    """
    Actualiza la cantidad de un detalle perteneciente
    al carrito ACTIVO del usuario.

    La validación comercial y de stock se realiza
    previamente desde services.py.
    """

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                UPDATE carrito_detalles AS cd

                INNER JOIN carritos AS c
                    ON c.id = cd.carrito_id

                SET
                    cd.cantidad = %s

                WHERE
                    cd.id = %s
                    AND c.usuario_id = %s
                    AND c.estado = 'ACTIVO'
                """,
                (
                    cantidad,
                    carrito_detalle_id,
                    usuario_id,
                ),
            )

            actualizado = (
                cursor.rowcount > 0
            )

            conexion.commit()

            return actualizado

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()


# ============================================================
# 13. ELIMINAR DETALLE DEL CARRITO
# ============================================================

def eliminar_detalle_carrito(
    usuario_id,
    carrito_detalle_id,
):
    """
    Elimina un detalle del carrito ACTIVO del usuario.

    Si el detalle corresponde a un pack personalizado,
    elimina primero su composición.
    """

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            # ------------------------------------------------
            # 1. Verificar que el detalle pertenece
            #    al carrito activo del usuario.
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    cd.id

                FROM carrito_detalles AS cd

                INNER JOIN carritos AS c
                    ON c.id = cd.carrito_id

                WHERE
                    cd.id = %s
                    AND c.usuario_id = %s
                    AND c.estado = 'ACTIVO'

                LIMIT 1

                FOR UPDATE
                """,
                (
                    carrito_detalle_id,
                    usuario_id,
                ),
            )

            detalle = cursor.fetchone()

            if not detalle:

                conexion.rollback()

                return False

            # ------------------------------------------------
            # 2. Eliminar composición si existe.
            # ------------------------------------------------

            cursor.execute(
                """
                DELETE FROM carrito_composiciones

                WHERE carrito_detalle_id = %s
                """,
                (
                    carrito_detalle_id,
                ),
            )

            # ------------------------------------------------
            # 3. Eliminar el detalle.
            # ------------------------------------------------

            cursor.execute(
                """
                DELETE FROM carrito_detalles

                WHERE id = %s
                """,
                (
                    carrito_detalle_id,
                ),
            )

            eliminado = (
                cursor.rowcount > 0
            )

            conexion.commit()

            return eliminado

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()