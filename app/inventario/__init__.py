"""Dominio de existencias y reservas de inventario."""

from app.inventario.services import (
	obtener_disponibilidad_variantes,
	reservar_stock_pedido,
)

__all__ = [
	"obtener_disponibilidad_variantes",
	"reservar_stock_pedido",
]
