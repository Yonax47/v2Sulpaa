"""Integración real (MySQL) del Bloque 2 sin alterar datos de producción.

Estrategia: cada caso abre una UnidadTrabajo real y ejecuta las escrituras
de los repositorios SIN confirmar; el __exit__ revierte todo, de modo que el
flujo completo (LISTO -> PROGRAMADO -> EN_TRANSITO -> ENTREGADO, recojo
disponible, seguimiento de envío) se valida contra el esquema real y queda
intacto al terminar.
"""

import unittest

from app import create_app
from app.admin.services import resumen_dashboard
from app.operaciones import repositories as repos
from app.shared.unit_of_work import UnidadTrabajo


def listar_entregas(estado=None, tipo=None):
    with UnidadTrabajo() as unidad:
        return repos.listar_entregas_admin(
            unidad.conexion, unidad.esquemas, estado=estado, tipo=tipo
        )


class FlujoEntregaIntegracionTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def test_flujo_completo_delivery_se_revierte(self):
        candidata = next(
            (
                entrega for entrega in listar_entregas(tipo="DELIVERY_LOCAL")
                if entrega["estado"] in ("EN_PREPARACION", "LISTO")
            ),
            None,
        )
        if not candidata:
            self.skipTest("No existe una entrega DELIVERY_LOCAL no entregada")

        entrega_id = candidata["id"]
        with UnidadTrabajo() as unidad:
            contexto = repos.bloquear_entrega_operativa(
                unidad.conexion, unidad.esquemas, entrega_id
            )
            self.assertIsNotNone(contexto)
            inicio = contexto["entrega"]["estado"]

            # 1) Preparar: EN_PREPARACION/LISTO -> LISTO
            if inicio != "LISTO":
                repos.actualizar_estado_entrega(
                    unidad.conexion, unidad.esquemas, entrega_id,
                    inicio, "LISTO",
                )
                repos.insertar_historial_entrega(
                    unidad.conexion, unidad.esquemas, entrega_id,
                    inicio, "LISTO", "actor-prueba",
                    "Prueba integración revertida 1/4.",
                )
            # 2) Programar
            repos.actualizar_estado_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                "LISTO", "PROGRAMADO",
                fecha_programada="2026-12-01 10:00:00",
            )
            repos.insertar_historial_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                "LISTO", "PROGRAMADO", "actor-prueba",
                "Prueba integración revertida 2/4.",
            )
            # 3) En tránsito
            repos.actualizar_estado_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                "PROGRAMADO", "EN_TRANSITO",
            )
            repos.actualizar_iniciado_delivery(
                unidad.conexion, unidad.esquemas, entrega_id
            )
            repos.insertar_historial_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                "PROGRAMADO", "EN_TRANSITO", "actor-prueba",
                "Prueba integración revertida 3/4.",
            )
            # 4) Entregar
            repos.actualizar_estado_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                "EN_TRANSITO", "ENTREGADO", completar=True,
            )
            repos.actualizar_entregado_delivery(
                unidad.conexion, unidad.esquemas, entrega_id
            )
            repos.insertar_historial_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                "EN_TRANSITO", "ENTREGADO", "actor-prueba",
                "Prueba integración revertida 4/4.",
            )
            repos.limpiar_codigo_cliente_entrega(
                unidad.conexion, unidad.esquemas, entrega_id
            )

        # La transacción nunca se confirmó: el estado original debe seguir ahí.
        with UnidadTrabajo() as verificacion:
            detalle_final = repos.obtener_entrega_admin(
                verificacion.conexion, verificacion.esquemas, entrega_id
            )
            fin = detalle_final["estado"]

        self.assertEqual(fin, inicio)
        self.assertIsNone(detalle_final["completado_en"])
        self.assertIsNone(detalle_final["fecha_programada"])

    def test_rollback_historial_sin_fantasma(self):
        candidata = next(
            (
                entrega for entrega in listar_entregas()
                if entrega["estado"] in ("EN_PREPARACION", "LISTO")
            ),
            None,
        )
        if not candidata:
            self.skipTest("No existe una entrega no entregada")

        with UnidadTrabajo() as antes:
            antes_total = len(
                repos.obtener_entrega_admin(
                    antes.conexion, antes.esquemas, candidata["id"]
                )["historial"]
            )

        with UnidadTrabajo() as unidad:
            repos.insertar_historial_entrega(
                unidad.conexion, unidad.esquemas, candidata["id"],
                candidata["estado"], candidata["estado"], "actor-prueba",
                "Rollback garantizado de historial.",
            )

        with UnidadTrabajo() as despues:
            despues_total = len(
                repos.obtener_entrega_admin(
                    despues.conexion, despues.esquemas, candidata["id"]
                )["historial"]
            )

        self.assertEqual(despues_total, antes_total)

    def test_recojo_disponible_evalua_como_listo_para_recojo(self):
        candidata = next(
            (
                entrega for entrega in listar_entregas(tipo="RECOJO_LOCAL")
                if entrega["estado"] == "EN_PREPARACION"
            ),
            None,
        )
        if not candidata:
            self.skipTest("No existe una entrega RECOJO_LOCAL EN_PREPARACION")

        with UnidadTrabajo() as unidad:
            repos.actualizar_estado_entrega(
                unidad.conexion, unidad.esquemas, candidata["id"],
                "EN_PREPARACION", "LISTO_PARA_RECOJO",
            )
            repos.insertar_historial_entrega(
                unidad.conexion, unidad.esquemas, candidata["id"],
                "EN_PREPARACION", "LISTO_PARA_RECOJO", "actor-prueba",
                "Recojo disponible (prueba revertida).",
            )
            repos.actualizar_notificado_recojo(
                unidad.conexion, unidad.esquemas, candidata["id"]
            )

        with UnidadTrabajo() as verificacion:
            detalle = repos.obtener_entrega_admin(
                verificacion.conexion, verificacion.esquemas, candidata["id"]
            )

        self.assertEqual(detalle["estado"], "EN_PREPARACION")
        self.assertIsNone(detalle["recojo"].get("notificado_en"))


