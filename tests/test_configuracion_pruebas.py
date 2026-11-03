# -*- coding: utf-8 -*-
"""Pruebas de la barrera de bases TEST sin abrir una conexión real."""

import os
import unittest
from unittest.mock import patch

from app.config import database


def entorno_test_valido():
    """Crea valores ficticios que solo se usan para validar la configuración."""

    return {
        "SULPAA_TESTING": "1",
        "DB_HOST_TEST": "127.0.0.1",
        "DB_PORT_TEST": "3307",
        "DB_USER_TEST": "sulpaa_pruebas",
        "DB_PASSWORD_TEST": "valor-solo-para-prueba-unitaria",
        "DB_TEST_SCHEMA_PREFIX": "sulpaa_test_",
        "DB_IDENTIDAD_TEST": "sulpaa_test_identidad",
        "DB_COMERCIO_TEST": "sulpaa_test_comercio",
        "DB_INVENTARIO_TEST": "sulpaa_test_inventario",
        "DB_OPERACIONES_TEST": "sulpaa_test_operaciones",
        "DB_USER": "sulpaa_produccion",
        "DB_IDENTIDAD": "base1sulpaa_identidad",
        "DB_COMERCIO": "base1sulpaa_comercio",
        "DB_INVENTARIO": "base1sulpaa_inventario",
        "DB_OPERACIONES": "base1sulpaa_operaciones",
    }


class ConfiguracionPruebasTest(unittest.TestCase):
    """Verifica que una configuración peligrosa falle antes de PyMySQL."""

    def test_faltan_variables_y_no_intenta_conectar(self):
        entorno = entorno_test_valido()
        entorno.pop("DB_PASSWORD_TEST")
        with patch.dict(os.environ, entorno, clear=True), patch.object(
            database.pymysql, "connect"
        ) as conectar:
            with self.assertRaisesRegex(RuntimeError, "DB_PASSWORD_TEST"):
                database.conexion_identidad()
        conectar.assert_not_called()

    def test_rechaza_un_esquema_productivo_antes_de_conectar(self):
        entorno = entorno_test_valido()
        entorno["DB_TEST_SCHEMA_PREFIX"] = "base1sulpaa_"
        entorno["DB_IDENTIDAD_TEST"] = "base1sulpaa_identidad"
        with patch.dict(os.environ, entorno, clear=True), patch.object(
            database.pymysql, "connect"
        ) as conectar:
            with self.assertRaisesRegex(RuntimeError, "productivo prohibido"):
                database.conexion_identidad()
        conectar.assert_not_called()

    def test_rechaza_el_usuario_productivo(self):
        entorno = entorno_test_valido()
        entorno["DB_USER_TEST"] = entorno["DB_USER"]
        with patch.dict(os.environ, entorno, clear=True):
            with self.assertRaisesRegex(RuntimeError, "diferente"):
                database.validar_configuracion_pruebas()

    def test_solo_conecta_con_credenciales_y_esquema_test(self):
        entorno = entorno_test_valido()
        conexion_falsa = object()
        with patch.dict(os.environ, entorno, clear=True), patch.object(
            database.pymysql, "connect", return_value=conexion_falsa
        ) as conectar:
            resultado = database.conexion_comercio()

        self.assertIs(resultado, conexion_falsa)
        conectar.assert_called_once()
        argumentos = conectar.call_args.kwargs
        self.assertEqual(argumentos["host"], entorno["DB_HOST_TEST"])
        self.assertEqual(argumentos["user"], entorno["DB_USER_TEST"])
        self.assertEqual(argumentos["database"], entorno["DB_COMERCIO_TEST"])
        self.assertNotEqual(argumentos["user"], entorno["DB_USER"])


if __name__ == "__main__":
    unittest.main()
