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


class RedireccionesLoginYConfirmacionTest(unittest.TestCase):
    """Tareas 1-2 del ajuste final: destino del login y del confirmar."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def _cliente_con_sesion(self, roles, correo="actor@example.test"):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "actor",
                "correo": correo,
                "roles": roles,
            })
        return cliente

    # --------------------------------------------------------
    # Tarea 1: el login redirige según ROLES ACTIVOS
    # --------------------------------------------------------

    def _login_post(self, roles_recibidos):
        from unittest.mock import patch
        with patch(
            "app.identidad.routes.autenticar_usuario",
            return_value={
                "ok": True,
                "usuario": {
                    "id": "actor",
                    "correo": "actor@example.test",
                },
            },
        ), patch(
            "app.identidad.routes.obtener_roles_usuario",
            return_value=roles_recibidos,
        ):
            return self.app.test_client().post(
                "/identidad/login",
                data={"correo": "actor@example.test",
                      "password": "clave"},
            )

    def test_login_repartidor_va_a_su_panel(self):
        respuesta = self._login_post(["REPARTIDOR"])
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/repartidor/", respuesta.headers["Location"])

    def test_login_repartidor_con_rol_admin_va_al_admin(self):
        # Prioridad multirol: admin gana sobre repartidor.
        respuesta = self._login_post(["REPARTIDOR", "GERENTE"])
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/admin/", respuesta.headers["Location"])

    def test_login_cliente_va_al_inicio(self):
        for roles in ([], ["CLIENTE"]):
            with self.subTest(roles=roles):
                respuesta = self._login_post(roles)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn("/", respuesta.headers["Location"])
                self.assertNotIn("/repartidor/",
                                 respuesta.headers["Location"])
                self.assertNotIn("/admin/",
                                 respuesta.headers["Location"])

    def test_get_login_con_sesion_de_repartidor_redirige_a_repartos(self):
        cliente = self._cliente_con_sesion(["REPARTIDOR"])
        respuesta = cliente.get("/identidad/login")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/repartidor/", respuesta.headers["Location"])

    def test_get_login_con_sesion_cliente_redirige_a_inicio(self):
        cliente = self._cliente_con_sesion(["CLIENTE"])
        respuesta = cliente.get("/identidad/login")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/", respuesta.headers["Location"])
        self.assertNotIn("/repartidor/", respuesta.headers["Location"])

    # --------------------------------------------------------
    # Tarea 2: tras confirmar la entrega no debe haber 404.
    # --------------------------------------------------------

    def test_confirmar_entrega_ok_redirige_a_repartos(self):
        from unittest.mock import patch
        from app.repartidor.routes import confirmar_entrega
        with patch(
            "app.repartidor.routes.confirmar_entrega",
            return_value={"ok": True, "mensaje": "correcta"},
        ):
            cliente = self._cliente_con_sesion(["REPARTIDOR"])
            respuesta = cliente.post(
                "/repartidor/e-1/confirmar",
                data={"codigo_cliente": "1234"},
            )
            self.assertEqual(respuesta.status_code, 302)
            self.assertIn("/repartidor/", respuesta.headers["Location"])

    def test_confirmar_entrega_error_vuelve_al_detalle(self):
        from unittest.mock import patch
        from app.repartidor.routes import ReglaOperativaError
        with patch(
            "app.repartidor.routes.confirmar_entrega",
            side_effect=ReglaOperativaError("código no coincide"),
        ):
            cliente = self._cliente_con_sesion(["REPARTIDOR"])
            respuesta = cliente.post(
                "/repartidor/e-1/confirmar",
                data={"codigo_cliente": "0000"},
            )
            self.assertIn(respuesta.status_code, (200, 302))
            # Nunca un 404: la entrega sigue activa y el detalle existe.
            self.assertNotEqual(respuesta.status_code, 404)

    def test_confirmar_entrega_ok_conserva_flash(self):
        from unittest.mock import patch
        from app.repartidor.routes import confirmar_entrega
        with patch(
            "app.repartidor.routes.confirmar_entrega",
            return_value={"ok": True, "mensaje": "correcta"},
        ):
            cliente = self._cliente_con_sesion(["REPARTIDOR"])
            respuesta = cliente.post(
                "/repartidor/e-1/confirmar",
                data={"codigo_cliente": "1234"},
                follow_redirects=True,
            )
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn(
                "Entrega confirmada correctamente.".encode("utf-8"),
                respuesta.data,
            )


class CabeceraRepartidorLogoutTest(unittest.TestCase):
    """Tarea A del ajuste visual final: cabecera profesional del repartidor.

    Reutiliza el logout REAL de identidad (POST /identidad/logout) y no
    debe exponer enlaces del panel administrativo.
    """

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def _cliente_con_sesion(self, correo="repartidor@example.test"):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "r-1",
                "correo": correo,
                "roles": ["REPARTIDOR"],
            })
        return cliente

    def _listado(self):
        with patch(
            "app.repartidor.routes.listar_repartos_repartidor",
            return_value={
                "activas": [{
                    "numero_pedido": "P-100",
                    "cliente_nombre": "Cliente Uno",
                    "cliente_correo": "",
                    "entrega_estado": "PROGRAMADO",
                    "entrega_estado_label": "Programado",
                    "asignacion_estado_label": "Asignada",
                    "fecha_programada": None,
                    "entrega_id": "e-1",
                }],
                "historial": [],
            },
        ):
            return self._cliente_con_sesion().get("/repartidor/")

    def test_listado_renderiza_cabecera_y_boton_cerrar_sesion(self):
        respuesta = self._listado()
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.data.decode("utf-8")
        self.assertIn("Panel del repartidor", html)
        self.assertIn("Cerrar sesión", html)
        self.assertIn('action="/identidad/logout"', html)
        self.assertIn('method="POST"', html)
        self.assertIn("repartidor@example.test", html)

    def test_listado_sin_enlaces_administrativos(self):
        respuesta = self._listado()
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.data.decode("utf-8")
        self.assertNotIn("href=\"/admin", html)
        self.assertNotIn("href=\"/admin/", html)
        self.assertNotIn("/admin/", html)

    def test_detalle_renderiza_cabecera_y_cerrar_sesion(self):
        with patch(
            "app.repartidor.routes.obtener_detalle_reparto_repartidor",
            return_value={
                "numero_pedido": "P-100",
                "entrega_id": "e-1",
                "cliente_nombre": "Cliente Uno",
                "cliente_correo": "",
                "cliente_telefono": "999",
                "pedido_total": 25,
                "entrega_estado": "PROGRAMADO",
                "entrega_estado_label": "Programado",
                "asignacion_estado": "ASIGNADA",
                "asignacion_estado_label": "Asignada",
                "fecha_programada": None,
                "asignado_en": None,
                "aceptado_en": None,
                "costo_cobrado_cliente": 3,
                "delivery": None,
                "tipo_entrega": "DELIVERY_LOCAL",
            },
        ):
            respuesta = self._cliente_con_sesion().get("/repartidor/e-1")
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.data.decode("utf-8")
        self.assertIn("Panel del repartidor", html)
        self.assertIn("Cerrar sesión", html)
        self.assertIn('action="/identidad/logout"', html)
        self.assertNotIn("href=\"/admin", html)

    def test_logout_posteado_cierra_sesion_y_redirige_al_login(self):
        cliente = self._cliente_con_sesion()
        with cliente.session_transaction() as sesion:
            self.assertTrue(sesion.get("autenticado"))
        respuesta = cliente.post("/identidad/logout")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])
        with cliente.session_transaction() as sesion:
            self.assertFalse(sesion.get("autenticado", False))

    def test_logout_no_acepta_get(self):
        cliente = self._cliente_con_sesion()
        respuesta = cliente.get("/identidad/logout")
        self.assertEqual(respuesta.status_code, 405)


if __name__ == "__main__":
    unittest.main()