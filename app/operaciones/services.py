"""Reglas de negocio para confirmar pedidos."""

from collections import defaultdict

from app.comercio.repositories import (
	obtener_composiciones_carrito,
	obtener_detalles_carrito_usuario,
)
from app.identidad.services import obtener_checkout_usuario
from app.inventario.services import reservar_stock_pedido
from app.operaciones.repositories import (
	actualizar_estado_pedido,
	crear_pedido,
)


def confirmar_pedido(usuario_id, tipo_comprobante="BOLETA"):
	"""Valida el checkout, crea el pedido y reserva su inventario."""

	if tipo_comprobante not in {"BOLETA", "FACTURA"}:
		return {"ok": False, "mensaje": "Tipo de comprobante inválido."}

	checkout = obtener_checkout_usuario(usuario_id)
	if not checkout.get("direccion"):
		return {"ok": False, "mensaje": "Registra una dirección de entrega."}

	detalles = obtener_detalles_carrito_usuario(usuario_id)
	if not detalles:
		return {"ok": False, "mensaje": "Tu carrito está vacío."}

	composiciones = obtener_composiciones_carrito(
		[item["carrito_detalle_id"] for item in detalles]
	)
	composiciones_por_detalle = defaultdict(list)
	for composicion in composiciones:
		composiciones_por_detalle[composicion["carrito_detalle_id"]].append(composicion)

	items = []
	consumos = defaultdict(int)
	for detalle in detalles:
		cantidad = int(detalle["cantidad"])
		precio = float(detalle["precio"] or 0)
		item = {
			"articulo_venta_id": detalle["articulo_venta_id"],
			"cantidad": cantidad,
			"precio": precio,
			"subtotal": precio * cantidad,
			"composicion": composiciones_por_detalle.get(
				detalle["carrito_detalle_id"], []
			),
		}
		items.append(item)

		if detalle["variante_id"]:
			consumos[detalle["variante_id"]] += cantidad
		else:
			for componente in item["composicion"]:
				consumos[componente["variante_id"]] += (
					int(componente["cantidad"]) * cantidad
				)

	subtotal = sum(item["subtotal"] for item in items)
	pedido = crear_pedido(
		usuario_id=usuario_id,
		items=items,
		subtotal=subtotal,
		tipo_comprobante=tipo_comprobante,
		direccion=checkout["direccion"],
		facturacion=checkout.get("facturacion"),
	)

	try:
		reserva = reservar_stock_pedido(pedido["pedido_id"], consumos)
	except Exception:
		actualizar_estado_pedido(pedido["pedido_id"], "CANCELADO")
		raise

	return {
		"ok": True,
		"mensaje": "Pedido creado correctamente.",
		**pedido,
		"reserva": reserva,
	}
