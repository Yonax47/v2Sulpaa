"""Pruebas unitarias del contrato central de estados."""

import unittest

from app.comercio.pedido_states import (
    ESTADO_CONFIRMADO,
    ESTADO_CREADO,
    ESTADO_EN_PREPARACION,
    transicion_permitida,
)


class MaquinaEstadosPedidoTest(unittest.TestCase):
    """Demuestra que la fase solo admite sus dos aristas autorizadas."""

    def test_transiciones_habilitadas(self):
        self.assertTrue(transicion_permitida(ESTADO_CREADO, ESTADO_CONFIRMADO))
        self.assertTrue(
            transicion_permitida(ESTADO_CONFIRMADO, ESTADO_EN_PREPARACION)
        )

    def test_saltos_y_retrocesos_rechazados(self):
        casos = [
            ("CREADO", "EN_PREPARACION"),
            ("CREADO", "COMPLETADO"),
            ("CONFIRMADO", "COMPLETADO"),
            ("EN_PREPARACION", "CONFIRMADO"),
            ("CANCELADO", "CREADO"),
        ]
        for anterior, nuevo in casos:
            with self.subTest(anterior=anterior, nuevo=nuevo):
                self.assertFalse(transicion_permitida(anterior, nuevo))


if __name__ == "__main__":
    unittest.main()
