"""
Acceso a datos del módulo Inventario de SULPAA V2.

Este repositorio es responsable únicamente de consultar
información almacenada en v2sulpaa_inventario_db.

No contiene reglas comerciales ni lógica de presentación.
"""

from app.config.database import conexion_inventario


# ============================================================
# DISPONIBILIDAD DE VARIANTES
# ============================================================

def obtener_existencias_por_variantes(variantes_ids):
    """
    Obtiene el stock consolidado de una colección de variantes.

    El stock disponible se calcula como:

        stock físico - stock reservado

    Si una variante no posee registro en existencias,
    posteriormente el servicio la considerará con stock 0.

    Args:
        variantes_ids: Lista de UUID de variantes.

    Returns:
        dict: Información de stock indexada por variante_id.
    """

    if not variantes_ids:
        return {}

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:

            placeholders = ", ".join(
                ["%s"] * len(variantes_ids)
            )

            consulta = f"""
                SELECT
                    variante_id,
                    SUM(stock_fisico) AS stock_fisico,
                    SUM(stock_reservado) AS stock_reservado
                FROM existencias
                WHERE variante_id IN ({placeholders})
                GROUP BY variante_id
            """

            cursor.execute(
                consulta,
                tuple(variantes_ids),
            )

            filas = cursor.fetchall()

            return {
                fila["variante_id"]: {
                    "stock_fisico": int(
                        fila["stock_fisico"] or 0
                    ),
                    "stock_reservado": int(
                        fila["stock_reservado"] or 0
                    ),
                }
                for fila in filas
            }

    finally:
        conexion.close()

# ============================================================
# 2. CREAR RESERVA DE INVENTARIO
# ============================================================

import uuid
from datetime import datetime, timedelta


def crear_reserva_inventario(
    referencia_id,
    consumos,
    minutos_expiracion=30,
):
    """
    Reserva stock para un pedido.

    consumos:
    {
        variante_id: cantidad,
        ...
    }

    La operación se realiza dentro de una única
    transacción de Inventario.
    """

    if not consumos:
        raise ValueError(
            "La reserva no contiene productos."
        )

    conexion = conexion_inventario()

    try:

        with conexion.cursor() as cursor:

            # ------------------------------------------------
            # 1. Obtener almacén activo
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT id

                FROM almacenes

                WHERE estado = 'ACTIVO'

                ORDER BY creado_en ASC

                LIMIT 1

                FOR UPDATE
                """
            )

            almacen = cursor.fetchone()

            if not almacen:

                raise ValueError(
                    "No existe un almacén activo."
                )

            almacen_id = almacen["id"]

            # ------------------------------------------------
            # 2. Validar y bloquear existencias
            # ------------------------------------------------

            existencias = {}

            for variante_id, cantidad in consumos.items():

                cantidad = int(cantidad)

                if cantidad <= 0:
                    raise ValueError(
                        "Cantidad de reserva inválida."
                    )

                cursor.execute(
                    """
                    SELECT
                        id,
                        stock_fisico,
                        stock_reservado

                    FROM existencias

                    WHERE
                        almacen_id = %s
                        AND variante_id = %s

                    LIMIT 1

                    FOR UPDATE
                    """,
                    (
                        almacen_id,
                        variante_id,
                    ),
                )

                existencia = cursor.fetchone()

                if not existencia:

                    raise ValueError(
                        "No existe stock para uno de los productos."
                    )

                stock_disponible = (
                    int(existencia["stock_fisico"])
                    - int(existencia["stock_reservado"])
                )

                if cantidad > stock_disponible:

                    raise ValueError(
                        "El stock cambió y ya no hay suficiente disponibilidad."
                    )

                existencias[variante_id] = {
                    "existencia_id":
                        existencia["id"],

                    "cantidad":
                        cantidad,
                }

            # ------------------------------------------------
            # 3. Crear cabecera de reserva
            # ------------------------------------------------

            reserva_id = str(
                uuid.uuid4()
            )

            codigo_reserva = (
                "RES-"
                + uuid.uuid4().hex[
                    :12
                ].upper()
            )

            expira_en = (
                datetime.now()
                + timedelta(
                    minutes=minutos_expiracion
                )
            )

            cursor.execute(
                """
                INSERT INTO reservas (
                    id,
                    codigo_reserva,
                    referencia_tipo,
                    referencia_id,
                    estado,
                    expira_en
                )
                VALUES (
                    %s,
                    %s,
                    'PEDIDO',
                    %s,
                    'ACTIVA',
                    %s
                )
                """,
                (
                    reserva_id,
                    codigo_reserva,
                    referencia_id,
                    expira_en,
                ),
            )

            # ------------------------------------------------
            # 4. Crear detalle y aumentar stock reservado
            # ------------------------------------------------

            for variante_id, datos in existencias.items():

                detalle_reserva_id = str(
                    uuid.uuid4()
                )

                cursor.execute(
                    """
                    INSERT INTO reserva_detalles (
                        id,
                        reserva_id,
                        almacen_id,
                        variante_id,
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
                        detalle_reserva_id,
                        reserva_id,
                        almacen_id,
                        variante_id,
                        datos["cantidad"],
                    ),
                )

                cursor.execute(
                    """
                    UPDATE existencias

                    SET
                        stock_reservado =
                            stock_reservado + %s

                    WHERE id = %s
                    """,
                    (
                        datos["cantidad"],
                        datos["existencia_id"],
                    ),
                )

            conexion.commit()

            return {
                "ok": True,
                "mensaje":
                    "Stock reservado correctamente.",

                "reserva_id":
                    reserva_id,

                "codigo_reserva":
                    codigo_reserva,

                "almacen_id":
                    almacen_id,

                "expira_en":
                    expira_en,
            }
    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()

