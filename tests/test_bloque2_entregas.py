"""Pruebas del Bloque 2: servicios de entregas y repartidor + permisos HTTP."""

import unittest
from unittest.mock import patch

from app import create_app
from app.operaciones.services import ReglaOperativaError


class ServiciosAdmEntregasTest(unittest.TestCase):
    """Traduce los errores de negocio a ReglaEntregaError de la interfaz."""

    def test_errores_operativos_se_traducen_a_regla_entrega(self):
        from app.admin.entregas import services as entregas_services

        class ServiciosOperacionesFalsos:
            ReglaOperativaError = ReglaOperativaError

            @staticmethod
            def marcar_entrega_listo(*args, **kwargs):
                raise ReglaOperativaError("Transición no habilitada.")

            @staticmethod
            def listar_entregas_operativa(*args, **kwargs):
                return []

        with patch(
            "app.admin.entregas.services.operaciones_services",
            ServiciosOperacionesFalsos,
        ):
            with self.assertRaises(entregas_services.ReglaEntregaError):
                entregas_services.marcar_listo("a1", ["GERENTE"], "e1")

            self.assertEqual(
                entregas_services.listar_entregas({"estado": "LISTO"}), []
            )

    def test_enriquecimiento_de_detalle_no_modifica_datos(self):
        from app.admin.entregas.services import enriquecer_detalle

        detalle = {
            "estado": "EN_TRANSITO",
            "tipo_entrega": "DELIVERY_LOCAL",
            "pago_modalidad": "CONTRA_ENTREGA",
            "pago_estado": "PENDIENTE",
            "pago_metodo_nombre": "Efectivo",
            "transportista": {"estado": "EN_TRANSITO"},
            "incidencias": [{"estado": "ABIERTA"}],
        }
        enriquecido = enriquecer_detalle(detalle)
        self.assertEqual(enriquecido["estado_label"], "En tránsito")
        self.assertEqual(enriquecido["tipo_label"], "Delivery local")
        self.assertEqual(
            enriquecido["transportista"]["estado_label"], "En tránsito"
        )
        self.assertEqual(enriquecido["incidencias"][0]["estado_label"], "Abierta")
        self.assertIsNone(enriquecer_detalle(None))


class RepartidorServicioTest(unittest.TestCase):
    """El repartidor solo opera asignaciones propias; el service lo garantiza."""

    def test_aceptar_asignacion_resuelve_el_repartidor_desde_el_usuario(self):
        import app.operaciones.services as servicios_operaciones
        from app.operaciones.services import ReglaOperativaError

        class UoW:
            conexion = object()
            esquemas = {
                "comercio": "comercio_p",
                "operaciones": "operaciones_p",
                "identidad": "identidad_p",
            }

            def __enter__(self): return self
            def __exit__(self, *a): return False
            def confirmar(self): pass

        with patch.object(servicios_operaciones, "UnidadTrabajo", UoW):
            from app.operaciones import repositories as repos_ops
            with patch.object(repos_ops, "obtener_repartidor_por_usuario") as rep_usuario,\
                 patch.object(repos_ops, "obtener_asignacion_repartidor_entrega") as asignacion,\
                 patch.object(repos_ops, "actualizar_asignacion_estado") as actualizar:
                rep_usuario.return_value = {"id": "repartidor-1"}
                asignacion.return_value = {
                    "id": "asig-1", "estado": "ASIGNADA", "entrega_id": "e1",
                }
                actualizar.return_value = True
                resultado = servicios_operaciones.aceptar_asignacion("usuario-1", "e1")
                self.assertEqual(resultado["accion"], "ACEPTADA")
                rep_usuario.assert_called_once()
                asignacion.assert_called_once()

    def test_aceptar_asignacion_rechaza_entrega_ajena(self):
        import app.operaciones.services as servicios_operaciones
        from app.operaciones.services import ReglaOperativaError

        class UoW:
            conexion = object()
            esquemas = {"comercio": "c", "operaciones": "o", "identidad": "i"}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def confirmar(self): pass

        with patch.object(servicios_operaciones, "UnidadTrabajo", UoW):
            from app.operaciones import repositories as repos_ops
            with patch.object(repos_ops, "obtener_repartidor_por_usuario") as rep_usuario,\
                 patch.object(repos_ops, "obtener_asignacion_repartidor_entrega") as asignacion:
                rep_usuario.return_value = {"id": "repartidor-1"}
                asignacion.return_value = None
                with self.assertRaisesRegex(ReglaOperativaError, "no te está asignada"):
                    servicios_operaciones.aceptar_asignacion("usuario-1", "e1")


