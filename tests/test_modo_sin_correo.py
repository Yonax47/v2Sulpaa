"""Modo productivo sin correo; pruebas sin red, secretos ni bases reales."""

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from app import create_app
from app.config.email import configurar_email
from app.identidad import email_verification as correo, repositories as identidad
from app.identidad import services as identidad_servicios
from app.admin.usuarios import repositories as admin
from app.operaciones import repositories as operaciones
from app.comercio import services as comercio
from app.shared.decorators import correo_verificado_required, admin_required


class ModoSinCorreoTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True, OMITIR_SEGURIDAD_EN_PRUEBAS=True,
            EMAIL_VERIFICATION_REQUIRED=False, MAIL_ENABLED=False,
            MAIL_PAYLOAD_ENCRYPTION_KEY="", MAIL_RATE_LIMIT_KEY="",
        )

    def test_configuracion_explicita_sin_claves(self):
        with patch.dict("os.environ", {
            "EMAIL_VERIFICATION_REQUIRED": "0", "MAIL_ENABLED": "0",
        }, clear=True):
            configurar_email(self.app)
        self.assertFalse(self.app.config["EMAIL_VERIFICATION_REQUIRED"])
        self.assertFalse(self.app.config["MAIL_ENABLED"])

    def test_sin_correo_no_genera_tokens_ni_consulta_tablas_de_correo(self):
        with self.app.app_context(), patch.object(correo.secrets, "token_urlsafe") as token, patch.object(
            correo.email_repositories, "consumir_token"
        ) as consumir, patch.object(correo, "consumir_limites_persistentes") as limites:
            self.assertIsNone(correo.preparar_solicitud("u", "u@sulpaa.test", "ANA"))
            self.assertEqual(correo.confirmar("token")["estado"], "DESACTIVADO")
            correo.solicitar_reenvio("u@sulpaa.test", "192.0.2.1")
        token.assert_not_called()
        consumir.assert_not_called()
        limites.assert_not_called()

    def test_politica_no_bloquea_ni_verifica_cuentas(self):
        with self.app.app_context():
            for requerido in (False, True):
                self.assertEqual(correo.estado_cuenta(False, requerido), "NO_REQUERIDO")
            self.assertEqual(correo.estado_cuenta(True, True), "VERIFICADO")
            self.app.config["EMAIL_VERIFICATION_REQUIRED"] = True
            self.assertEqual(correo.estado_cuenta(False, True), "PENDIENTE_OBLIGATORIO")

    def test_activado_sigue_exigiendo_configuracion_criptografica(self):
        with self.app.app_context():
            self.app.config["EMAIL_VERIFICATION_REQUIRED"] = True
            with self.assertRaises(RuntimeError):
                correo.preparar_solicitud("u", "u@sulpaa.test", "ANA")

    def test_endpoints_correo_desactivados(self):
        client = self.app.test_client()
        for ruta in ("/identidad/verificacion", "/identidad/verificacion/pendiente"):
            self.assertEqual(client.get(ruta).status_code, 404)
        self.assertEqual(client.post("/identidad/verificacion/reenviar").status_code, 404)

    def test_registro_redirige_login_sin_pantalla_de_correo(self):
        with patch("app.identidad.routes.registrar_usuario", return_value={"ok": True}):
            respuesta = self.app.test_client().post("/identidad/registro", data={})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])

    def test_alta_publica_verifica_dni_sin_fernet_y_sin_solicitud(self):
        with self.app.app_context(), patch.object(
            identidad_servicios, "buscar_usuario_por_correo", return_value=None
        ), patch.object(identidad_servicios, "buscar_perfil_por_dni", return_value=None), patch.object(
            identidad_servicios, "verificar_dni_registro", return_value={
                "ok": True, "persona": {"nombres": "ANA", "apellido_paterno": "PRUEBA", "apellido_materno": "FICTICIA"},
            }
        ) as dni, patch.object(identidad_servicios.bcrypt, "hashpw", return_value=b"hash"), patch.object(
            identidad_servicios, "crear_usuario_y_perfil"
        ) as crear:
            resultado = identidad_servicios.registrar_usuario(
                "u@sulpaa.test", "PasswordSeguro123!", "ignorado", "ignorado", None,
                "12345678", "999999999",
            )
        self.assertTrue(resultado["ok"])
        self.assertFalse(resultado["correo_pendiente"])
        self.assertIsNone(crear.call_args.kwargs["verificacion_correo"])
        dni.assert_called_once_with("12345678", comprobar_duplicado=False)

    def test_login_pendiente_permitido_sin_fingir_verificado(self):
        client = self.app.test_client()
        with patch("app.identidad.routes.autenticar_usuario", return_value={
            "ok": True, "usuario": {"id": "u", "correo": "u@sulpaa.test",
                                     "correo_verificado": False, "requiere_verificacion_correo": True},
        }), patch("app.identidad.routes.obtener_roles_usuario", return_value=["CLIENTE"]):
            respuesta = client.post("/identidad/login", data={"correo": "u@sulpaa.test", "password": "sintetica"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertNotIn("verificacion", respuesta.headers["Location"])
        with client.session_transaction() as sesion:
            self.assertTrue(sesion["autenticado"])
            self.assertFalse(sesion["correo_verificado"])

    def test_decoradores_permiten_compra_y_admin_solo_en_modo_desactivado(self):
        @self.app.route("/prueba-compra")
        @correo_verificado_required
        def compra():
            return "permitido"

        @self.app.route("/prueba-admin")
        @admin_required
        def administracion():
            return "permitido"

        client = self.app.test_client()
        with client.session_transaction() as sesion:
            sesion.update(autenticado=True, usuario_id="u", roles=["ADMINISTRADOR"],
                          correo_verificado=False, requiere_verificacion_correo=True)
        for ruta in ("/prueba-compra", "/prueba-admin"):
            self.assertEqual(client.get(ruta).status_code, 200)
        self.app.config["EMAIL_VERIFICATION_REQUIRED"] = True
        for ruta in ("/prueba-compra", "/prueba-admin"):
            self.assertEqual(client.get(ruta).status_code, 302)

    def test_tres_altas_respetan_ambos_modos_en_bd(self):
        for requerido in (False, True):
            for tipo in ("publico", "admin", "repartidor"):
                with self.subTest(requerido=requerido, tipo=tipo):
                    self.app.config["EMAIL_VERIFICATION_REQUIRED"] = requerido
                    conexion = MagicMock()
                    cursor = conexion.cursor.return_value.__enter__.return_value
                    cursor.fetchone.return_value = {"id": "rol"}
                    datos = dict(usuario_id="u", perfil_id="p", correo="u@sulpaa.test",
                                 password_hash="hash-sintetico", nombres="ANA", apellido_paterno="PRUEBA",
                                 apellido_materno=None, dni="12345678", telefono="999999999",
                                 verificacion_correo={"sintetica": True})
                    modulo = identidad if tipo == "publico" else admin if tipo == "admin" else operaciones
                    with self.app.app_context(), patch.object(modulo, "insertar_solicitud") as insertar:
                        if tipo == "repartidor":
                            operaciones.crear_usuario_perfil(conexion, {"identidad": "test_id"}, **datos)
                        else:
                            with patch.object(modulo, "conexion_identidad", return_value=conexion):
                                if tipo == "publico":
                                    identidad.crear_usuario_y_perfil(**datos)
                                else:
                                    admin.crear_usuario_con_roles(**datos, rol_ids=["rol"])
                    sql, params = cursor.execute.call_args_list[0].args
                    self.assertEqual(params[-1], requerido)
                    self.assertTrue("FALSE" in sql or "'ACTIVO', 0" in sql)
                    self.assertEqual(insertar.call_count, 1 if requerido else 0)

    def test_checkout_sin_correo_no_inserta_outbox_y_conserva_compra(self):
        conexion = MagicMock()
        with self.app.app_context(), ExitStack() as stack:
            for nombre, resultado in (
                ("reservar_stock_pedido", {"ok": True}), ("crear_pedido", {"ok": True}),
                ("crear_pago_checkout", {"ok": True}), ("crear_entrega_pedido", "entrega"),
                ("cerrar_carrito_usuario", True), ("confirmar_stock_pedido", {"ok": True}),
            ):
                stack.enter_context(patch.object(comercio, nombre, return_value=resultado))
            outbox = stack.enter_context(patch.object(comercio, "insertar_confirmacion_pedido"))
            resultado = comercio._checkout_escrituras(
                conexion, {"identidad": "id", "comercio": "com", "inventario": "inv", "operaciones": "ops"},
                "pedido", "pago", "PED-1", "u", "RECOJO_LOCAL", "metodo", 20, 0, 20,
                [{"nombre": "Kombucha", "cantidad": 2, "precio": 10}], [],
                {"ok": True, "direccion_entrega": "Punto ficticio"},
            )
        self.assertTrue(resultado["ok"])
        outbox.assert_not_called()
        self.assertNotIn(unittest.mock.call("id"), conexion.select_db.call_args_list)


if __name__ == "__main__":
    unittest.main()