# ============================================================
# 3. LIBERAR RESERVA DE UN PEDIDO
# ============================================================

def liberar_reserva_pedido(
    pedido_id,
):
    """
    Libera una reserva ACTIVA asociada a un pedido.

    Se utiliza como mecanismo de compensación cuando alguna
    operación posterior al reservado de inventario falla.

    Flujo:
    1. Bloquea la reserva.
    2. Obtiene sus detalles.
    3. Reduce stock_reservado.
    4. Marca la reserva como LIBERADA.

    Nunca modifica stock_fisico.
    """

    if not pedido_id:
        return False

    conexion = conexion_inventario()

    try:

        with conexion.cursor() as cursor:

            # ----------------------------------------------------
            # 1. Buscar y bloquear reserva activa
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    estado

                FROM reservas

                WHERE
                    referencia_tipo = 'PEDIDO'
                    AND referencia_id = %s
                    AND estado = 'ACTIVA'

                ORDER BY creado_en DESC

                LIMIT 1

                FOR UPDATE
                """,
                (
                    pedido_id,
                ),
            )

            reserva = cursor.fetchone()

            if not reserva:

                conexion.rollback()
                return False

            reserva_id = reserva["id"]

            # ----------------------------------------------------
            # 2. Obtener detalles de la reserva
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT
                    almacen_id,
                    variante_id,
                    cantidad

                FROM reserva_detalles

                WHERE reserva_id = %s

                FOR UPDATE
                """,
                (
                    reserva_id,
                ),
            )

            detalles = cursor.fetchall()

            # ----------------------------------------------------
            # 3. Liberar stock reservado
            # ----------------------------------------------------

            for detalle in detalles:

                cantidad = int(
                    detalle["cantidad"]
                )

                cursor.execute(
                    """
                    SELECT
                        id,
                        stock_reservado

                    FROM existencias

                    WHERE
                        almacen_id = %s
                        AND variante_id = %s

                    LIMIT 1

                    FOR UPDATE
                    """,
                    (
                        detalle["almacen_id"],
                        detalle["variante_id"],
                    ),
                )

                existencia = cursor.fetchone()

                if not existencia:

                    raise ValueError(
                        "No se encontró una existencia "
                        "asociada a la reserva."
                    )

                stock_reservado = int(
                    existencia[
                        "stock_reservado"
                    ]
                    or 0
                )

                nuevo_reservado = max(
                    stock_reservado
                    - cantidad,
                    0,
                )

                cursor.execute(
                    """
                    UPDATE existencias

                    SET stock_reservado = %s

                    WHERE id = %s
                    """,
                    (
                        nuevo_reservado,
                        existencia["id"],
                    ),
                )

            # ----------------------------------------------------
            # 4. Marcar reserva como liberada
            # ----------------------------------------------------

            cursor.execute(
                """
                UPDATE reservas

                SET
                    estado = 'LIBERADA',
                    liberado_en = NOW()

                WHERE
                    id = %s
                    AND estado = 'ACTIVA'
                """,
                (
                    reserva_id,
                ),
            )

            conexion.commit()

            return True

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()

# ============================================================
# 4. CONFIRMAR RESERVA COMO VENTA
# ============================================================