class PermisosHTTPEntregasTest(unittest.TestCase):
    """Las rutas POST del módulo exigen rol operativo en cada endpoint."""

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

    def test_get_entregas_permitido_para_roles_operativos(self):
        for rol in ("GERENTE", "ADMINISTRADOR", "PEDIDOS_LOGISTICA"):
            with self.subTest(rol=rol):
                self.assertEqual(
                    self.cliente_con_rol(rol).get("/admin/entregas/").status_code,
                    200,
                )

    def test_get_entregas_rechazado_para_repartidor_y_cliente(self):
        for rol in ("REPARTIDOR", None):
            with self.subTest(rol=rol):
                self.assertEqual(
                    self.cliente_con_rol(rol).get("/admin/entregas/").status_code,
                    403,
                )

    def test_acciones_post_respetan_rol_en_todos_los_verbos(self):
        destinos = ("listo", "recojo", "programar", "asignar", "iniciar",
                    "confirmar", "recojo-confirmar", "incidencia", "cancelar",
                    "envio", "pago-anticipado")
        for accion in destinos:
            with self.subTest(accion=accion), patch(
                "app.admin.entregas.routes.marcar_listo",
                return_value={"ok": True},
            ):
                respuesta = self.cliente_con_rol("REPARTIDOR").post(
                    f"/admin/entregas/e-1/{accion}"
                )
                self.assertEqual(respuesta.status_code, 403)

    def test_sin_sesion_redirige_login(self):
        respuesta = self.app.test_client().get("/admin/entregas/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])

    def test_planilla_repartidores_carga_para_operativo(self):
        self.assertEqual(
            self.cliente_con_rol("GERENTE").get(
                "/admin/entregas/repartidores"
            ).status_code,
            200,
        )

    def test_detalle_inexistente_responde_404(self):
        self.assertEqual(
            self.cliente_con_rol("GERENTE").get(
                "/admin/entregas/entrega-no-existente"
            ).status_code,
            404,
        )


class PermisosHTTPRepartidorTest(unittest.TestCase):
    """El panel del repartidor exige rol REPARTIDOR y oculta el admin."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def cliente_con_rol(self, rol):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "actor-prueba",
                "correo": "repartidor@example.test",
                "roles": [rol] if rol else [],
            })
        return cliente

    def test_lista_solo_para_repartidor(self):
        self.assertEqual(
            self.cliente_con_rol("REPARTIDOR").get("/repartidor/").status_code,
            200,
        )

    def test_otros_roles_no_acceden(self):
        for rol in ("GERENTE", "PEDIDOS_LOGISTICA", None):
            with self.subTest(rol=rol):
                self.assertEqual(
                    self.cliente_con_rol(rol).get("/repartidor/").status_code,
                    403,
                )

    def test_acciones_repartidor_exigen_su_rol(self):
        for accion in ("aceptar", "iniciar", "confirmar"):
            with self.subTest(accion=accion):
                self.assertEqual(
                    self.cliente_con_rol("GERENTE").post(
                        f"/repartidor/e-1/{accion}"
                    ).status_code,
                    403,
                )


if __name__ == "__main__":
    unittest.main()