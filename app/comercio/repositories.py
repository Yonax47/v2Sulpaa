"""
Acceso a datos del módulo Comercio de SULPAA V2.

Responsabilidades:

- catálogo;
- variantes;
- packs;
- precios;
- reglas comerciales;
- carrito persistente.
- pedidos

IMPORTANTE:

El stock NO pertenece a este repositorio.
El stock se consulta exclusivamente mediante Inventario.
"""

import uuid
from datetime import datetime
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
# PEDIDOS
# ============================================================

def generar_numero_pedido():
    """
    Genera un número único y legible para el pedido.

    Ejemplo:
    PED-20260905-A1B2C3
    """

    fecha = datetime.now().strftime("%Y%m%d")
    codigo = uuid.uuid4().hex[:6].upper()

    return f"PED-{fecha}-{codigo}"


def crear_pedido_completo(
    usuario_id,
    origen,
    subtotal,
    descuento_total,
    costo_entrega,
    total,
    moneda,
    detalles,
    datos_cliente,
    datos_facturacion
):
    """
    Crea el pedido completo en una sola transacción.

    Inserta:
        pedidos
        pedido_detalles
        pedidos_composiciones
        pedido_datos_cliente
        pedido_facturacion
        pedido_historial

    Si algo falla, se hace ROLLBACK.
    """

    conn = conexion_comercio()
    cursor = conn.cursor()

    try:

        # ----------------------------------------------------
        # 1. CABECERA DEL PEDIDO
        # ----------------------------------------------------

        pedido_id = str(uuid.uuid4())
        numero_pedido = generar_numero_pedido()

        sql_pedido = """
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
                estado,
                creado_en,
                actualizado_en
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'PENDIENTE',
                NOW(),
                NOW()
            )
        """

        cursor.execute(sql_pedido, (
            pedido_id,
            numero_pedido,
            usuario_id,
            origen,
            subtotal,
            descuento_total,
            costo_entrega,
            total,
            moneda
        ))

        # ----------------------------------------------------
        # 2. DETALLES DEL PEDIDO
        # ----------------------------------------------------

        sql_detalle = """
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
                %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        # ----------------------------------------------------
        # 3. COMPOSICIONES
        # ----------------------------------------------------

        sql_composicion = """
            INSERT INTO pedidos_composiciones (
                id,
                pedido_detalle_id,
                variante_id,
                nombre_variante,
                cantidad
            )
            VALUES (
                %s, %s, %s, %s, %s
            )
        """

        for detalle in detalles:

            pedido_detalle_id = str(uuid.uuid4())

            cursor.execute(sql_detalle, (
                pedido_detalle_id,
                pedido_id,
                detalle["articulo_venta_id"],
                detalle["nombre_articulo"],
                detalle["cantidad"],
                detalle["precio_unitario"],
                detalle["descuento_unitario"],
                detalle["subtotal_linea"]
            ))

            # Composiciones del pack
            for composicion in detalle.get(
                "composiciones",
                []
            ):

                cursor.execute(sql_composicion, (
                    str(uuid.uuid4()),
                    pedido_detalle_id,
                    composicion["variante_id"],
                    composicion["nombre_variante"],
                    composicion["cantidad"]
                ))

        # ----------------------------------------------------
        # 4. DATOS DEL CLIENTE
        # ----------------------------------------------------

        sql_cliente = """
            INSERT INTO pedido_datos_cliente (
                pedido_id,
                nombres,
                apellido_paterno,
                apellido_materno,
                dni,
                telefono,
                correo
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s
            )
        """

        cursor.execute(sql_cliente, (
            pedido_id,
            datos_cliente.get("nombres"),
            datos_cliente.get("apellido_paterno"),
            datos_cliente.get("apellido_materno"),
            datos_cliente.get("dni"),
            datos_cliente.get("telefono"),
            datos_cliente.get("correo")
        ))

        # ----------------------------------------------------
        # 5. FACTURACIÓN
        # ----------------------------------------------------

        sql_facturacion = """
            INSERT INTO pedido_facturacion (
                pedido_id,
                tipo,
                dni,
                ruc,
                nombre_facturacion,
                razon_social,
                distrito_id,
                direccion_fiscal
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        cursor.execute(sql_facturacion, (
            pedido_id,
            datos_facturacion.get("tipo"),
            datos_facturacion.get("dni"),
            datos_facturacion.get("ruc"),
            datos_facturacion.get("nombre_facturacion"),
            datos_facturacion.get("razon_social"),
            datos_facturacion.get("distrito_id"),
            datos_facturacion.get("direccion_fiscal")
        ))

        # ----------------------------------------------------
        # 6. HISTORIAL
        # ----------------------------------------------------

        sql_historial = """
            INSERT INTO pedido_historial (
                id,
                pedido_id,
                estado_anterior,
                estado_nuevo,
                cambiado_por_usuario_id,
                origen,
                comentario,
                creado_en
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, NOW()
            )
        """

        cursor.execute(sql_historial, (
            str(uuid.uuid4()),
            pedido_id,
            None,
            "PENDIENTE",
            usuario_id,
            origen,
            "Pedido creado desde el checkout."
        ))

        # ----------------------------------------------------
        # CONFIRMAR TODA LA TRANSACCIÓN
        # ----------------------------------------------------

        conn.commit()

        return {
            "id": pedido_id,
            "numero_pedido": numero_pedido
        }

    except Exception:

        conn.rollback()
        raise

    finally:

        cursor.close()
        conn.close()

def obtener_pedidos_usuario(usuario_id):
    """
    Obtiene todos los pedidos realizados por el usuario autenticado.

    Devuelve los pedidos ordenados del más reciente
    al más antiguo.
    """

    conn = conexion_comercio()

    try:

        with conn.cursor() as cursor:

            sql = """
                SELECT
                    id,
                    numero_pedido,
                    usuario_id,
                    origen,
                    subtotal,
                    descuento_total,
                    costo_entrega,
                    total,
                    moneda,
                    estado,
                    creado_en,
                    actualizado_en
                FROM pedidos
                WHERE usuario_id = %s
                ORDER BY creado_en DESC
            """

            cursor.execute(
                sql,
                (usuario_id,)
            )

            filas = cursor.fetchall()

            # ------------------------------------------------
            # Si el cursor ya devuelve diccionarios
            # ------------------------------------------------

            if not filas:
                return []

            if isinstance(filas[0], dict):
                return filas

            # ------------------------------------------------
            # Si el cursor devuelve tuplas
            # ------------------------------------------------

            columnas = [
                columna[0]
                for columna in cursor.description
            ]

            return [
                dict(zip(columnas, fila))
                for fila in filas
            ]

    finally:

        conn.close()

def obtener_pedido_usuario(
    pedido_id,
    usuario_id
):
    """
    Obtiene un pedido específico.

    IMPORTANTE:
    El pedido debe pertenecer al usuario autenticado.
    """

    conn = conexion_comercio()

    try:

        with conn.cursor() as cursor:

            sql = """
                SELECT
                    id,
                    numero_pedido,
                    usuario_id,
                    origen,
                    subtotal,
                    descuento_total,
                    costo_entrega,
                    total,
                    moneda,
                    estado,
                    creado_en,
                    actualizado_en
                FROM pedidos
                WHERE id = %s
                  AND usuario_id = %s
                LIMIT 1
            """

            cursor.execute(
                sql,
                (
                    pedido_id,
                    usuario_id
                )
            )

            fila = cursor.fetchone()

            if not fila:
                return None

            if isinstance(fila, dict):
                return fila

            columnas = [
                columna[0]
                for columna in cursor.description
            ]

            return dict(
                zip(
                    columnas,
                    fila
                )
            )

    finally:

        conn.close()

def obtener_detalles_pedido(pedido_id):
    """
    Obtiene los productos pertenecientes a un pedido.
    """

    conn = conexion_comercio()

    try:

        with conn.cursor() as cursor:

            sql = """
                SELECT
                    id,
                    pedido_id,
                    articulo_venta_id,
                    nombre_articulo,
                    cantidad,
                    precio_unitario,
                    descuento_unitario,
                    subtotal_linea
                FROM pedido_detalles
                WHERE pedido_id = %s
                ORDER BY id
            """

            cursor.execute(
                sql,
                (pedido_id,)
            )

            filas = cursor.fetchall()

            if not filas:
                return []

            if isinstance(filas[0], dict):
                return filas

            columnas = [
                columna[0]
                for columna in cursor.description
            ]

            return [
                dict(zip(columnas, fila))
                for fila in filas
            ]

    finally:

        conn.close()

def obtener_composiciones_pedido(
    pedido_detalle_id
):

    conn = conexion_comercio()

    try:

        with conn.cursor() as cursor:

            sql = """
                SELECT
                    variante_id,
                    nombre_variante,
                    cantidad
                FROM pedidos_composiciones
                WHERE pedido_detalle_id = %s
                ORDER BY variante_id
            """

            cursor.execute(
                sql,
                (pedido_detalle_id,)
            )

            filas = cursor.fetchall()

            columnas = [
                columna[0]
                for columna in cursor.description
            ]

            composiciones = [
                dict(zip(columnas, fila))
                for fila in filas
            ]

            return composiciones

    finally:

        conn.close()

def cerrar_carrito_usuario(usuario_id):

    conn = conexion_comercio()
    cursor = conn.cursor()

    sql = """
        UPDATE carritos
        SET
            estado = 'CERRADO',
            actualizado_en = NOW()
        WHERE usuario_id = %s
          AND estado = 'ACTIVO'
    """

    cursor.execute(sql, (usuario_id,))

    conn.commit()

    cursor.close()
    conn.close()