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