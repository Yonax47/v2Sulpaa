"""Pruebas de integración de lectura contra MySQL y render Jinja real."""

import unittest

from app import create_app
from app.admin.pedidos import repositories as repositorios_pedidos
from app.admin.pedidos.services import listar_pedidos_admin
from app.shared.unit_of_work import UnidadTrabajo


class LecturasRealesTest(unittest.TestCase):
    """Valida navegación completa sin alterar pedidos operativos existentes."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        pedidos = listar_pedidos_admin({})
        if not pedidos:
            raise unittest.SkipTest("No existen pedidos reales para integrar.")
        cls.pedido = pedidos[0]

    def cliente_autenticado(self, usuario_id, roles):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": usuario_id,
                "correo": "prueba-integracion@example.test",
                "roles": roles,
            })
        return cliente

    def test_listado_busqueda_filtros_y_detalle_admin(self):
        cliente = self.cliente_autenticado("actor-admin", ["GERENTE"])
        numero = self.pedido["numero_pedido"]
        lista = cliente.get(
            "/admin/pedidos/",
            query_string={"q": numero, "estado": self.pedido["estado"]},
        )
        detalle = cliente.get(f"/admin/pedidos/{self.pedido['id']}")
        self.assertEqual(lista.status_code, 200)
        self.assertIn(numero.encode(), lista.data)
        self.assertEqual(detalle.status_code, 200)
        self.assertIn(numero.encode(), detalle.data)

    def test_logistica_accede_a_pedidos_pero_no_dashboard(self):
        cliente = self.cliente_autenticado("actor-logistica", ["PEDIDOS_LOGISTICA"])
        self.assertEqual(cliente.get("/admin/pedidos/").status_code, 200)
        self.assertEqual(cliente.get("/admin/dashboard").status_code, 403)

    def test_cliente_ve_sus_pedidos_y_propiedad_sigue_protegida(self):
        propietario = self.cliente_autenticado(self.pedido["usuario_id"], [])
        ajeno = self.cliente_autenticado("usuario-que-no-es-propietario", [])
        lista = propietario.get("/pedidos")
        detalle = propietario.get(f"/pedidos/{self.pedido['id']}")
        detalle_ajeno = ajeno.get(f"/pedidos/{self.pedido['id']}")
        self.assertEqual(lista.status_code, 200)
        self.assertEqual(detalle.status_code, 200)
        self.assertEqual(detalle_ajeno.status_code, 404)

    def test_regresion_navegacion_cliente_y_dashboard(self):
        cliente = self.cliente_autenticado(self.pedido["usuario_id"], [])
        for ruta in ("/", "/tienda", "/checkout", "/pedidos"):
            with self.subTest(ruta=ruta):
                self.assertEqual(cliente.get(ruta).status_code, 200)

        gerente = self.cliente_autenticado("actor-admin", ["GERENTE"])
        self.assertEqual(gerente.get("/admin/dashboard").status_code, 200)

    def test_logout_conserva_flujo_existente(self):
        cliente = self.cliente_autenticado(self.pedido["usuario_id"], [])
        salida = cliente.post("/identidad/logout")
        posterior = cliente.get("/pedidos")
        self.assertEqual(salida.status_code, 302)
        self.assertEqual(posterior.status_code, 302)
        self.assertIn("/identidad/login", posterior.headers["Location"])

    def test_css_responsive_del_modulo(self):
        cliente = self.app.test_client()
        respuesta = cliente.get("/static/css/pages/admin-orders.css")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b"@media (max-width: 760px)", respuesta.data)
        self.assertIn(b"@media (max-width: 540px)", respuesta.data)
        respuesta.close()

    def test_historial_real_cubre_todos_los_pedidos(self):
        """Comprueba en MySQL la fuente oficial utilizada por KPI-04."""
        with UnidadTrabajo() as unidad:
            comercio = unidad.esquemas["comercio"]
            with unidad.conexion.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) total FROM {comercio}.pedidos")
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"SELECT COUNT(DISTINCT pedido_id) total "
                    f"FROM {comercio}.pedido_historial"
                )
                con_historial = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"""
                    SELECT COUNT(*) total FROM {comercio}.pedidos AS p
                    WHERE NOT EXISTS (
                        SELECT 1 FROM {comercio}.pedido_historial AS h
                        WHERE h.pedido_id = p.id
                    )
                    """
                )
                sin_historial = int(cursor.fetchone()["total"])
        self.assertEqual(total, con_historial)
        self.assertEqual(sin_historial, 0)

    def test_rollback_mysql_abarca_comercio_y_operaciones(self):
        """Demuestra rollback real de escrituras calificadas entre esquemas."""
        candidato = next(
            (
                pedido for pedido in listar_pedidos_admin({})
                if pedido["estado"] == "CREADO"
                and pedido.get("entrega_estado") == "PENDIENTE"
            ),
            None,
        )
        if not candidato:
            self.skipTest("No existe un pedido pendiente apto para probar rollback.")

        with UnidadTrabajo() as lectura:
            contexto_antes = repositorios_pedidos.bloquear_contexto_operativo(
                lectura.conexion, lectura.esquemas, candidato["id"]
            )
            historial_antes = repositorios_pedidos.obtener_historial_pedido(
                lectura.conexion, lectura.esquemas, candidato["id"]
            )

        # No se llama confirmar(): __exit__ revierte pedido, entrega y ambos
        # historiales aun cuando pertenecen a esquemas distintos.
        with UnidadTrabajo() as unidad:
            repositorios_pedidos.actualizar_estado_pedido(
                unidad.conexion,
                unidad.esquemas,
                candidato["id"],
                "CREADO",
                "CONFIRMADO",
            )
            repositorios_pedidos.insertar_historial_pedido(
                unidad.conexion,
                unidad.esquemas,
                candidato["id"],
                "CREADO",
                "CONFIRMADO",
                None,
                "SISTEMA",
                "Prueba transaccional destinada a rollback.",
            )
            repositorios_pedidos.actualizar_entrega_a_preparacion(
                unidad.conexion,
                unidad.esquemas,
                contexto_antes["entrega"]["id"],
            )
            repositorios_pedidos.insertar_historial_entrega(
                unidad.conexion,
                unidad.esquemas,
                contexto_antes["entrega"]["id"],
                None,
                "Prueba transaccional destinada a rollback.",
            )

        with UnidadTrabajo() as verificacion:
            contexto_despues = repositorios_pedidos.bloquear_contexto_operativo(
                verificacion.conexion, verificacion.esquemas, candidato["id"]
            )
            historial_despues = repositorios_pedidos.obtener_historial_pedido(
                verificacion.conexion, verificacion.esquemas, candidato["id"]
            )

        self.assertEqual(contexto_despues["pedido"]["estado"], "CREADO")
        self.assertEqual(contexto_despues["entrega"]["estado"], "PENDIENTE")
        self.assertEqual(len(historial_despues), len(historial_antes))


if __name__ == "__main__":
    unittest.main()
