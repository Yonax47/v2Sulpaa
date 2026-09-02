"""
Servicios del módulo Inventario de SULPAA V2.

Aquí se encuentra la lógica relacionada con disponibilidad
de inventario que puede ser utilizada por otros módulos.
"""

from app.inventario.repositories import (
    obtener_existencias_por_variantes,
)


# ============================================================
# DISPONIBILIDAD
# ============================================================

def obtener_disponibilidad_variantes(variantes_ids):
    """
    Obtiene la disponibilidad real de varias variantes.

    Disponible = stock físico - stock reservado.

    Una variante sin registro de existencias se considera
    correctamente con disponibilidad 0.
    """

    existencias = obtener_existencias_por_variantes(
        variantes_ids
    )

    disponibilidad = {}

    for variante_id in variantes_ids:

        existencia = existencias.get(
            variante_id,
            {
                "stock_fisico": 0,
                "stock_reservado": 0,
            },
        )

        stock_fisico = existencia["stock_fisico"]
        stock_reservado = existencia["stock_reservado"]

        # Nunca exponemos disponibilidad negativa.
        stock_disponible = max(
            stock_fisico - stock_reservado,
            0,
        )

        disponibilidad[variante_id] = {
            "stock_fisico": stock_fisico,
            "stock_reservado": stock_reservado,
            "stock_disponible": stock_disponible,
            "disponible": stock_disponible > 0,
        }

    return disponibilidad

from app.inventario.repositories import (
    crear_reserva_inventario,
)


# ============================================================
# CREAR RESERVA PARA PEDIDO
# ============================================================

def reservar_stock_pedido(
    pedido_id,
    consumos,
):
    """
    Solicita al repositorio de Inventario
    reservar físicamente la disponibilidad
    necesaria para un pedido.
    """

    return crear_reserva_inventario(
        referencia_id=pedido_id,
        consumos=consumos,
        minutos_expiracion=30,
    )