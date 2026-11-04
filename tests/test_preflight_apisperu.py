"""Preflight local: contador InnoDB simulado, sin SQL ni HTTP reales."""

import hashlib
import hmac
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from flask import Flask

from app.config.apisperu import configurar_apisperu
from app.identidad import apisperu, apisperu_rate_limit as repos


class AlmacenSimulado:
    """Simula bloqueo transaccional compartido entre conexiones independientes.

    Prueba el algoritmo Python, no sustituye locks reales de MariaDB.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.filas = {}
        self.ahora = datetime(2026, 11, 3, 12)
        self.conexiones = []

    def conectar(self, *args, **kwargs):
        conexion = ConexionSimulada(self)
        self.conexiones.append(conexion)
        return conexion


class ConexionSimulada:
    def __init__(self, almacen):
        self.almacen = almacen
        self.bloqueada = False
        self.cerrada = False
        self.confirmada = False

    def begin(self):
        self.almacen.lock.acquire()
        self.bloqueada = True

    def cursor(self):
        return CursorSimulado(self)

    def commit(self):
        self.confirmada = True
        self.rollback()

    def rollback(self):
        if self.bloqueada:
            self.bloqueada = False
            self.almacen.lock.release()

    def close(self):
        self.rollback()
        self.cerrada = True


class CursorSimulado:
    def __init__(self, conexion):
        self.almacen = conexion.almacen
        self.resultado = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        if "SELECT NOW" in sql:
            self.resultado = {"ahora": self.almacen.ahora}
        elif "INSERT INTO" in sql:
            operacion, clave, ahora, _ = params
            self.almacen.filas.setdefault((operacion, clave), {
                "intentos": 0, "ventana_inicia_en": ahora,
                "ultimo_intento_en": ahora,
            })
        elif "FOR UPDATE" in sql:
            self.resultado = dict(self.almacen.filas[tuple(params)])
        elif "UPDATE limites" in sql:
            intentos, inicio, ahora, operacion, clave = params
            self.almacen.filas[(operacion, clave)] = {
                "intentos": intentos, "ventana_inicia_en": inicio,
                "ultimo_intento_en": ahora,
            }
        else:
            raise AssertionError("SQL inesperado en fixture")

    def fetchone(self):
        return self.resultado


class ContadorTest(unittest.TestCase):
    def setUp(self):
        self.almacen = AlmacenSimulado()
        self.conectar = patch.object(
            repos, "crear_conexion", side_effect=self.almacen.conectar
        ).start()
        patch.object(repos, "nombre_esquema", return_value="test_identidad").start()
        self.addCleanup(patch.stopall)

    def consumir(self, operacion="DNI", clave=b"h" * 32):
        return repos.consumir_limite_apisperu(
            operacion=operacion, clave_hash=clave, maximo=5, ventana_segundos=600
        )

    def test_primera_solicitud_confirma_y_cierra_conexion_independiente(self):
        self.assertTrue(self.consumir().permitido)
        self.conectar.assert_called_once_with("test_identidad", reutilizar=False)
        self.assertTrue(self.almacen.conexiones[0].confirmada)
        self.assertTrue(self.almacen.conexiones[0].cerrada)

    def test_40_workers_simulados_solo_admiten_cinco(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados = list(pool.map(lambda _: self.consumir(), range(40)))
        self.assertEqual(sum(r.permitido for r in resultados), 5)
        self.assertEqual(self.almacen.filas[("DNI", b"h" * 32)]["intentos"], 5)
        self.assertTrue(all(c.cerrada for c in self.almacen.conexiones))
        self.assertEqual(resultados[-1].reintentar_en, 600)

    def test_ventana_expira_y_se_reinicia(self):
        for _ in range(5):
            self.consumir()
        self.assertFalse(self.consumir().permitido)
        self.almacen.ahora += timedelta(seconds=600)
        self.assertTrue(self.consumir().permitido)
        self.assertEqual(self.almacen.filas[("DNI", b"h" * 32)]["intentos"], 1)

    def test_operaciones_y_clientes_aislados(self):
        for _ in range(5):
            self.consumir()
        self.assertTrue(self.consumir("RUC").permitido)
        self.assertTrue(self.consumir(clave=b"x" * 32).permitido)

    def test_error_sql_revierte_y_cierra(self):
        conexion = Mock()
        conexion.cursor.side_effect = RuntimeError("fallo fixture")
        self.conectar.side_effect = None
        self.conectar.return_value = conexion
        with self.assertRaises(RuntimeError):
            self.consumir()
        conexion.rollback.assert_called_once()
        conexion.close.assert_called_once()

    def test_entradas_invalidas_no_abren_conexion(self):
        for operacion, clave in (("OTRO", b"h" * 32), ("DNI", b"mal")):
            with self.assertRaises(ValueError):
                self.consumir(operacion, clave)
        self.conectar.assert_not_called()


class ClienteTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            APISPERU_RATE_LIMIT_ENABLED=True,
            APISPERU_RATE_LIMIT_MIGRATION_APPROVED=True,
            APISPERU_RATE_LIMIT_KEY="sintetica-no-real-" * 3,
            APISPERU_RATE_LIMIT_MAX_DNI=5,
            APISPERU_RATE_LIMIT_MAX_RUC=5,
            APISPERU_RATE_LIMIT_WINDOW_SECONDS=600,
        )
        self.http = patch.object(apisperu.requests, "get").start()
        self.http.return_value = Mock(status_code=200)
        self.http.return_value.json.return_value = {
            "dni": "12345678", "nombres": "ANA",
            "apellidoPaterno": "PRUEBA", "razonSocial": "EMPRESA FICTICIA",
        }
        patch.object(apisperu, "_obtener_token", return_value="token-sintetico").start()
        self.contador = patch.object(
            apisperu, "consumir_limite_apisperu",
            return_value=repos.ResultadoLimite(True),
        ).start()
        self.addCleanup(patch.stopall)

    def contexto(self, **kwargs):
        return self.app.test_request_context(
            environ_base={"REMOTE_ADDR": "192.0.2.5"}, **kwargs
        )

    def test_desactivado_no_usa_sql(self):
        self.app.config["APISPERU_RATE_LIMIT_ENABLED"] = False
        with self.contexto():
            self.assertTrue(apisperu.consultar_dni("12345678")["ok"])
        self.contador.assert_not_called()

    def test_hmac_ip_no_cabecera_ni_documento(self):
        with self.contexto(headers={"X-Forwarded-For": "198.51.100.88"}):
            apisperu.consultar_dni("12345678")
        esperado = hmac.new(
            self.app.config["APISPERU_RATE_LIMIT_KEY"].encode(),
            b"192.0.2.5", hashlib.sha256,
        ).digest()
        self.assertEqual(self.contador.call_args.kwargs["clave_hash"], esperado)
        self.assertNotIn("12345678", repr(self.contador.call_args))

    def test_dni_y_ruc_son_limitados(self):
        self.contador.return_value = repos.ResultadoLimite(False, 120)
        with self.contexto():
            for consultar, documento in (
                (apisperu.consultar_dni, "12345678"),
                (apisperu.consultar_ruc, "20123456789"),
            ):
                resultado = consultar(documento)
                self.assertEqual(resultado["tipo_error"], "LIMITE")
                self.assertEqual(resultado["reintentar_en"], 120)
        self.http.assert_not_called()

    def test_fallo_contador_no_hace_http_ni_filtra_excepcion(self):
        self.contador.side_effect = RuntimeError("secreto-documento-token")
        with self.contexto(), self.assertLogs(apisperu.logger, level="ERROR") as logs:
            resultado = apisperu.consultar_dni("12345678")
        self.assertEqual(resultado["tipo_error"], "CONTADOR_NO_DISPONIBLE")
        self.assertNotIn("secreto-documento-token", str(logs.output))
        self.http.assert_not_called()

    def test_ip_invalida_o_proxy_no_validado_falla_cerrado(self):
        self.app.config.update(ENTORNO="production", RAILWAY_PROXY_VALIDADO=False)
        with self.contexto():
            resultado = apisperu.consultar_dni("12345678")
        self.assertEqual(resultado["tipo_error"], "CONTADOR_NO_DISPONIBLE")
        self.contador.assert_not_called()
        self.http.assert_not_called()

    def test_fuera_de_peticion_falla_cerrado(self):
        with self.app.app_context():
            resultado = apisperu.consultar_dni("12345678")
        self.assertEqual(resultado["tipo_error"], "CONTADOR_NO_DISPONIBLE")
        self.http.assert_not_called()

    def test_sin_aprobacion_o_ip_valida_no_consulta(self):
        self.app.config["APISPERU_RATE_LIMIT_MIGRATION_APPROVED"] = False
        with self.contexto():
            self.assertFalse(apisperu.consultar_dni("12345678")["ok"])
        self.app.config["APISPERU_RATE_LIMIT_MIGRATION_APPROVED"] = True
        with self.app.test_request_context(environ_base={"REMOTE_ADDR": "invalida"}):
            self.assertFalse(apisperu.consultar_dni("12345678")["ok"])
        self.http.assert_not_called()
        self.contador.assert_not_called()

    def test_proxy_validado_permite_consumir_con_ip_canonica(self):
        self.app.config.update(
            ENTORNO="production", RAILWAY_PROXY_VALIDADO=True,
            TRUSTED_PROXY_HOPS=1,
        )
        with self.contexto():
            self.assertTrue(apisperu.consultar_dni("12345678")["ok"])
        self.contador.assert_called_once()

    def test_cierra_socket_contador_antes_de_http(self):
        almacen = AlmacenSimulado()
        self.contador.side_effect = repos.consumir_limite_apisperu
        def http(*args, **kwargs):
            self.assertTrue(almacen.conexiones[-1].cerrada)
            return Mock(status_code=404)
        self.http.side_effect = http
        with self.contexto(), patch.object(
            repos, "crear_conexion", side_effect=almacen.conectar
        ), patch.object(repos, "nombre_esquema", return_value="test_identidad"):
            apisperu.consultar_dni("12345678")
        self.http.assert_called_once()


class ConfiguracionTest(unittest.TestCase):
    def test_por_defecto_desactivado(self):
        with patch.dict("os.environ", {}, clear=True):
            app = Flask(__name__)
            configurar_apisperu(app)
        self.assertFalse(app.config["APISPERU_RATE_LIMIT_ENABLED"])

    def test_no_activa_sin_aprobar_migracion_o_sin_clave(self):
        for entorno in (
            {"APISPERU_RATE_LIMIT_ENABLED": "1"},
            {"APISPERU_RATE_LIMIT_ENABLED": "1",
             "APISPERU_RATE_LIMIT_MIGRATION_APPROVED": "1"},
        ):
            with patch.dict("os.environ", entorno, clear=True):
                with self.assertRaises(RuntimeError):
                    configurar_apisperu(Flask(__name__))

    def test_activacion_explicita_y_limites(self):
        with patch.dict("os.environ", {
            "APISPERU_RATE_LIMIT_ENABLED": "1",
            "APISPERU_RATE_LIMIT_MIGRATION_APPROVED": "1",
            "APISPERU_RATE_LIMIT_KEY": "clave-sintetica-" * 3,
        }, clear=True):
            app = Flask(__name__)
            configurar_apisperu(app)
        self.assertTrue(app.config["APISPERU_RATE_LIMIT_ENABLED"])
        self.assertEqual(app.config["APISPERU_RATE_LIMIT_MAX_DNI"], 5)

    def test_limites_fuera_de_rango_impiden_arranque(self):
        for valor in ("0", "101", "no-numero"):
            with patch.dict("os.environ", {
                "APISPERU_RATE_LIMIT_MAX_DNI": valor,
            }, clear=True), self.assertRaises(RuntimeError):
                configurar_apisperu(Flask(__name__))


class ContratoHTTPTest(unittest.TestCase):
    def test_rechazos_del_endpoint_registro(self):
        from app import create_app
        from app.shared.rate_limit import limpiar_limites

        app = create_app()
        app.config.update(TESTING=True, OMITIR_SEGURIDAD_EN_PRUEBAS=True)
        for tipo, estado, codigo in (
            ("LIMITE", "LIMITE", 429),
            ("CONTADOR_NO_DISPONIBLE", "ERROR", 503),
        ):
            limpiar_limites()
            with patch("app.identidad.routes.verificar_dni_registro", return_value={
                "ok": False, "tipo_error": tipo, "estado": estado,
                "mensaje": "Respuesta controlada",
            }):
                respuesta = app.test_client().post(
                    "/identidad/api/registro/verificar-dni", json={"dni": "12345678"}
                )
            self.assertEqual(respuesta.status_code, codigo)
            self.assertEqual(respuesta.headers["Cache-Control"], "no-store")
        limpiar_limites()


if __name__ == "__main__":
    unittest.main()
