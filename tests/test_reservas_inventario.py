"""Pruebas de reservas de inventario sin base de datos real.

Se usan conexiones y cursores falsos que imitan a MariaDB. Así se
verifica el SQL y la lógica sin escribir nada en Alwaysdata.

Cubren:

- reserva válida, con la expiración calculada por la base;
- expiración inválida;
- confirmación correcta de la reserva;
- reserva vencida, confirmación repetida y stock insuficiente;
- mensajes de error seguros para el cliente.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from pymysql.err import MySQLError

from app.comercio import services
from app.inventario import repositories


AHORA_BD = datetime(2026, 10, 28, 22, 45, 0)
EXPIRA_BD = AHORA_BD + timedelta(minutes=30)


class _CursorFalso:
    """Cursor falso que responde según la consulta recibida."""

    def __init__(self, responder):
        self.responder = responder
        self.consultas = []
        self.rowcount = 0
        self._uno = None
        self._todos = []

    def __enter__(self):
        return self

    def __exit__(self, tipo, error, traza):
        return False

    def execute(self, sql, parametros=None):
        consulta = " ".join(sql.split())
        self.consultas.append((consulta, parametros))
        self._uno, self._todos, self.rowcount = self.responder(
            consulta, parametros
        )

    def fetchone(self):
        return self._uno

    def fetchall(self):
        return self._todos


class _ConexionFalsa:
    """Conexión falsa que registra commit, rollback y cierre."""

    def __init__(self, responder):
        self.cursor_falso = _CursorFalso(responder)
        self.commits = 0
        self.rollbacks = 0
        self.cerrada = False
        self.esquemas = []

    def cursor(self):
        return self.cursor_falso

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.cerrada = True

    def select_db(self, nombre):
        self.esquemas.append(nombre)


def _responder_creacion(expira_en=EXPIRA_BD):
    """Respuestas esperadas al crear una reserva."""

    def responder(consulta, parametros):

        if "FROM almacenes" in consulta:
            return {"id": "almacen-1"}, [], 0

        if "FROM existencias" in consulta:
            return {
                "id": "existencia-1",
                "stock_fisico": 10,
                "stock_reservado": 2,
            }, [], 0

        if consulta.startswith("INSERT INTO reservas"):
            return None, [], 1

        if consulta.startswith("SELECT expira_en"):
            return {"expira_en": expira_en}, [], 0

        if "INSERT INTO reserva_detalles" in consulta:
            return None, [], 1

        if consulta.startswith("UPDATE existencias"):
            return None, [], 1

        raise AssertionError("Consulta no esperada: " + consulta)

    return responder


def _responder_confirmacion(
    estado="ACTIVA",
    expira_en=EXPIRA_BD,
    ahora=AHORA_BD,
    stock_fisico=10,
    stock_reservado=2,
):
    """Respuestas esperadas al confirmar una reserva."""

    def responder(consulta, parametros):

        if "NOW() AS ahora" in consulta:
            return {
                "id": "reserva-1",
                "estado": estado,
                "expira_en": expira_en,
                "ahora": ahora,
            }, [], 0

        if "FROM reserva_detalles" in consulta:
            return None, [
                {
                    "almacen_id": "almacen-1",
                    "variante_id": "variante-1",
                    "cantidad": 2,
                }
            ], 0

        if "FROM motivos_movimiento" in consulta:
            return {"id": 4}, [], 0

        if "FROM existencias" in consulta:
            return {
                "id": "existencia-1",
                "stock_fisico": stock_fisico,
                "stock_reservado": stock_reservado,
            }, [], 0

        if consulta.startswith("UPDATE existencias"):
            return None, [], 1

        if consulta.startswith("INSERT INTO movimientos_inventario"):
            return None, [], 1

        if consulta.startswith("UPDATE reservas"):
            return None, [], 1

        raise AssertionError("Consulta no esperada: " + consulta)

    return responder


class CrearReservaInventarioTest(unittest.TestCase):
    """La reserva se crea con el reloj de MariaDB."""

    def _crear(self, minutos=30, responder=None):
        conexion = _ConexionFalsa(
            responder or _responder_creacion()
        )

        with patch.object(
            repositories,
            "conexion_inventario",
            return_value=conexion,
        ):
            resultado = repositories.crear_reserva_inventario(
                referencia_id="pedido-1",
                consumos={"variante-1": 2},
                minutos_expiracion=minutos,
            )

        return resultado, conexion

    def test_reserva_valida_usa_reloj_de_la_base(self):
        resultado, conexion = self._crear()

        self.assertTrue(resultado["ok"], resultado)

        insert = next(
            consulta
            for consulta, _ in conexion.cursor_falso.consultas
            if consulta.startswith("INSERT INTO reservas")
        )
        parametros = next(
            parametros
            for consulta, parametros in conexion.cursor_falso.consultas
            if consulta.startswith("INSERT INTO reservas")
        )

        # La fecha la calcula MariaDB, no Python.
        self.assertIn("DATE_ADD", insert)
        self.assertIn("NOW()", insert)
        self.assertIn("INTERVAL %s MINUTE", insert)

        # El único valor variable de la fecha son los minutos.
        self.assertEqual(parametros[3], 30)
        self.assertFalse(
            any(isinstance(valor, datetime) for valor in parametros),
            "No se debe enviar una fecha calculada en Python.",
        )

    def test_reserva_devuelve_la_fecha_guardada_por_la_base(self):
        resultado, _ = self._crear()

        self.assertEqual(resultado["expira_en"], EXPIRA_BD)
        self.assertGreater(resultado["expira_en"], AHORA_BD)

    def test_reserva_valida_confirma_y_cierra_su_conexion(self):
        _, conexion = self._crear()

        self.assertEqual(conexion.commits, 1)
        self.assertEqual(conexion.rollbacks, 0)
        self.assertTrue(conexion.cerrada)

    def test_reserva_con_expiracion_invalida_no_inserta(self):
        conexion = _ConexionFalsa(_responder_creacion())

        with patch.object(
            repositories,
            "conexion_inventario",
            return_value=conexion,
        ):
            with self.assertRaises(ValueError) as contexto:
                repositories.crear_reserva_inventario(
                    referencia_id="pedido-1",
                    consumos={"variante-1": 2},
                    minutos_expiracion=0,
                )

        self.assertIn("mayor que cero", str(contexto.exception))
        self.assertEqual(conexion.commits, 0)
        self.assertEqual(conexion.rollbacks, 1)
        self.assertTrue(conexion.cerrada)

        self.assertFalse(
            any(
                consulta.startswith("INSERT INTO reservas")
                for consulta, _ in conexion.cursor_falso.consultas
            )
        )


class ConfirmarReservaTest(unittest.TestCase):
    """Una reserva solo se confirma si está activa y vigente."""

    def _confirmar(self, **opciones):
        conexion = _ConexionFalsa(
            _responder_confirmacion(**opciones)
        )

        resultado = repositories.confirmar_reserva_pedido(
            pedido_id="pedido-1",
            usuario_id="usuario-1",
            conexion=conexion,
        )

        return resultado, conexion

    def test_confirmacion_correcta_descuenta_stock(self):
        resultado, conexion = self._confirmar()

        self.assertTrue(resultado["ok"], resultado)
        self.assertEqual(resultado["estado"], "CONFIRMADA")

        actualizaciones = [
            (consulta, parametros)
            for consulta, parametros in conexion.cursor_falso.consultas
            if consulta.startswith("UPDATE existencias")
        ]

        self.assertEqual(len(actualizaciones), 1)
        # stock_fisico 10 - 2 = 8 | stock_reservado 2 - 2 = 0
        self.assertEqual(actualizaciones[0][1][0], 8)
        self.assertEqual(actualizaciones[0][1][1], 0)

        movimientos = [
            consulta
            for consulta, _ in conexion.cursor_falso.consultas
            if consulta.startswith("INSERT INTO movimientos_inventario")
        ]
        self.assertEqual(len(movimientos), 1)

    def test_reserva_vencida_no_ejecuta_escrituras(self):
        conexion = _ConexionFalsa(
            _responder_confirmacion(
                expira_en=AHORA_BD - timedelta(minutes=1),
            )
        )

        with self.assertRaises(ValueError) as contexto:
            repositories.confirmar_reserva_pedido(
                pedido_id="pedido-1",
                conexion=conexion,
            )

        self.assertIn("expiró", str(contexto.exception))

        escrituras = [
            consulta
            for consulta, _ in conexion.cursor_falso.consultas
            if consulta.startswith(("UPDATE ", "INSERT "))
        ]
        self.assertEqual(escrituras, [])

    def test_reserva_con_estado_distinto_no_se_confirma(self):
        with self.assertRaises(ValueError) as contexto:
            self._confirmar(estado="CONFIRMADA")

        self.assertIn("ya no está activa", str(contexto.exception))

    def test_confirmacion_repetida_se_rechaza(self):
        # La segunda confirmación encuentra la reserva ya confirmada.
        with self.assertRaises(ValueError) as contexto:
            self._confirmar(estado="CONFIRMADA")

        self.assertIn("ya no está activa", str(contexto.exception))

    def test_stock_insuficiente_se_rechaza(self):
        with self.assertRaises(ValueError) as contexto:
            self._confirmar(stock_fisico=0)

        self.assertIn("stock físico", str(contexto.exception))


class MensajeErrorCheckoutTest(unittest.TestCase):
    """El cliente nunca recibe detalles internos de MariaDB."""

    def _traducir(self, error):
        with patch.object(services.logger, "error") as registro:
            mensaje = services._mensaje_error_checkout(error)
        self.assertTrue(registro.called, "El error real debe registrarse.")
        return mensaje

    def test_error_de_restriccion_no_expone_detalles(self):
        error = MySQLError(
            4025,
            "CONSTRAINT `chk_reserva_expiracion` failed for "
            "`base1sulpaa_inventario`.`reservas`",
        )

        mensaje = self._traducir(error)

        for prohibido in (
            "4025",
            "CONSTRAINT",
            "chk_reserva_expiracion",
            "base1sulpaa_inventario",
            "reservas",
        ):
            self.assertNotIn(prohibido, mensaje)

        self.assertIn("Intenta nuevamente", mensaje)

    def test_errores_conocidos_tienen_mensaje_propio(self):
        casos = {
            1062: "ya fue registrado",
            1205: "actualizando",
            1213: "conflicto",
            1452: "ya no está disponible",
        }

        for codigo, texto in casos.items():
            with self.subTest(codigo=codigo):
                mensaje = self._traducir(
                    MySQLError(codigo, "detalle interno")
                )
                self.assertIn(texto, mensaje)
                self.assertNotIn("detalle interno", mensaje)

    def test_error_de_negocio_conserva_su_mensaje(self):
        mensaje = self._traducir(
            ValueError("La reserva del pedido expiró. "
                       "Vuelve a armar el carrito e intenta nuevamente.")
        )

        self.assertIn("expiró", mensaje)
        self.assertIn("carrito", mensaje)

    def test_error_inesperado_tampoco_expone_detalles(self):
        mensaje = self._traducir(
            RuntimeError("fallo simulado en entrega")
        )

        self.assertNotIn("fallo simulado", mensaje)
        self.assertNotIn("Traceback", mensaje)
        self.assertIn("Intenta nuevamente", mensaje)


if __name__ == "__main__":
    unittest.main()
