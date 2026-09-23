"""Pruebas de permisos, reglas y rollback del módulo Pedidos."""

import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from app.admin.pedidos import services
from app.admin.pedidos.services import ReglaPedidoError


class UnidadTrabajoFalsa:
    """Dobla la frontera transaccional sin escribir datos de producción."""

    instancias = []

    def __init__(self):
        self.conexion = object()
        self.esquemas = {
            "comercio": "comercio_prueba",
            "operaciones": "operaciones_prueba",
            "identidad": "identidad_prueba",
        }
        self.confirmada = False
        self.revertida = False
        self.__class__.instancias.append(self)

    def __enter__(self):
        return self

    def confirmar(self):
        self.confirmada = True

    def __exit__(self, tipo_error, error, traza):
        if tipo_error is not None or not self.confirmada:
            self.revertida = True
        return False


class ReglasServicioPedidosTest(unittest.TestCase):
    """Valida la coordinación Service -> Repository y su atomicidad."""

    def setUp(self):
        UnidadTrabajoFalsa.instancias.clear()
        self.parche_uow = patch(
            "app.admin.pedidos.services.UnidadTrabajo", UnidadTrabajoFalsa
        )
        self.parche_uow.start()
        self.repositorio = patch(
            "app.admin.pedidos.services.repositories"
        ).start()
        self.addCleanup(patch.stopall)
        self.repositorio.actualizar_estado_pedido.return_value = True
        self.repositorio.actualizar_entrega_a_preparacion.return_value = True

    @staticmethod
    def contexto(estado="CREADO", modalidad="CONTRA_ENTREGA",
                 pago_estado="PENDIENTE", entrega_estado="PENDIENTE"):
        return {
            "pedido": {"id": "pedido-1", "numero_pedido": "PED-1", "estado": estado},
            "pago": {"id": "pago-1", "modalidad": modalidad,
                     "estado": pago_estado, "monto": 10},
            "entrega": {"id": "entrega-1", "tipo_entrega": "DELIVERY_LOCAL",
                        "estado": entrega_estado},
        }

    def test_roles_operativos_pueden_confirmar(self):
        for rol in ("GERENTE", "ADMINISTRADOR", "PEDIDOS_LOGISTICA"):
            with self.subTest(rol=rol):
                self.repositorio.bloquear_contexto_operativo.return_value = (
                    self.contexto()
                )
                resultado = services.confirmar_pedido(
                    "pedido-1", "actor-1", [rol]
                )
                self.assertEqual(resultado["estado"], "CONFIRMADO")
                self.assertTrue(UnidadTrabajoFalsa.instancias[-1].confirmada)

    def test_roles_no_autorizados_no_transicionan(self):
        for rol in ("INVENTARIO", "REPARTIDOR", "CLIENTE"):
            with self.subTest(rol=rol):
                with self.assertRaises(ReglaPedidoError):
                    services.confirmar_pedido("pedido-1", "actor-1", [rol])
        self.repositorio.bloquear_contexto_operativo.assert_not_called()

    def test_pago_anticipado_pendiente_es_rechazado(self):
        self.repositorio.bloquear_contexto_operativo.return_value = self.contexto(
            modalidad="ANTICIPADO", pago_estado="PENDIENTE"
        )
        with self.assertRaisesRegex(ReglaPedidoError, "debe estar pagado"):
            services.confirmar_pedido("pedido-1", "actor-1", ["GERENTE"])
        self.repositorio.actualizar_estado_pedido.assert_not_called()

    def test_repeticion_no_duplica_historial(self):
        self.repositorio.bloquear_contexto_operativo.return_value = self.contexto(
            estado="CONFIRMADO"
        )
        with self.assertRaisesRegex(ReglaPedidoError, "ya no se encuentra"):
            services.confirmar_pedido("pedido-1", "actor-1", ["GERENTE"])
        self.repositorio.insertar_historial_pedido.assert_not_called()

    def test_preparacion_sincroniza_ambos_historiales(self):
        self.repositorio.bloquear_contexto_operativo.return_value = self.contexto(
            estado="CONFIRMADO", modalidad="PAGO_EN_LOCAL"
        )
        services.iniciar_preparacion(
            "pedido-1", "actor-1", ["PEDIDOS_LOGISTICA"]
        )
        self.repositorio.actualizar_entrega_a_preparacion.assert_called_once()
        self.repositorio.insertar_historial_entrega.assert_called_once()
        self.repositorio.insertar_historial_pedido.assert_called_once()
        self.assertTrue(UnidadTrabajoFalsa.instancias[-1].confirmada)

    def test_fallo_intermedio_provoca_rollback(self):
        self.repositorio.bloquear_contexto_operativo.return_value = self.contexto(
            estado="CONFIRMADO", modalidad="PAGO_EN_LOCAL"
        )
        self.repositorio.insertar_historial_entrega.side_effect = RuntimeError(
            "fallo controlado"
        )
        with self.assertRaises(RuntimeError):
            services.iniciar_preparacion(
                "pedido-1", "actor-1", ["GERENTE"]
            )
        unidad = UnidadTrabajoFalsa.instancias[-1]
        self.assertFalse(unidad.confirmada)
        self.assertTrue(unidad.revertida)
        self.repositorio.insertar_historial_pedido.assert_not_called()


class PermisosHTTPPedidosTest(unittest.TestCase):
    """Comprueba que la autorización existe en los endpoints POST."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def cliente_con_rol(self, rol):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "actor-prueba",
                "correo": "actor@example.test",
                "roles": [rol] if rol else [],
            })
        return cliente

    def test_roles_permitidos_llegan_al_servicio(self):
        for rol in ("GERENTE", "ADMINISTRADOR", "PEDIDOS_LOGISTICA"):
            with self.subTest(rol=rol), patch(
                "app.admin.pedidos.routes.confirmar_pedido"
            ) as confirmar:
                confirmar.return_value = {"ok": True, "estado": "CONFIRMADO"}
                respuesta = self.cliente_con_rol(rol).post(
                    "/admin/pedidos/pedido-1/confirmar"
                )
                self.assertEqual(respuesta.status_code, 302)
                confirmar.assert_called_once()

    def test_roles_prohibidos_reciben_403(self):
        for rol in ("INVENTARIO", "REPARTIDOR", None):
            with self.subTest(rol=rol), patch(
                "app.admin.pedidos.routes.confirmar_pedido"
            ) as confirmar:
                respuesta = self.cliente_con_rol(rol).post(
                    "/admin/pedidos/pedido-1/confirmar"
                )
                self.assertEqual(respuesta.status_code, 403)
                confirmar.assert_not_called()

    def test_sin_sesion_redirige_al_login(self):
        respuesta = self.app.test_client().post(
            "/admin/pedidos/pedido-1/confirmar"
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])


if __name__ == "__main__":
    unittest.main()
