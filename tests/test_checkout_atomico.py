"""Atomicidad del checkout: una sola conexión y un solo commit.

Cubre dos frentes:

- unitario: el orquestador escribe todos los pasos por la MISMA conexión y
  confirma una sola vez; si un paso falla, no confirma y no ejecuta
  compensaciones silenciosas;
- integración real (MySQL): una misma UnidadTrabajo inserta en dos esquemas
  distintos y, al no confirmar, InnoDB revierte ambos sin dejar residuos.
"""

import unittest
import uuid
from decimal import Decimal
from unittest.mock import patch

from app.comercio import services
from app.identidad import services as identidad_services
from app.shared.unit_of_work import UnidadTrabajo

ESQUEMAS = {
    "comercio": "v2sulpaa_comercio_db",
    "operaciones": "v2sulpaa_operaciones_db",
    "identidad": "v2sulpaa_identidad_db",
    "inventario": "v2sulpaa_inventario_db",
}


class _ConexionFalsa:

    def __init__(self):
        self.esquemas_seleccionados = []

    def select_db(self, nombre):
        self.esquemas_seleccionados.append(nombre)


class _UnidadTrabajoFalsa:

    instancias = []

    def __init__(self):
        self.conexion = _ConexionFalsa()
        self.confirmada = False
        _UnidadTrabajoFalsa.instancias.append(self)

    def __enter__(self):
        return self

    def confirmar(self):
        self.confirmada = True

    def __exit__(self, tipo, error, traza):
        return False


