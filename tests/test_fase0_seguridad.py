# -*- coding: utf-8 -*-
"""Pruebas de la Fase 0 sin escribir en las bases de datos reales.

Los servicios que normalmente consultarían MySQL se reemplazan por respuestas
controladas. Así comprobamos CSRF, sesiones y permisos en las rutas completas
sin crear usuarios, pedidos, movimientos ni reportes en producción.
"""

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.config.testing import configurar_como_produccion
from app.identidad import services as identidad_services


TOKEN_VALIDO = "token-csrf-de-prueba"
USUARIO_ID = "usuario-seguridad-prueba"


def contexto_activo(roles=None):
    """Construye la respuesta que Identidad daría para una cuenta activa."""

    return {
        "id": USUARIO_ID,
        "correo": "seguridad@sulpaa.test",
        "estado": "ACTIVO",
        "roles": list(roles or []),
    }


class Fase0SeguridadTest(unittest.TestCase):
    """Ejercita las protecciones globales y los módulos sensibles."""

    def setUp(self):
        self.app = create_app()
        # Esta suite recorre siempre el comportamiento equivalente a
        # producción, aunque otras pruebas aíslen sus reglas de negocio.
        configurar_como_produccion(self.app)
        self.client = self.app.test_client()

    def _sesion(self, roles=None, csrf=True):
        """Crea una cookie de prueba; la autorización aún se revalida."""

        with self.client.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": USUARIO_ID,
                "correo": "anterior@sulpaa.test",
                "roles": list(roles or []),
            })
            if csrf:
                sesion["_csrf_token"] = TOKEN_VALIDO

    def _post(self, ruta, datos=None, json=None):
        """Envía un POST válido como lo haría un formulario o JavaScript."""

        if json is not None:
            return self.client.post(
                ruta,
                json=json,
                headers={"X-CSRF-Token": TOKEN_VALIDO},
            )
        formulario = dict(datos or {})
        formulario["csrf_token"] = TOKEN_VALIDO
        return self.client.post(ruta, data=formulario)

    def test_formulario_post_rechaza_token_ausente(self):
        respuesta = self.client.post(
            "/identidad/login",
            data={"correo": "x@sulpaa.test", "password": "Clave123"},
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("solicitud no es segura", respuesta.get_data(as_text=True))

    def test_excepcion_testing_no_funciona_fuera_de_testing(self):
        """Una bandera accidental no puede apagar controles en producción."""

        self.app.config.update(
            TESTING=False,
            OMITIR_SEGURIDAD_EN_PRUEBAS=True,
            CSRF_ENABLED=True,
        )
        respuesta = self.client.post("/identidad/logout")
        self.assertEqual(respuesta.status_code, 400)

        self._sesion(["GERENTE"], csrf=False)
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=None,
        ) as revalidar:
            respuesta = self.client.get("/admin/dashboard")
        self.assertEqual(respuesta.status_code, 302)
        revalidar.assert_called_once_with(USUARIO_ID)

    def test_login_acepta_token_valido_y_carga_roles(self):
        # Primero se visita el formulario para crear el token de la sesión.
        pagina = self.client.get("/identidad/login")
        token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            pagina.get_data(as_text=True),
        ).group(1)

        with patch(
            "app.identidad.routes.autenticar_usuario",
            return_value={
                "ok": True,
                "usuario": {"id": USUARIO_ID, "correo": "seguridad@sulpaa.test"},
            },
        ), patch(
            "app.identidad.routes.obtener_roles_usuario",
            return_value=["ADMINISTRADOR"],
        ):
            respuesta = self.client.post(
                "/identidad/login",
                data={
                    "correo": "seguridad@sulpaa.test",
                    "password": "Clave123",
                    "csrf_token": token,
                },
            )

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/admin/dashboard", respuesta.headers["Location"])

    def test_registro_con_token_valido_sigue_funcionando(self):
        pagina = self.client.get("/identidad/registro")
        token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            pagina.get_data(as_text=True),
        ).group(1)
        with patch(
            "app.identidad.routes.registrar_usuario",
            return_value={"ok": True, "mensaje": "Usuario registrado."},
        ) as registrar:
            respuesta = self.client.post(
                "/identidad/registro",
                data={
                    "csrf_token": token,
                    "correo": "nuevo@sulpaa.test",
                    "password": "ClaveSegura123",
                    "nombres": "Usuario",
                    "apellido_paterno": "Prueba",
                    "telefono": "987654321",
                },
            )
        self.assertEqual(respuesta.status_code, 302)
        registrar.assert_called_once()

    def test_logout_exige_token_y_limpia_sesion(self):
        self._sesion(["CLIENTE"])
        self.assertEqual(self.client.post("/identidad/logout").status_code, 400)
        respuesta = self._post("/identidad/logout")
        self.assertEqual(respuesta.status_code, 302)
        with self.client.session_transaction() as sesion:
            self.assertNotIn("autenticado", sesion)

    def test_javascript_exige_cabecera_csrf(self):
        self._sesion(["GERENTE"])
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto_activo(["GERENTE"]),
        ), patch(
            "app.admin.delivery.routes.simular_cotizacion",
            return_value={"ok": True, "costo_entrega": 10},
        ) as simular:
            sin_token = self.client.post(
                "/admin/delivery/simular",
                json={"distancia_km": 2, "peso_kg": 1, "subtotal": 20},
            )
            con_token = self._post(
                "/admin/delivery/simular",
                json={"distancia_km": 2, "peso_kg": 1, "subtotal": 20},
            )
        self.assertEqual(sin_token.status_code, 400)
        self.assertEqual(con_token.status_code, 200)
        simular.assert_called_once()

    def test_admin_revalida_una_sola_vez_en_decoradores_apilados(self):
        self._sesion(["GERENTE"])
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto_activo(["GERENTE"]),
        ) as revalidar:
            # /admin usa login_required y admin_required, pero no necesita
            # consultar métricas porque solo redirige al dashboard.
            respuesta = self.client.get("/admin/")
        self.assertEqual(respuesta.status_code, 302)
        revalidar.assert_called_once_with(USUARIO_ID)

    def test_retirar_rol_durante_sesion_produce_403(self):
        self._sesion(["GERENTE"])
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto_activo(["CLIENTE"]),
        ):
            respuesta = self.client.get("/admin/dashboard")
        self.assertEqual(respuesta.status_code, 403)
        with self.client.session_transaction() as sesion:
            self.assertEqual(sesion["roles"], ["CLIENTE"])

    def test_desactivar_cuenta_con_sesion_abierta_cierra_acceso(self):
        self._sesion(["GERENTE"])
        inactivo = contexto_activo(["GERENTE"])
        inactivo["estado"] = "INACTIVO"
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=inactivo,
        ):
            respuesta = self.client.get("/admin/dashboard")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])
        with self.client.session_transaction() as sesion:
            self.assertNotIn("autenticado", sesion)

    def test_operaciones_principales_aceptan_token_y_permiso_vigente(self):
        """Comprueba inventario, pedidos, entregas, reportes y checkout."""

        casos = [
            (
                ["INVENTARIO"],
                "/admin/inventario/ex-1/verificar",
                {"conteo_fisico": "10"},
                "app.admin.inventario.routes.registrar_verificacion",
                {"mensaje": "Verificación registrada."},
                302,
            ),
            (
                ["PEDIDOS_LOGISTICA"],
                "/admin/pedidos/ped-1/confirmar",
                {},
                "app.admin.pedidos.routes.confirmar_pedido",
                {"mensaje": "Pedido confirmado."},
                302,
            ),
            (
                ["PEDIDOS_LOGISTICA"],
                "/admin/entregas/ent-1/listo",
                {},
                "app.admin.entregas.routes.marcar_listo",
                {"mensaje": "Entrega lista."},
                302,
            ),
        ]
        for roles, ruta, datos, parche, resultado, estado in casos:
            with self.subTest(ruta=ruta):
                self._sesion(roles)
                with patch(
                    "app.identidad.services.obtener_contexto_sesion",
                    return_value=contexto_activo(roles),
                ), patch(parche, return_value=resultado) as servicio:
                    respuesta = self._post(ruta, datos=datos)
                self.assertEqual(respuesta.status_code, estado)
                servicio.assert_called_once()

        self._sesion(["GERENTE"])
        reporte = {
            "contenido": b"reporte-prueba",
            "mimetype": "text/csv",
            "nombre_archivo": "reporte.csv",
        }
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto_activo(["GERENTE"]),
        ), patch(
            "app.admin.reportes.routes.generar_reporte", return_value=reporte
        ):
            respuesta = self._post(
                "/admin/reportes/generar",
                datos={"tipo": "KPI", "formato": "CSV"},
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data, b"reporte-prueba")

        self._sesion(["CLIENTE"])
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto_activo(["CLIENTE"]),
        ), patch(
            "app.comercio.routes.confirmar_checkout_con_entrega",
            return_value={"ok": True, "pedido_id": "ped-1"},
        ) as checkout:
            respuesta = self._post(
                "/api/checkout/confirmar", json={"tipo_entrega": "RECOJO_LOCAL"}
            )
        self.assertEqual(respuesta.status_code, 200)
        checkout.assert_called_once()

    def test_vistas_conservan_responsive_y_todos_los_post_tienen_token(self):
        raiz = Path(__file__).resolve().parents[1]
        base = (raiz / "templates" / "base.html").read_text(encoding="utf-8")
        admin_css = (raiz / "static" / "css" / "pages" / "admin.css").read_text(
            encoding="utf-8"
        )
        javascript = (raiz / "static" / "js" / "main.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('name="viewport"', base)
        self.assertIn('name="csrf-token"', base)
        self.assertIn("@media (max-width: 900px)", admin_css)
        self.assertIn('cabeceras.set("X-CSRF-Token", token)', javascript)
        self.assertIn("url.origin === window.location.origin", javascript)

        patron_formulario = re.compile(r"<form\b[^>]*>.*?</form>", re.I | re.S)
        for ruta in (raiz / "templates").rglob("*.html"):
            texto = ruta.read_text(encoding="utf-8")
            for formulario in patron_formulario.findall(texto):
                if re.search(r'method\s*=\s*["\']POST["\']', formulario, re.I):
                    self.assertIn("csrf_token", formulario, str(ruta))


class EnumeracionCuentasTest(unittest.TestCase):
    """Comprueba que las causas de rechazo no cambien la respuesta pública."""

    def test_inexistente_incorrecta_e_inactiva_comparten_mensaje_y_bcrypt(self):
        hash_valido = "$2b$12$hash-de-prueba"
        escenarios = [
            None,
            {
                "id": "u1", "correo": "u@sulpaa.test", "estado": "ACTIVO",
                "password_hash": hash_valido,
            },
            {
                "id": "u2", "correo": "u@sulpaa.test", "estado": "INACTIVO",
                "password_hash": hash_valido,
            },
        ]
        mensajes = []
        for usuario in escenarios:
            with patch(
                "app.identidad.services.buscar_usuario_por_correo",
                return_value=usuario,
            ), patch(
                "app.identidad.services.bcrypt.checkpw", return_value=False
            ) as comprobar:
                resultado = identidad_services.autenticar_usuario(
                    "u@sulpaa.test", "ClaveIncorrecta123"
                )
            mensajes.append(resultado["mensaje"])
            comprobar.assert_called_once()

        self.assertEqual(len(set(mensajes)), 1)
        self.assertNotIn("inactiva", mensajes[0].lower())
        self.assertNotIn("existe", mensajes[0].lower())


if __name__ == "__main__":
    unittest.main()
