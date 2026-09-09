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

# ============================================================
# 14. PESOS DE VARIANTES
# ============================================================

def obtener_pesos_variantes(variante_ids):
    """
    Obtiene el peso físico registrado de las variantes indicadas.

    El peso se obtiene exclusivamente desde Comercio.
    No se calcula ni se hardcodea en frontend.

    Se utiliza principalmente para calcular el peso total
    del carrito antes de cotizar una modalidad de entrega.
    """

    if not variante_ids:
        return {}

    # Evita repetir IDs innecesariamente en la consulta.
    variante_ids = list(dict.fromkeys(variante_ids))

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            placeholders = ", ".join(
                ["%s"] * len(variante_ids)
            )

            consulta = f"""
                SELECT
                    id AS variante_id,
                    peso_gramos

                FROM variantes

                WHERE
                    id IN ({placeholders})
                    AND estado = 'ACTIVO'
            """

            cursor.execute(
                consulta,
                tuple(variante_ids),
            )

            filas = cursor.fetchall()

            return {
                fila["variante_id"]:
                    float(fila["peso_gramos"])
                    if fila["peso_gramos"] is not None
                    else None

                for fila in filas
            }

    finally:

        conexion.close()

# ============================================================
# 15. CREAR PEDIDO DESDE SNAPSHOT DEL CHECKOUT
# ============================================================