def confirmar_reserva_pedido(
    pedido_id,
    usuario_id=None,
):
    """
    Confirma una reserva ACTIVA y convierte el stock reservado
    en una salida física real por venta.

    Toda la operación se ejecuta dentro de una sola transacción:

    1. Bloquea la reserva.
    2. Bloquea las existencias involucradas.
    3. Descuenta stock_fisico.
    4. Descuenta stock_reservado.
    5. Registra el movimiento VENTA.
    6. Marca la reserva como CONFIRMADA.

    Si cualquier paso falla, se ejecuta ROLLBACK.
    """

    import uuid

    if not pedido_id:
        raise ValueError(
            "No se recibió el identificador del pedido."
        )

    conexion = conexion_inventario()

    try:

        with conexion.cursor() as cursor:

            # ----------------------------------------------------
            # 1. Buscar y bloquear reserva
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    estado

                FROM reservas

                WHERE
                    referencia_tipo = 'PEDIDO'
                    AND referencia_id = %s

                ORDER BY creado_en DESC

                LIMIT 1

                FOR UPDATE
                """,
                (
                    pedido_id,
                ),
            )

            reserva = cursor.fetchone()

            if not reserva:

                raise ValueError(
                    "No existe una reserva para este pedido."
                )

            if reserva["estado"] != "ACTIVA":

                raise ValueError(
                    "La reserva del pedido ya no está activa."
                )

            reserva_id = reserva["id"]

            # ----------------------------------------------------
            # 2. Obtener detalles
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT
                    almacen_id,
                    variante_id,
                    cantidad

                FROM reserva_detalles

                WHERE reserva_id = %s

                FOR UPDATE
                """,
                (
                    reserva_id,
                ),
            )

            detalles = cursor.fetchall()

            if not detalles:

                raise ValueError(
                    "La reserva no contiene productos."
                )

            # ----------------------------------------------------
            # 3. Obtener motivo VENTA desde catálogo
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT id

                FROM motivos_movimiento

                WHERE
                    codigo = 'VENTA'
                    AND estado = 'ACTIVO'

                LIMIT 1
                """
            )

            motivo = cursor.fetchone()

            if not motivo:

                raise ValueError(
                    "No existe el motivo activo VENTA "
                    "en Inventario."
                )

            motivo_id = motivo["id"]

            # ----------------------------------------------------
            # 4. Procesar cada variante reservada
            # ----------------------------------------------------

            for detalle in detalles:

                cantidad = int(
                    detalle["cantidad"]
                )

                if cantidad <= 0:

                    raise ValueError(
                        "La reserva contiene una cantidad inválida."
                    )

                cursor.execute(
                    """
                    SELECT
                        id,
                        stock_fisico,
                        stock_reservado

                    FROM existencias

                    WHERE
                        almacen_id = %s
                        AND variante_id = %s

                    LIMIT 1

                    FOR UPDATE
                    """,
                    (
                        detalle["almacen_id"],
                        detalle["variante_id"],
                    ),
                )

                existencia = cursor.fetchone()

                if not existencia:

                    raise ValueError(
                        "No se encontró la existencia "
                        "de una variante reservada."
                    )

                stock_fisico = int(
                    existencia["stock_fisico"]
                    or 0
                )

                stock_reservado = int(
                    existencia["stock_reservado"]
                    or 0
                )

                # La reserva debe seguir respaldada
                # por stock físico suficiente.
                if stock_fisico < cantidad:

                    raise ValueError(
                        "El stock físico ya no es suficiente "
                        "para confirmar el pedido."
                    )

                if stock_reservado < cantidad:

                    raise ValueError(
                        "El stock reservado es inconsistente "
                        "para confirmar el pedido."
                    )

                stock_posterior = (
                    stock_fisico
                    - cantidad
                )

                reservado_posterior = (
                    stock_reservado
                    - cantidad
                )

                # ------------------------------------------------
                # 5. Convertir reserva en salida física
                # ------------------------------------------------

                cursor.execute(
                    """
                    UPDATE existencias

                    SET
                        stock_fisico = %s,
                        stock_reservado = %s

                    WHERE id = %s
                    """,
                    (
                        stock_posterior,
                        reservado_posterior,
                        existencia["id"],
                    ),
                )

                # ------------------------------------------------
                # 6. Kardex / movimiento de venta
                # ------------------------------------------------

                cursor.execute(
                    """
                    INSERT INTO movimientos_inventario (
                        id,
                        almacen_id,
                        variante_id,
                        motivo_id,
                        tipo_movimiento,
                        cantidad,
                        stock_anterior,
                        stock_posterior,
                        origen,
                        referencia_tipo,
                        referencia_id,
                        usuario_responsable_id,
                        observacion
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        'SALIDA',
                        %s,
                        %s,
                        %s,
                        'SISTEMA',
                        'PEDIDO',
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        str(uuid.uuid4()),
                        detalle["almacen_id"],
                        detalle["variante_id"],
                        motivo_id,
                        cantidad,
                        stock_fisico,
                        stock_posterior,
                        pedido_id,
                        usuario_id,
                        "Salida automática por venta "
                        "confirmada desde checkout.",
                    ),
                )

            # ----------------------------------------------------
            # 7. Confirmar reserva
            # ----------------------------------------------------

            cursor.execute(
                """
                UPDATE reservas

                SET
                    estado = 'CONFIRMADA',
                    confirmado_en = NOW()

                WHERE
                    id = %s
                    AND estado = 'ACTIVA'
                """,
                (
                    reserva_id,
                ),
            )

            if cursor.rowcount != 1:

                raise ValueError(
                    "No fue posible confirmar la reserva."
                )

            conexion.commit()

            return {
                "ok": True,
                "reserva_id": reserva_id,
                "pedido_id": pedido_id,
                "estado": "CONFIRMADA",
            }

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()