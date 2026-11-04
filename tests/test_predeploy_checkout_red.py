"""Separación validación externa/escritura, sin SQL ni red reales."""

import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, Mock, patch

from flask import Flask, g

from app.config import database
from app.identidad import services, repositories


class FacturacionPreparadaTest(unittest.TestCase):
    def test_preparacion_no_guarda_y_es_inmutable(self):
        with patch.object(services, "validar_dni_con_perfil", return_value={
            "ok": True, "persona": {"dni": "12345678", "nombre_completo": "ANA PRUEBA"},
        }), patch.object(services, "guardar_datos_facturacion") as guardar:
            resultado = services.preparar_facturacion_checkout("usuario", "BOLETA", "12345678")
        guardar.assert_not_called()
        preparada = resultado["preparada"]
        self.assertEqual(preparada.usuario_id, "usuario")
        with self.assertRaises(FrozenInstanceError):
            preparada.dni = "00000000"

    def test_persistencia_no_consulta_http_y_usa_la_misma_conexion(self):
        preparada = services.FacturacionPreparada(
            "usuario", "FACTURA", ruc="20123456789",
            razon_social="EMPRESA FICTICIA", direccion_fiscal="Dirección ficticia",
        )
        conexion = object()
        with patch.object(services, "consultar_dni") as dni, patch.object(
            services, "consultar_ruc"
        ) as ruc, patch.object(
            services, "guardar_datos_facturacion", return_value="fact-id"
        ) as guardar:
            resultado = services.guardar_facturacion_preparada("usuario", preparada, conexion)
        self.assertEqual(resultado["facturacion_id"], "fact-id")
        self.assertIs(guardar.call_args.kwargs["conexion"], conexion)
        self.assertEqual(guardar.call_args.kwargs["tipo_contribuyente"], "EMPRESA")
        dni.assert_not_called()
        ruc.assert_not_called()

    def test_no_acepta_diccionario_del_navegador_ni_otro_usuario(self):
        with patch.object(services, "guardar_datos_facturacion") as guardar:
            for preparada in ({"dni": "12345678"}, services.FacturacionPreparada("otro", "BOLETA")):
                with self.assertRaises(ValueError):
                    services.guardar_facturacion_preparada("usuario", preparada)
        guardar.assert_not_called()

    def test_perfil_de_facturacion_cierra_conexion_no_reutilizable(self):
        conexion = MagicMock()
        cursor = conexion.cursor.return_value.__enter__.return_value = Mock()
        cursor.fetchone.return_value = None
        with patch.object(database, "crear_conexion", return_value=conexion) as crear, patch.object(
            database, "nombre_esquema", return_value="test_identidad"
        ):
            self.assertIsNone(repositories.obtener_datos_checkout_usuario("usuario"))
        crear.assert_called_once_with("test_identidad", reutilizar=False)
        conexion.close.assert_called_once()

    def test_liberacion_cache_cierra_socket_no_solo_wrapper(self):
        app = Flask(__name__)
        real = Mock()
        with app.app_context():
            g._conexiones_sulpaa = {"identidad": database._ConexionCompartida(real)}
            database.cerrar_conexiones_solicitud(None)
            self.assertFalse(hasattr(g, "_conexiones_sulpaa"))
        real.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