class CheckoutAtomicoUnitTest(unittest.TestCase):
    """El checkout se apoya en una única conexión y un único commit."""

    def _ejecutar(self, falla_en=None):
        capturas = {}
        snapshot = {
            "ok": True,
            "items": [{"cantidad": Decimal("2"), "precio": Decimal("10.00")}],
            "consumos": [{"articulo_venta_id": "art-1", "cantidad": 2}],
        }

        def fabricar(nombre, exito):
            def _falso(*args, **kwargs):
                capturas.setdefault(nombre, []).append(kwargs.get("conexion"))
                if falla_en == nombre:
                    if nombre == "entrega":
                        raise RuntimeError("fallo simulado en entrega")
                    return {"ok": False, "mensaje": f"fallo simulado en {nombre}"}
                return exito
            return _falso

        _UnidadTrabajoFalsa.instancias = []

        with patch.object(services, "esquemas_sulpaa", return_value=ESQUEMAS), \
                patch.object(services, "UnidadTrabajo", _UnidadTrabajoFalsa), \
                patch.object(services, "preparar_snapshot_pedido", return_value=snapshot), \
                patch.object(services, "reservar_stock_pedido", fabricar("reserva", {"ok": True})), \
                patch.object(services, "crear_pedido", fabricar("pedido", {"ok": True})), \
                patch.object(services, "crear_pago_checkout", fabricar("pago", {"ok": True})), \
                patch.object(services, "crear_entrega_pedido", fabricar("entrega", "entrega-1")), \
                patch.object(services, "cerrar_carrito_usuario", fabricar("carrito", True)), \
                patch.object(services, "confirmar_stock_pedido", fabricar("inventario", {"ok": True})):

            resultado = services.confirmar_checkout(
                usuario_id="usuario-1",
                tipo_entrega="RECOJO_LOCAL",
                metodo_pago_id=1,
                costo_entrega=0,
                entrega={"ok": True, "direccion_entrega": "Av. Prueba 123"},
            )

        return resultado, capturas

    def test_exito_una_sola_conexion_y_un_solo_commit(self):
        resultado, capturas = self._ejecutar()

        self.assertTrue(resultado["ok"], resultado)
        uow = _UnidadTrabajoFalsa.instancias[-1]
        self.assertTrue(uow.confirmada)

        conexiones = [c for lista in capturas.values() for c in lista]
        self.assertEqual(len(conexiones), 6)
        self.assertEqual(len({id(c) for c in conexiones}), 1)
        self.assertIs(conexiones[0], uow.conexion)
        self.assertEqual(
            uow.conexion.esquemas_seleccionados,
            [ESQUEMAS["inventario"], ESQUEMAS["comercio"],
             ESQUEMAS["operaciones"], ESQUEMAS["comercio"],
             ESQUEMAS["inventario"]],
        )

    def test_fallo_reserva_no_escribe_nada_posterior(self):
        resultado, capturas = self._ejecutar(falla_en="reserva")
        self.assertFalse(resultado["ok"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(set(capturas), {"reserva"})

    def test_fallo_pedido_revierte_reserva(self):
        resultado, capturas = self._ejecutar(falla_en="pedido")
        self.assertFalse(resultado["ok"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(set(capturas), {"reserva", "pedido"})

    def test_fallo_pago_revierte_lo_anterior(self):
        resultado, capturas = self._ejecutar(falla_en="pago")
        self.assertFalse(resultado["ok"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(set(capturas), {"reserva", "pedido", "pago"})

    def test_fallo_entrega_revierte_lo_anterior(self):
        resultado, capturas = self._ejecutar(falla_en="entrega")
        self.assertFalse(resultado["ok"])
        self.assertIn("entrega", resultado["mensaje"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(set(capturas), {"reserva", "pedido", "pago", "entrega"})

    def test_fallo_carrito_revierte_lo_anterior(self):
        resultado, capturas = self._ejecutar(falla_en="carrito")
        self.assertFalse(resultado["ok"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(
            set(capturas), {"reserva", "pedido", "pago", "entrega", "carrito"}
        )

    def test_fallo_inventario_no_confirma(self):
        resultado, capturas = self._ejecutar(falla_en="inventario")
        self.assertFalse(resultado["ok"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(
            set(capturas),
            {"reserva", "pedido", "pago", "entrega", "carrito", "inventario"},
        )

    def test_no_quedan_compensaciones_silenciosas(self):
        for nombre in (
            "liberar_stock_pedido",
            "cancelar_pago_checkout",
            "compensar_entrega_pedido",
            "actualizar_estado_pedido",
            "reabrir_carrito_usuario",
        ):
            self.assertFalse(
                hasattr(services, nombre),
                f"{nombre} no debe seguir disponible como compensación.",
            )


class CheckoutConFacturacionUnitTest(unittest.TestCase):
    """Facturación y checkout comparten conexión, transacción y commit."""

    def _datos(self):
        return {
            "tipo_comprobante": "BOLETA",
            "documento_facturacion": "12345678",
            "tipo_entrega": "RECOJO_LOCAL",
            "metodo_pago_id": 1,
        }

    def _ejecutar(
        self,
        falla_facturacion=False,
        falla_en=None,
        facturacion_resultado=None,
    ):
        capturas = {}
        snapshot = {
            "ok": True,
            "items": [{"cantidad": Decimal("2"), "precio": Decimal("10.00")}],
            "consumos": [{"articulo_venta_id": "art-1", "cantidad": 2}],
        }

        def fabricar(nombre, exito):
            def _falso(*args, **kwargs):
                capturas.setdefault(nombre, []).append(kwargs.get("conexion"))
                if falla_en == nombre:
                    if nombre == "entrega":
                        raise RuntimeError("fallo simulado en entrega")
                    return {"ok": False, "mensaje": f"fallo simulado en {nombre}"}
                return exito
            return _falso

        def fabricar_facturacion(*args, **kwargs):
            capturas.setdefault("facturacion", []).append(kwargs.get("conexion"))
            if falla_facturacion:
                return {"ok": False, "mensaje": "fallo simulado en facturacion"}
            return facturacion_resultado or {"ok": True, "facturacion_id": "fact-1"}

        _UnidadTrabajoFalsa.instancias = []

        with patch.object(services, "esquemas_sulpaa", return_value=ESQUEMAS), \
                patch.object(services, "UnidadTrabajo", _UnidadTrabajoFalsa), \
                patch.object(services, "validar_entrega_confirmacion",
                             return_value={"ok": True, "costo_entrega": Decimal("0.00"),
                                           "direccion_entrega": "Av. Prueba 123"}), \
                patch.object(services, "preparar_snapshot_pedido", return_value=snapshot), \
                patch.object(services, "reservar_stock_pedido", fabricar("reserva", {"ok": True})), \
                patch.object(services, "crear_pedido", fabricar("pedido", {"ok": True})), \
                patch.object(services, "crear_pago_checkout", fabricar("pago", {"ok": True})), \
                patch.object(services, "crear_entrega_pedido", fabricar("entrega", "entrega-1")), \
                patch.object(services, "cerrar_carrito_usuario", fabricar("carrito", {"ok": True})), \
                patch.object(services, "confirmar_stock_pedido", fabricar("inventario", {"ok": True})), \
                patch.object(identidad_services, "registrar_facturacion_checkout",
                             fabricar_facturacion):

            resultado = services.confirmar_checkout_con_entrega(
                "usuario-1", self._datos()
            )

        return resultado, capturas

    def _conexiones(self, capturas):
        return [c for lista in capturas.values() for c in lista]

    def test_fallo_facturacion_no_abre_checkout_ni_confirma(self):
        resultado, capturas = self._ejecutar(falla_facturacion=True)

        self.assertFalse(resultado["ok"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(set(capturas), {"facturacion"})

    def test_fallo_pedido_despues_de_facturacion_no_confirma(self):
        resultado, capturas = self._ejecutar(falla_en="pedido")

        self.assertFalse(resultado["ok"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertIn("facturacion", capturas)
        self.assertEqual(
            set(capturas), {"facturacion", "reserva", "pedido"}
        )
        self.assertEqual(
            len({id(c) for c in self._conexiones(capturas)}), 1
        )

    def test_fallo_pago_despues_de_facturacion_no_confirma(self):
        resultado, capturas = self._ejecutar(falla_en="pago")

        self.assertFalse(resultado["ok"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(
            set(capturas),
            {"facturacion", "reserva", "pedido", "pago"},
        )
        self.assertEqual(
            len({id(c) for c in self._conexiones(capturas)}), 1
        )

    def test_fallo_entrega_despues_de_facturacion_no_confirma(self):
        resultado, capturas = self._ejecutar(falla_en="entrega")

        self.assertFalse(resultado["ok"])
        self.assertIn("entrega", resultado["mensaje"])
        self.assertFalse(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(
            set(capturas),
            {"facturacion", "reserva", "pedido", "pago", "entrega"},
        )
        self.assertEqual(
            len({id(c) for c in self._conexiones(capturas)}), 1
        )

    def test_compra_exitosa_con_facturacion_un_solo_commit(self):
        resultado, capturas = self._ejecutar()

        self.assertTrue(resultado["ok"], resultado)
        uow = _UnidadTrabajoFalsa.instancias[-1]
        self.assertTrue(uow.confirmada)

        conexiones = self._conexiones(capturas)
        self.assertEqual(len(conexiones), 7)
        self.assertEqual(len({id(c) for c in conexiones}), 1)
        self.assertIs(conexiones[0], uow.conexion)

        self.assertEqual(
            uow.conexion.esquemas_seleccionados,
            [ESQUEMAS["identidad"], ESQUEMAS["inventario"], ESQUEMAS["comercio"],
             ESQUEMAS["operaciones"], ESQUEMAS["comercio"],
             ESQUEMAS["inventario"]],
        )
        self.assertEqual(resultado["facturacion_id"], "fact-1")
        self.assertEqual(resultado["tipo_comprobante"], "BOLETA")

    def test_compra_exitosa_sin_actualizar_facturacion(self):
        resultado, capturas = self._ejecutar(
            facturacion_resultado={
                "ok": True,
                "facturacion_id": "fact-existente",
                "actualizado": False,
            }
        )

        self.assertTrue(resultado["ok"], resultado)
        self.assertTrue(_UnidadTrabajoFalsa.instancias[-1].confirmada)
        self.assertEqual(resultado["facturacion_id"], "fact-existente")


class CheckoutAtomicoIntegracionTest(unittest.TestCase):
    """Una transacción real revierte sus escrituras en dos esquemas a la vez."""

    def _contar(self, esquema, tabla):
        with UnidadTrabajo() as unidad:
            unidad.conexion.select_db(unidad.esquemas[esquema])
            with unidad.conexion.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM {tabla}")
                return cursor.fetchone()["total"]

    def _primera_fila(self, esquema, consulta, parametros=()):
        with UnidadTrabajo() as unidad:
            unidad.conexion.select_db(unidad.esquemas[esquema])
            with unidad.conexion.cursor() as cursor:
                cursor.execute(consulta, parametros)
                return cursor.fetchone()

    def test_rollback_cruza_esquemas_sin_residuos(self):
        pedido = self._primera_fila("comercio", "SELECT id FROM pedidos LIMIT 1")
        entrega = self._primera_fila("operaciones", "SELECT id FROM entregas LIMIT 1")
        usuario = self._primera_fila("identidad", "SELECT id FROM usuarios LIMIT 1")

        if not pedido or not entrega or not usuario:
            self.skipTest("No hay datos reales para probar atomicidad.")

        pedidos_antes = self._contar("comercio", "pedido_historial")
        entregas_antes = self._contar("operaciones", "entrega_historial")
        facturacion_antes = self._contar("identidad", "datos_facturacion")

        with UnidadTrabajo() as unidad:
            unidad.conexion.select_db(unidad.esquemas["comercio"])
            with unidad.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO pedido_historial "
                    "(pedido_id, estado_nuevo, origen, comentario) "
                    "VALUES (%s, 'CREADO', 'SISTEMA', 'Atomicidad: se revierte.')",
                    (pedido["id"],),
                )
            unidad.conexion.select_db(unidad.esquemas["operaciones"])
            with unidad.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO entrega_historial "
                    "(entrega_id, estado_nuevo, comentario) "
                    "VALUES (%s, 'PENDIENTE', 'Atomicidad: se revierte.')",
                    (entrega["id"],),
                )
            unidad.conexion.select_db(unidad.esquemas["identidad"])
            with unidad.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO datos_facturacion "
                    "(id, usuario_id, tipo, dni, nombre_facturacion, es_predeterminado, estado) "
                    "VALUES (%s, %s, 'PERSONA', '00000000', 'Atomicidad', 0, 'ACTIVO')",
                    (str(uuid.uuid4()), usuario["id"]),
                )
            # Nunca se confirma: __exit__ debe revertir los tres esquemas.

        self.assertEqual(
            self._contar("comercio", "pedido_historial"), pedidos_antes
        )
        self.assertEqual(
            self._contar("operaciones", "entrega_historial"), entregas_antes
        )
        self.assertEqual(
            self._contar("identidad", "datos_facturacion"), facturacion_antes
        )


if __name__ == "__main__":
    unittest.main()
