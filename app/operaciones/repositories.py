"""Persistencia de pedidos del dominio de Operaciones."""

import uuid

from app.config.database import conexion_operaciones


def crear_pedido(
	usuario_id,
	items,
	subtotal, 
	tipo_comprobante,
	direccion,
	facturacion=None,
):
	"""Crea un pedido y sus detalles dentro de una transacción."""

	conexion = conexion_operaciones()
	pedido_id = str(uuid.uuid4())
	codigo_pedido = "PED-" + uuid.uuid4().hex[:12].upper()

	try:
		with conexion.cursor() as cursor:
			cursor.execute(
				"""
				INSERT INTO pedidos (
					id, codigo_pedido, usuario_id, estado,
					tipo_comprobante, subtotal, moneda,
					distrito_id, direccion, referencia,
					dni, ruc, nombre_facturacion, razon_social
				)
				VALUES (
					%s, %s, %s, 'PENDIENTE', %s, %s, 'PEN',
					%s, %s, %s, %s, %s, %s, %s
				)
				""",
				(
					pedido_id,
					codigo_pedido,
					usuario_id,
					tipo_comprobante,
					subtotal,
					direccion.get("distrito_id"),
					direccion.get("direccion"),
					direccion.get("referencia"),
					(facturacion or {}).get("dni"),
					(facturacion or {}).get("ruc"),
					(facturacion or {}).get("nombre_facturacion"),
					(facturacion or {}).get("razon_social"),
				),
			)

			for item in items:
				detalle_id = str(uuid.uuid4())
				cursor.execute(
					"""
					INSERT INTO pedido_detalles (
						id, pedido_id, articulo_venta_id, cantidad,
						precio_unitario, subtotal
					)
					VALUES (%s, %s, %s, %s, %s, %s)
					""",
					(
						detalle_id,
						pedido_id,
						item["articulo_venta_id"],
						item["cantidad"],
						item["precio"],
						item["subtotal"],
					),
				)

				for componente in item.get("composicion", []):
					cursor.execute(
						"""
						INSERT INTO pedido_composiciones (
							id, pedido_detalle_id, variante_id, cantidad
						)
						VALUES (%s, %s, %s, %s)
						""",
						(
							str(uuid.uuid4()),
							detalle_id,
							componente["variante_id"],
							componente["cantidad"],
						),
					)

		conexion.commit()
		return {
			"pedido_id": pedido_id,
			"codigo_pedido": codigo_pedido,
		}
	except Exception:
		conexion.rollback()
		raise
	finally:
		conexion.close()


def actualizar_estado_pedido(pedido_id, estado):
	"""Actualiza el estado de un pedido."""

	conexion = conexion_operaciones()

	try:
		with conexion.cursor() as cursor:
			cursor.execute(
				"UPDATE pedidos SET estado = %s WHERE id = %s",
				(estado, pedido_id),
			)
		conexion.commit()
	except Exception:
		conexion.rollback()
		raise
	finally:
		conexion.close()