def crear_pedido(
    pedido_id,
    numero_pedido,
    usuario_id,
    items,
    costo_entrega,
    moneda="PEN",
):
    """
    Crea la cabecera, detalles y composiciones de un pedido.

    IMPORTANTE:
    - Los items recibidos deben haber sido reconstruidos y
      validados previamente desde backend.
    - No se confían precios, cantidades ni totales enviados
      directamente desde JavaScript.
    - Toda la escritura de Comercio ocurre en una única
      transacción.
    """

    from decimal import (
        Decimal,
        ROUND_HALF_UP,
    )

    if not pedido_id:
        raise ValueError(
            "No se recibió el identificador del pedido."
        )

    if not numero_pedido:
        raise ValueError(
            "No se recibió el número del pedido."
        )

    if not usuario_id:
        raise ValueError(
            "No se pudo identificar al usuario."
        )

    if not items:
        raise ValueError(
            "El pedido no contiene productos."
        )

    def dinero(valor):
        return Decimal(
            str(valor or 0)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    costo_entrega = dinero(
        costo_entrega
    )

    if costo_entrega < 0:
        raise ValueError(
            "El costo de entrega no es válido."
        )

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            # ----------------------------------------------------
            # 1. Verificar que el número no exista
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT id

                FROM pedidos

                WHERE numero_pedido = %s

                LIMIT 1

                FOR UPDATE
                """,
                (
                    numero_pedido,
                ),
            )

            if cursor.fetchone():

                raise ValueError(
                    "El número de pedido ya existe."
                )

            # ----------------------------------------------------
            # 2. Calcular subtotal exclusivamente
            #    desde el snapshot validado por backend
            # ----------------------------------------------------

            subtotal = Decimal("0.00")

            items_normalizados = []

            for item in items:

                articulo_venta_id = item.get(
                    "articulo_venta_id"
                )

                nombre = str(
                    item.get(
                        "nombre",
                        "",
                    )
                ).strip()

                try:

                    cantidad = int(
                        item.get(
                            "cantidad",
                            0,
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    cantidad = 0

                precio = dinero(
                    item.get(
                        "precio",
                        0,
                    )
                )

                if not articulo_venta_id:

                    raise ValueError(
                        "Uno de los artículos del pedido "
                        "no es válido."
                    )

                if not nombre:

                    raise ValueError(
                        "Uno de los artículos no tiene "
                        "un nombre válido."
                    )

                if cantidad <= 0:

                    raise ValueError(
                        "Uno de los artículos tiene "
                        "una cantidad inválida."
                    )

                if precio < 0:

                    raise ValueError(
                        "Uno de los artículos tiene "
                        "un precio inválido."
                    )

                subtotal_linea = dinero(
                    precio
                    * cantidad
                )

                subtotal += subtotal_linea

                items_normalizados.append({
                    **item,

                    "nombre":
                        nombre,

                    "cantidad":
                        cantidad,

                    "precio":
                        precio,

                    "subtotal_linea":
                        subtotal_linea,
                })

            subtotal = dinero(
                subtotal
            )

            total = dinero(
                subtotal
                + costo_entrega
            )

            # ----------------------------------------------------
            # 3. Crear cabecera
            # ----------------------------------------------------

            cursor.execute(
                """
                INSERT INTO pedidos (
                    id,
                    numero_pedido,
                    usuario_id,
                    origen,
                    subtotal,
                    descuento_total,
                    costo_entrega,
                    total,
                    moneda,
                    estado
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'WEB',
                    %s,
                    0.00,
                    %s,
                    %s,
                    %s,
                    'CREADO'
                )
                """,
                (
                    pedido_id,
                    numero_pedido,
                    usuario_id,
                    subtotal,
                    costo_entrega,
                    total,
                    moneda,
                ),
            )

            # ----------------------------------------------------
            # 4. Crear detalles
            # ----------------------------------------------------

            detalles_creados = []

            for item in items_normalizados:

                pedido_detalle_id = str(
                    uuid.uuid4()
                )

                cursor.execute(
                    """
                    INSERT INTO pedido_detalles (
                        id,
                        pedido_id,
                        articulo_venta_id,
                        nombre_articulo,
                        cantidad,
                        precio_unitario,
                        descuento_unitario,
                        subtotal_linea
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        0.00,
                        %s
                    )
                    """,
                    (
                        pedido_detalle_id,
                        pedido_id,
                        item[
                            "articulo_venta_id"
                        ],
                        item["nombre"],
                        item["cantidad"],
                        item["precio"],
                        item[
                            "subtotal_linea"
                        ],
                    ),
                )

                # ------------------------------------------------
                # 5. Snapshot de composición
                # ------------------------------------------------

                composicion = item.get(
                    "composicion",
                    [],
                )

                for componente in composicion:

                    variante_id = (
                        componente.get(
                            "variante_id"
                        )
                    )

                    nombre_variante = str(
                        componente.get(
                            "nombre_variante",
                            "",
                        )
                    ).strip()

                    try:

                        cantidad_componente = int(
                            componente.get(
                                "cantidad",
                                0,
                            )
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):

                        cantidad_componente = 0

                    if not variante_id:

                        raise ValueError(
                            "La composición de uno de los "
                            "productos no es válida."
                        )

                    if not nombre_variante:

                        raise ValueError(
                            "Una variante del pedido "
                            "no tiene nombre."
                        )

                    if cantidad_componente <= 0:

                        raise ValueError(
                            "La composición contiene una "
                            "cantidad inválida."
                        )

                    cursor.execute(
                        """
                        INSERT INTO pedido_composiciones (
                            id,
                            pedido_detalle_id,
                            variante_id,
                            nombre_variante,
                            cantidad
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        """,
                        (
                            str(
                                uuid.uuid4()
                            ),
                            pedido_detalle_id,
                            variante_id,
                            nombre_variante,
                            cantidad_componente,
                        ),
                    )

                detalles_creados.append({
                    "pedido_detalle_id":
                        pedido_detalle_id,

                    "articulo_venta_id":
                        item[
                            "articulo_venta_id"
                        ],
                })

            conexion.commit()

            return {
                "ok": True,
                "mensaje":
                    "Pedido creado correctamente.",

                "pedido_id":
                    pedido_id,

                "numero_pedido":
                    numero_pedido,

                "subtotal":
                    float(subtotal),

                "costo_entrega":
                    float(costo_entrega),

                "total":
                    float(total),

                "moneda":
                    moneda,

                "estado":
                    "CREADO",

                "detalles":
                    detalles_creados,
            }

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()


# ============================================================
# 16. CAMBIAR ESTADO DEL PEDIDO
# ============================================================

def actualizar_estado_pedido(
    pedido_id,
    estado,
):
    """
    Permite actualizar el estado comercial del pedido.

    Se utilizará principalmente como mecanismo de compensación
    cuando una operación posterior de Inventario u Operaciones
    no pueda completarse.
    """

    if not pedido_id:
        return False

    estado = str(
        estado or ""
    ).strip().upper()

    if not estado:
        return False

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                UPDATE pedidos

                SET estado = %s

                WHERE id = %s
                """,
                (
                    estado,
                    pedido_id,
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
# 17. CERRAR CARRITO DESPUÉS DE LA COMPRA
# ============================================================

def cerrar_carrito_usuario(
    usuario_id,
):
    """
    Cierra el carrito ACTIVO únicamente cuando todo el proceso
    de confirmación del pedido terminó correctamente.

    No eliminamos físicamente el carrito ni sus detalles:
    conservamos el registro histórico.
    """

    if not usuario_id:
        return False

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                UPDATE carritos

                SET estado = 'CONVERTIDO'

                WHERE
                    usuario_id = %s
                    AND estado = 'ACTIVO'
                """,
                (
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

def reabrir_carrito_usuario(
    usuario_id,
):
    """
    Revierte el carrito CONVERTIDO a ACTIVO cuando
    una confirmación de checkout falla después de
    haber cerrado temporalmente el carrito.

    Se utiliza únicamente como mecanismo de
    compensación del proceso de compra.
    """

    conexion = conexion_comercio()

    try:

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT id
            FROM carritos
            WHERE usuario_id = %s
              AND estado = 'CONVERTIDO'
            ORDER BY actualizado_en DESC
            LIMIT 1
            FOR UPDATE
            """,
            (
                usuario_id,
            ),
        )

        carrito = cursor.fetchone()

        if not carrito:

            conexion.rollback()

            return {
                "ok": False,
                "mensaje":
                    "No se encontró un carrito convertido.",
            }

        cursor.execute(
            """
            UPDATE carritos
            SET estado = 'ACTIVO'
            WHERE id = %s
            """,
            (
                carrito["id"],
            ),
        )

        conexion.commit()

        return {
            "ok": True,
            "carrito_id":
                carrito["id"],
        }

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()

# ============================================================
# 18. DATOS BÁSICOS DE VARIANTES PARA SNAPSHOT DE PEDIDO
# ============================================================

def obtener_variantes_snapshot(
    variante_ids,
):
    """
    Obtiene los datos mínimos de las variantes que deben
    conservarse como snapshot dentro de un pedido.

    Se utiliza para no depender posteriormente de que el nombre
    comercial de una variante cambie en el catálogo.
    """

    if not variante_ids:
        return {}

    variante_ids = list(
        dict.fromkeys(
            variante_ids
        )
    )

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            placeholders = ", ".join(
                ["%s"] * len(variante_ids)
            )

            consulta = f"""
                SELECT
                    id AS variante_id,
                    nombre_comercial

                FROM variantes

                WHERE id IN ({placeholders})
            """

            cursor.execute(
                consulta,
                tuple(variante_ids),
            )

            filas = cursor.fetchall()

            return {
                fila["variante_id"]: {
                    "variante_id":
                        fila["variante_id"],

                    "nombre_variante":
                        fila["nombre_comercial"],
                }

                for fila in filas
            }

    finally:

        conexion.close()