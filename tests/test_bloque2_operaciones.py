"""Pruebas unitarias del Bloque 2 de SULPAA (sin base de datos)."""

import unittest

from app.operaciones import codigos_cliente
from app.operaciones.services import (
    ROLES_OPERACION_ENTREGAS,
    TRANSICIONES_ENTREGA,
    TRANSICIONES_ENVIO,
    _puede_confirmar_entrega,
    _puede_operar_entregas,
    _roles_normalizados,
    _transicion_habilitada,
    _transicion_envio_habilitada,
)


class CodigosClienteTest(unittest.TestCase):
    """El código debe ser seguro, reversible y verificar sin distinguir caja."""

    def test_generar_respeta_formato_y_alfabeto_seguro(self):
        for _ in range(200):
            codigo = codigos_cliente.generar_codigo()
            self.assertEqual(len(codigo), 8)
            self.assertTrue(codigo.isalnum())
            for caracter in codigo:
                self.assertNotIn(caracter, "0O1Il")

    def test_roundtrip_cifrado_y_descifrado(self):
        codigo = codigos_cliente.generar_codigo()
        token = codigos_cliente.cifrar_codigo(codigo)
        self.assertNotEqual(token, codigo)
        self.assertEqual(
            codigos_cliente.descifrar_codigo(token), codigo
        )

    def test_verificacion_no_distingue_mayusculas(self):
        codigo = "A7K2M9XQ"
        token = codigos_cliente.cifrar_codigo(codigo)
        self.assertTrue(codigos_cliente.verificar_codigo(token, "a7k2m9xq"))
        self.assertTrue(codigos_cliente.verificar_codigo(token, codigo))

    def test_verificacion_rechaza_incorrecto_o_vacio(self):
        token = codigos_cliente.cifrar_codigo("A7K2M9XQ")
        self.assertFalse(codigos_cliente.verificar_codigo(token, "ZZZZZZZZ"))
        self.assertFalse(codigos_cliente.verificar_codigo(token, None))
        self.assertFalse(codigos_cliente.verificar_codigo(token, ""))


class ReglasTransicionTest(unittest.TestCase):
    """La máquina de estados de entregas y envíos solo permite aristas reales."""

    def test_transiciones_validas_de_entrega(self):
        self.assertTrue(_transicion_habilitada("LISTO", "PROGRAMADO"))
        self.assertTrue(_transicion_habilitada("PROGRAMADO", "EN_TRANSITO"))
        self.assertTrue(_transicion_habilitada("EN_TRANSITO", "ENTREGADO"))
        self.assertTrue(
            _transicion_habilitada("LISTO_PARA_RECOJO", "ENTREGADO")
        )

    def test_transiciones_invalidas_de_entrega(self):
        self.assertFalse(_transicion_habilitada("EN_TRANSITO", "LISTO"))
        self.assertFalse(_transicion_habilitada("ENTREGADO", "EN_TRANSITO"))
        self.assertFalse(_transicion_habilitada("PENDIENTE", "ENTREGADO"))
        self.assertFalse(_transicion_habilitada(None, "ENTREGADO"))
        self.assertFalse(_transicion_habilitada("DESCONOCIDO", "LISTO"))

    def test_estados_terminales_no_admiten_avance(self):
        for origen in ("ENTREGADO", "CANCELADO"):
            for destino in TRANSICIONES_ENTREGA.get(origen, ()):
                self.assertTrue(destino in {"ENTREGADO", "CANCELADO"})

    def test_transiciones_envio_validas(self):
        self.assertTrue(
            _transicion_envio_habilitada("DESPACHADO", "EN_TRANSITO")
        )
        self.assertTrue(_transicion_envio_habilitada("EN_REPARTO", "ENTREGADO"))
        self.assertFalse(
            _transicion_envio_habilitada("PENDIENTE_DESPACHO", "ENTREGADO")
        )
        self.assertFalse(
            _transicion_envio_habilitada("DESPACHADO", "PENDIENTE_DESPACHO")
        )

    def test_cada_estado_envio_tiene_etiqueta_humana(self):
        terminales_envio = {"ENTREGADO", "CANCELADO"}
        for estado, destinos in TRANSICIONES_ENVIO.items():
            self.assertIn(estado, TRANSICIONES_ENVIO)
            for destino in destinos:
                self.assertTrue(
                    destino in TRANSICIONES_ENVIO
                    or destino in terminales_envio
                )


class RolesOperativosTest(unittest.TestCase):
    """Las reglas de permiso separan operativa, confirmación y cliente."""

    def test_operar_entregas_restringe_roles_admin(self):
        self.assertTrue(
            _puede_operar_entregas({"GERENTE", "ADMINISTRADOR", "PEDIDOS_LOGISTICA"})
        )
        self.assertFalse(_puede_operar_entregas({"REPARTIDOR"}))
        self.assertFalse(_puede_operar_entregas(set()))

    def test_confirmar_entrega_incluye_repartidor(self):
        self.assertTrue(
            _puede_confirmar_entrega({"REPARTIDOR", "PEDIDOS_LOGISTICA"})
        )
        self.assertFalse(_puede_confirmar_entrega({}))

    def test_roles_normalizados_toleran_minusculas_y_espacios(self):
        self.assertEqual(_roles_normalizados(["gerente ", " repartidor"]),
                         {"GERENTE", "REPARTIDOR"})

    def test_roles_operacion_entregas_coinciden_con_la_definicion(self):
        self.assertEqual(
            ROLES_OPERACION_ENTREGAS,
            {"GERENTE", "ADMINISTRADOR", "PEDIDOS_LOGISTICA"},
        )


if __name__ == "__main__":
    unittest.main()