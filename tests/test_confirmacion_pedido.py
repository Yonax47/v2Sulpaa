# -*- coding: utf-8 -*-
"""Pruebas de la página de confirmación posterior al checkout."""

import unittest
from unittest.mock import patch

from app import create_app


class ConfirmacionPedidoTest(unittest.TestCase):
    """La confirmación solo lee un pedido real del usuario autenticado."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def cliente_autenticado(self):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "usuario-1",
                "correo": "cliente@example.test",
                "roles": [],
            })
        return cliente

    def test_muestra_datos_reales_del_pedido(self):
        pedido = {
            "id": "pedido-1",
            "numero_pedido": "PED-2026-001",
            "estado_label": "Creado",
            "subtotal": 20.0,
            "costo_entrega": 5.0,
            "total": 25.0,
            "detalles": [{
                "nombre_articulo": "Kombucha limón",
                "cantidad": 2,
                "precio_unitario": 10.0,
                "subtotal_linea": 20.0,
            }],
            "entrega": {
                "tipo_entrega_label": "Delivery local",
                "delivery": {
                    "direccion": "Av. Prueba 123",
                    "distrito_nombre": "Huancayo",
                },
            },
            "pago": {
                "metodo_nombre": "Yape",
                "estado_label": "Pendiente",
            },
        }

        with patch(
            "app.comercio.routes.obtener_detalle_pedido_usuario",
            return_value={"ok": True, "pedido": pedido},
        ) as obtener:
            respuesta = self.cliente_autenticado().get(
                "/pedidos/pedido-1/confirmacion"
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("¡Tu pedido se realizó correctamente!".encode(),
                      respuesta.data)
        for texto in (
            "PED-2026-001", "Kombucha limón", "S/ 25.00",
            "Delivery local", "Yape", "Ver mi pedido",
            "Volver a la tienda",
        ):
            self.assertIn(texto.encode(), respuesta.data)
        obtener.assert_called_once_with(
            usuario_id="usuario-1", pedido_id="pedido-1"
        )

    def test_pedido_ajeno_o_inexistente_responde_404(self):
        with patch(
            "app.comercio.routes.obtener_detalle_pedido_usuario",
            return_value={"ok": False},
        ):
            respuesta = self.cliente_autenticado().get(
                "/pedidos/pedido-ajeno/confirmacion"
            )

        self.assertEqual(respuesta.status_code, 404)


if __name__ == "__main__":
    unittest.main()
