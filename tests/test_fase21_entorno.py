# -*- coding: utf-8 -*-
"""Pruebas sin conexión para las barreras de la Fase 2.1."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import database
from scripts.testing import diagnose_test_environment as diagnostico
from scripts.testing import prepare_test_databases as preparador
from scripts.testing import test_environment as entorno
from scripts.testing import verify_test_structure as verificador


def configuracion_ficticia(carpeta_imagenes):
    """Devuelve valores aislados que no corresponden a un servidor real."""

    return {
        "SULPAA_TESTING": "1",
        "DB_HOST_TEST": "127.0.0.1",
        "DB_PORT_TEST": "3307",
        "DB_USER_TEST": "sulpaa_pruebas",
        "DB_PASSWORD_TEST": "clave-test-ficticia",
        "DB_TEST_SCHEMA_PREFIX": "sulpaa_test_",
        "DB_IDENTIDAD_TEST": "sulpaa_test_identidad",
        "DB_COMERCIO_TEST": "sulpaa_test_comercio",
        "DB_INVENTARIO_TEST": "sulpaa_test_inventario",
        "DB_OPERACIONES_TEST": "sulpaa_test_operaciones",
        "CATALOGO_IMAGENES_DIR": str(carpeta_imagenes),
    }


class BarrerasEntornoTest(unittest.TestCase):
    """Comprueba marcadores, separación de credenciales y almacenamiento."""

    def test_marcadores_de_ejemplo_bloquean_configuracion(self):
        valores = configuracion_ficticia("C:/catalogo-test")
        valores["DB_HOST_TEST"] = "<servidor-mysql-aislado>"
        with patch.dict(os.environ, valores, clear=True):
            with self.assertRaisesRegex(RuntimeError, "marcadores"):
                database.validar_configuracion_pruebas()

    def test_host_y_password_productivos_no_se_reutilizan(self):
        valores = configuracion_ficticia("C:/catalogo-test")
        valores.update({
            "DB_HOST": valores["DB_HOST_TEST"],
            "DB_PASSWORD": "otra-clave",
        })
        with patch.dict(os.environ, valores, clear=True):
            with self.assertRaisesRegex(RuntimeError, "host de producción"):
                database.validar_configuracion_pruebas()

        valores["DB_HOST"] = "produccion.example"
        valores["DB_PASSWORD"] = valores["DB_PASSWORD_TEST"]
        with patch.dict(os.environ, valores, clear=True):
            with self.assertRaisesRegex(RuntimeError, "contraseña productiva"):
                database.validar_configuracion_pruebas()

    def test_directorio_se_revisa_sin_crearlo(self):
        with tempfile.TemporaryDirectory() as temporal:
            destino = Path(temporal) / "carpeta-que-no-existe-sulpaa"
            correcto, _detalle = entorno.revisar_directorio_imagenes(destino)
            self.assertFalse(correcto)
            self.assertFalse(destino.exists())

    def test_credenciales_admin_productivas_se_rechazan(self):
        valores = {
            "DB_ADMIN_USER_TEST": "admin-real",
            "DB_ADMIN_PASSWORD_TEST": "clave-test",
            "DB_ADMIN_USER": "admin-real",
        }
        with self.assertRaisesRegex(RuntimeError, "usuario productivo"):
            entorno.validar_credenciales_administrativas(valores)


class HerramientasSegurasTest(unittest.TestCase):
    """Valida diagnóstico, filtro SQL y contrato sin abrir MySQL."""

    def test_diagnostico_sin_env_informa_bloqueo(self):
        with tempfile.TemporaryDirectory() as temporal, patch.object(
            diagnostico, "CARPETA_SQL", Path(temporal) / "sql"
        ), patch.dict(os.environ, {}, clear=True):
            mensajes, correcto = diagnostico.diagnosticar(
                Path(temporal) / ".env.test"
            )
        self.assertFalse(correcto)
        self.assertTrue(any("No existe" in texto for _nivel, texto in mensajes))

    def test_sql_administrativo_se_rechaza_antes_de_conectar(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "comercio.schema.sql"
            ruta.write_text("DROP DATABASE produccion;", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "no permitida"):
                preparador.validar_contenido_sql(ruta)

    def test_sql_de_tabla_test_es_admitido(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "comercio.schema.sql"
            ruta.write_text(
                "-- Use solo datos ficticios\n"
                "CREATE TABLE categorias (id INT PRIMARY KEY);",
                encoding="utf-8",
            )
            preparador.validar_contenido_sql(ruta)

    def test_comparador_detecta_tabla_y_columnas_faltantes(self):
        estructura = {
            tabla: set(columnas)
            for tabla, columnas in verificador.CONTRATO["operaciones"].items()
        }
        self.assertEqual(
            verificador.comparar_estructura("operaciones", estructura), []
        )
        estructura["auditoria_operaciones"].remove("accion")
        errores = verificador.comparar_estructura("operaciones", estructura)
        self.assertIn("accion", errores[0])


if __name__ == "__main__":
    unittest.main()