class KPIsDashboardIntegracionTest(unittest.TestCase):
    """Los KPI del Bloque 2 leen métricas reales sin inventar porcentajes."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.resumen = resumen_dashboard()

    def test_kpis_instrumentados_tienen_valor_real(self):
        instrumentados = {
            kpi["codigo"]: kpi["valor"]
            for kpi in self.resumen["kpis_funcionales"]
            if kpi["valor"] is not None
        }
        for codigo in ("KPI-01", "KPI-04", "KPI-07", "KPI-08"):
            self.assertIn(codigo, instrumentados)
            self.assertGreaterEqual(instrumentados[codigo], 0.0)

    def test_kpi_09_hook_permanece_seguro_sin_tabla(self):
        kpi_09 = next(
            k for k in self.resumen["kpis_funcionales"] if k["codigo"] == "KPI-09"
        )
        self.assertIsNone(kpi_09["valor"])
        self.assertEqual(kpi_09["estado"], "pendiente")

    def test_dashboard_renders_kpis(self):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "actor",
                "correo": "gerente@example.test",
                "roles": ["GERENTE"],
            })
        respuesta = cliente.get("/admin/dashboard")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b"KPI-01", respuesta.data)
        self.assertIn(b"KPI-07", respuesta.data)
        self.assertIn(b"KPI-08", respuesta.data)


class ExportableViewsIntegracionTest(unittest.TestCase):
    """Las vistas listado/detalle/repartos leen la BD sin escribir."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def cliente_con_rol(self, roles, correo="actor@example.test"):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "actor-integracion",
                "correo": correo,
                "roles": roles,
            })
        return cliente

    def test_listado_y_detalle_real(self):
        reales = listar_entregas()
        if not reales:
            self.skipTest("No existen entregas reales para integrar.")
        cliente = self.cliente_con_rol(["PEDIDOS_LOGISTICA"])
        lista = cliente.get("/admin/entregas/")
        self.assertEqual(lista.status_code, 200)
        detalle = cliente.get(f"/admin/entregas/{reales[0]['id']}")
        self.assertEqual(detalle.status_code, 200)

    def test_repados_vacios_para_repartidor_sin_asignacion(self):
        cliente = self.cliente_con_rol(
            ["REPARTIDOR"], correo="repartidor@example.test"
        )
        # El repartidor no existe aún, el service reporta estado sin datos.
        self.assertEqual(cliente.get("/repartidor/").status_code, 200)


if __name__ == "__main__":
    unittest.main()