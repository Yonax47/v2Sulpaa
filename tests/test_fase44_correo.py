# -*- coding: utf-8 -*-
"""Fase 4.4: correo, verificación y outbox sin red ni bases reales."""

import inspect
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from cryptography.fernet import Fernet

from app import create_app
from app.comercio import services as comercio_services
from app.config.testing import configurar_como_produccion
from app.identidad import email_repositories, email_verification
from app.shared.email.crypto import decrypt_payload, encrypt_payload
from app.shared.email.fake import FakeEmailProvider
from app.shared.email.outbox import procesar_outbox
from app.shared.email import outbox as outbox_module
from app.shared.email.provider import EmailMessage, EmailResult
from app.shared.email.repositories import insertar_outbox
from app.shared.email.resend import ResendProvider
from app.shared.email.templates import render_email


RAIZ = Path(__file__).resolve().parents[1]
FERNET_KEY = Fernet.generate_key().decode("ascii")
TOKEN_CSRF = "csrf-fase44"
USUARIO_ID = "usuario-fase44"


def configurar_correo(app, enabled=True):
    app.config.update(
        MAIL_ENABLED=enabled,
        RESEND_API_KEY="api-key-sintetica",
        MAIL_FROM="no-reply@sulpaa.test",
        MAIL_FROM_NAME="SULPAA",
        APP_PUBLIC_URL="https://sulpaa.test",
        MAIL_PAYLOAD_ENCRYPTION_KEY=FERNET_KEY,
        MAIL_RATE_LIMIT_KEY="clave-hmac-sintetica-larga",
        EMAIL_VERIFICATION_TTL_HOURS=24,
        EMAIL_RESEND_MIN_SECONDS=120,
        EMAIL_RESEND_MAX_WINDOW=5,
        MAIL_OUTBOX_MAX_ATTEMPTS=5,
        MAIL_OUTBOX_LEASE_SECONDS=300,
        EMAIL_EXISTING_GRACE_END=None,
    )


class CryptoYTokenTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        configurar_correo(self.app)

    def test_cifrado_autenticado_no_conserva_texto_plano(self):
        cifrado = encrypt_payload({"token": "secreto-token"}, FERNET_KEY)
        self.assertNotIn("secreto-token", cifrado)
        self.assertEqual(
            decrypt_payload(cifrado, FERNET_KEY), {"token": "secreto-token"}
        )

    def test_solicitud_guarda_hash_y_token_cifrado(self):
        with self.app.app_context(), patch.object(
            email_verification.secrets,
            "token_urlsafe",
            return_value="token-aleatorio",
        ):
            solicitud = email_verification.preparar_solicitud(
                USUARIO_ID, "cliente@sulpaa.test", "Ana"
            )
        self.assertEqual(
            solicitud["token_hash"],
            email_verification.token_hash("token-aleatorio"),
        )
        self.assertNotIn("token-aleatorio", repr(solicitud["datos"]))
        self.assertNotIn("token-aleatorio", solicitud["secreto_cifrado"])
        secreto = decrypt_payload(solicitud["secreto_cifrado"], FERNET_KEY)
        self.assertTrue(secreto["verification_url"].endswith("#token=token-aleatorio"))

    def test_tokens_distintos_generan_hashes_distintos(self):
        self.assertNotEqual(
            email_verification.token_hash("uno"),
            email_verification.token_hash("dos"),
        )


class ResendProviderTest(unittest.TestCase):
    def _message(self):
        return EmailMessage(
            to="destino@sulpaa.test",
            subject="Prueba",
            html="<p>Hola</p>",
            text="Hola",
            idempotency_key="EVENTO:1",
        )

    def _provider(self, session):
        return ResendProvider("clave", "origen@sulpaa.test", "SULPAA", session)

    def test_respuesta_correcta(self):
        response = Mock(status_code=200)
        response.json.return_value = {"id": "resend-id"}
        session = Mock()
        session.post.return_value = response
        result = self._provider(session).send(self._message())
        self.assertTrue(result.ok)
        self.assertEqual(result.provider_id, "resend-id")
        self.assertEqual(
            session.post.call_args.kwargs["headers"]["Idempotency-Key"],
            "EVENTO:1",
        )
        self.assertFalse(session.post.call_args.kwargs["allow_redirects"])

    def test_timeout_es_temporal(self):
        session = Mock()
        session.post.side_effect = requests.Timeout()
        result = self._provider(session).send(self._message())
        self.assertFalse(result.ok)
        self.assertTrue(result.temporary)
        self.assertEqual(result.error_code, "TIMEOUT")

    def test_429_respeta_retry_after(self):
        response = Mock(status_code=429, headers={"Retry-After": "90"})
        session = Mock()
        session.post.return_value = response
        result = self._provider(session).send(self._message())
        self.assertTrue(result.temporary)
        self.assertEqual(result.retry_after, 90)

    def test_500_es_temporal_y_400_permanente(self):
        for status, temporal in ((500, True), (400, False)):
            with self.subTest(status=status):
                session = Mock()
                session.post.return_value = Mock(status_code=status, headers={})
                result = self._provider(session).send(self._message())
                self.assertEqual(result.temporary, temporal)

    def test_configuracion_ausente_no_hace_red(self):
        session = Mock()
        result = ResendProvider("", "", session=session).send(self._message())
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "CONFIG")
        session.post.assert_not_called()


class PoliticaVerificacionTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        configurar_correo(self.app)

    def test_verificada_tiene_acceso(self):
        with self.app.app_context():
            self.assertEqual(
                email_verification.estado_cuenta(True, True, ["CLIENTE"]),
                "VERIFICADO",
            )

    def test_nueva_pendiente_es_obligatoria(self):
        with self.app.app_context():
            self.assertEqual(
                email_verification.estado_cuenta(False, True, ["CLIENTE"]),
                "PENDIENTE_OBLIGATORIO",
            )

    def test_historica_permanece_en_transicion_sin_fecha(self):
        with self.app.app_context():
            self.assertEqual(
                email_verification.estado_cuenta(False, False, ["CLIENTE"]),
                "PENDIENTE_TRANSICION",
            )


class ReenvioTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        configurar_correo(self.app)

    def test_no_enumera_cuenta_existente_e_inexistente(self):
        mensajes = []
        with self.app.app_context(), patch.object(
            email_verification, "consumir_limites_persistentes", return_value=True
        ), patch.object(
            email_verification.email_repositories,
            "buscar_cuenta_para_verificacion",
            side_effect=[None, {
                "id": USUARIO_ID,
                "correo": "cliente@sulpaa.test",
                "correo_verificado": 1,
                "estado": "ACTIVO",
                "nombres": "Ana",
            }],
        ):
            mensajes.append(email_verification.solicitar_reenvio(
                "noexiste@sulpaa.test", "127.0.0.1"
            )["mensaje"])
            mensajes.append(email_verification.solicitar_reenvio(
                "cliente@sulpaa.test", "127.0.0.2"
            )["mensaje"])
        self.assertEqual(mensajes[0], mensajes[1])

    def test_reenvio_invalida_mediante_reemplazo_transaccional(self):
        cuenta = {
            "id": USUARIO_ID,
            "correo": "cliente@sulpaa.test",
            "correo_verificado": 0,
            "estado": "ACTIVO",
            "nombres": "Ana",
        }
        with self.app.app_context(), patch.object(
            email_verification, "consumir_limites_persistentes", return_value=True
        ), patch.object(
            email_verification.email_repositories,
            "buscar_cuenta_para_verificacion",
            return_value=cuenta,
        ), patch.object(
            email_verification.email_repositories, "reemplazar_solicitud",
            return_value=True,
        ) as reemplazar:
            resultado = email_verification.solicitar_reenvio(
                cuenta["correo"], "127.0.0.1"
            )
        self.assertTrue(resultado["ok"])
        reemplazar.assert_called_once()

    def test_reemplazo_cancela_eventos_pendientes_anteriores(self):
        fuente = inspect.getsource(email_repositories.reemplazar_solicitud)
        self.assertIn("REEMPLAZADO", fuente)
        self.assertIn("co.secreto_cifrado = NULL", fuente)
        self.assertIn("co.estado IN ('PENDIENTE','REINTENTO')", fuente)

    def test_limite_se_evalua_antes_de_buscar_cuenta(self):
        with self.app.app_context(), patch.object(
            email_verification, "consumir_limites_persistentes", return_value=False
        ), patch.object(
            email_verification.email_repositories,
            "buscar_cuenta_para_verificacion",
        ) as buscar:
            email_verification.solicitar_reenvio(
                "cliente@sulpaa.test", "127.0.0.1"
            )
        buscar.assert_not_called()

    def test_error_de_limite_no_filtra_correo_en_log(self):
        correo = "privado@sulpaa.test"
        with self.app.app_context(), patch.object(
            email_verification, "consumir_limites_persistentes",
            side_effect=RuntimeError("fallo sintético"),
        ), patch.object(email_verification.logger, "error") as log:
            email_verification.solicitar_reenvio(correo, "127.0.0.1")
        self.assertNotIn(correo, repr(log.call_args))


class TokenEstadoTest(unittest.TestCase):
    def test_invalido_expirado_consumido_y_valido(self):
        app = create_app()
        configurar_correo(app)
        casos = (
            (None, "INVALIDO"),
            ({"estado": "ACTIVO", "invalidado_en": None, "consumido_en": None,
              "correo_verificado": 0, "vigente": 0}, "EXPIRADO"),
            ({"estado": "ACTIVO", "invalidado_en": None, "consumido_en": "x",
              "correo_verificado": 0, "vigente": 1}, "CONSUMIDO"),
            ({"estado": "ACTIVO", "invalidado_en": None, "consumido_en": None,
              "correo_verificado": 0, "vigente": 1}, "VALIDO"),
        )
        with app.app_context():
            for registro, esperado in casos:
                with self.subTest(esperado=esperado), patch.object(
                    email_verification.email_repositories,
                    "inspeccionar_token",
                    return_value=registro,
                ):
                    self.assertEqual(
                        email_verification.inspeccionar("token")["estado"], esperado
                    )

    def test_consumo_concurrente_solo_verifica_una_vez(self):
        lock = threading.Lock()
        consumido = False

        def atomico(_hash):
            nonlocal consumido
            with lock:
                if consumido:
                    return {"estado": "CONSUMIDO"}
                consumido = True
                return {"estado": "VERIFICADO", "usuario_id": USUARIO_ID}

        resultados = []
        with patch.object(
            email_verification.email_repositories,
            "consumir_token",
            side_effect=atomico,
        ):
            hilos = [threading.Thread(
                target=lambda: resultados.append(email_verification.confirmar("token"))
            ) for _ in range(2)]
            for hilo in hilos:
                hilo.start()
            for hilo in hilos:
                hilo.join()
        self.assertEqual(
            [r["estado"] for r in resultados].count("VERIFICADO"), 1
        )

    def test_repositorio_usa_bloqueo_e_invalida_otros(self):
        fuente = inspect.getsource(email_repositories.consumir_token)
        self.assertIn("FOR UPDATE", fuente)
        self.assertIn("correo_verificado = 1", fuente)
        self.assertIn("invalidado_en = NOW(6)", fuente)


class OutboxTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        configurar_correo(self.app)

    def _fila(self, intentos=1):
        return {
            "id": "evento-1",
            "clave_idempotencia": "PEDIDO_CONFIRMADO:pedido-1",
            "tipo": "PEDIDO_CONFIRMADO",
            "destinatario": "cliente@sulpaa.test",
            "plantilla": "pedido_confirmado",
            "datos_json": json.dumps({
                "nombre": "Ana", "numero_pedido": "PED-1",
                "fecha": "03/11/2026", "estado": "Confirmado",
                "items": [{"nombre": "Kombucha", "cantidad": 2, "precio": 10.0}],
                "total": 20.0, "order_path": "/pedidos/pedido-1",
            }),
            "secreto_cifrado": None,
            "intentos": intentos,
        }

    def test_evento_idempotente_depende_de_clave_unica(self):
        cursor = Mock(rowcount=1)
        creado = insertar_outbox(
            cursor, evento_id="e", clave_idempotencia="K:1",
            tipo="PEDIDO_CONFIRMADO", destinatario="a@sulpaa.test",
            plantilla="pedido_confirmado", datos={"x": 1},
        )
        self.assertTrue(creado)
        self.assertIn("ON DUPLICATE KEY UPDATE", cursor.execute.call_args.args[0])

    def test_procesa_exito_y_marca_enviado(self):
        provider = FakeEmailProvider()
        with self.app.app_context(), patch(
            "app.shared.email.outbox.reclamar_lote", return_value=[self._fila()]
        ), patch("app.shared.email.outbox.marcar_enviado") as enviado, patch(
            "app.shared.email.outbox.marcar_fallo"
        ):
            resumen = procesar_outbox(provider=provider)
        self.assertEqual(resumen["enviados"], 1)
        enviado.assert_called_once()
        self.assertEqual(len(provider.messages), 1)

    def test_fallo_temporal_programa_reintento(self):
        provider = FakeEmailProvider([EmailResult(
            False, temporary=True, error_code="RATE_LIMIT", retry_after=90
        )])
        with self.app.app_context(), patch(
            "app.shared.email.outbox.reclamar_lote", return_value=[self._fila()]
        ), patch("app.shared.email.outbox.marcar_enviado"), patch(
            "app.shared.email.outbox.marcar_fallo"
        ) as fallo:
            procesar_outbox(provider=provider)
        self.assertFalse(fallo.call_args.kwargs["permanente"])
        self.assertEqual(fallo.call_args.kwargs["proximo_intento_segundos"], 90)

    def test_maximo_intentos_convierte_en_permanente(self):
        provider = FakeEmailProvider([EmailResult(
            False, temporary=True, error_code="TIMEOUT"
        )])
        with self.app.app_context(), patch(
            "app.shared.email.outbox.reclamar_lote",
            return_value=[self._fila(intentos=5)],
        ), patch("app.shared.email.outbox.marcar_enviado"), patch(
            "app.shared.email.outbox.marcar_fallo"
        ) as fallo:
            procesar_outbox(provider=provider)
        self.assertTrue(fallo.call_args.kwargs["permanente"])

    def test_fallo_permanente_no_se_reintenta(self):
        provider = FakeEmailProvider([EmailResult(
            False, temporary=False, error_code="PROVIDER_400"
        )])
        with self.app.app_context(), patch(
            "app.shared.email.outbox.reclamar_lote", return_value=[self._fila()]
        ), patch("app.shared.email.outbox.marcar_enviado"), patch(
            "app.shared.email.outbox.marcar_fallo"
        ) as fallo:
            procesar_outbox(provider=provider)
        self.assertTrue(fallo.call_args.kwargs["permanente"])

    def test_backoff_es_exponencial_y_acotado(self):
        self.assertEqual(outbox_module._backoff(1), 60)
        self.assertEqual(outbox_module._backoff(2), 120)
        self.assertEqual(outbox_module._backoff(20), 21600)

    def test_deshabilitado_no_reclama(self):
        configurar_correo(self.app, enabled=False)
        with self.app.app_context(), patch(
            "app.shared.email.outbox.reclamar_lote"
        ) as reclamar:
            resultado = procesar_outbox()
        self.assertTrue(resultado["deshabilitado"])
        reclamar.assert_not_called()

    def test_reclamo_concurrente_usa_skip_locked_y_lease(self):
        from app.shared.email import repositories
        fuente = inspect.getsource(repositories.reclamar_lote)
        self.assertIn("FOR UPDATE SKIP LOCKED", fuente)
        self.assertIn("lease_token", fuente)
        self.assertIn("bloqueado_hasta", fuente)

    def test_comando_cli_no_procesa_si_correo_esta_deshabilitado(self):
        configurar_correo(self.app, enabled=False)
        resultado = self.app.test_cli_runner().invoke(
            args=["procesar-correos", "--limite", "2"]
        )
        self.assertEqual(resultado.exit_code, 0)
        self.assertIn("Correo deshabilitado", resultado.output)


class RutasVerificacionTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        configurar_como_produccion(self.app)
        configurar_correo(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_csrf_token"] = TOKEN_CSRF

    def test_get_no_consume_token(self):
        with patch("app.identidad.routes.confirmar_correo") as confirmar:
            response = self.client.get("/identidad/verificacion")
        self.assertEqual(response.status_code, 200)
        confirmar.assert_not_called()
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_post_sin_csrf_no_consume(self):
        with patch("app.identidad.routes.confirmar_correo") as confirmar:
            response = self.client.post("/identidad/verificacion")
        self.assertEqual(response.status_code, 400)
        confirmar.assert_not_called()

    def test_post_confirma_con_csrf(self):
        with patch(
            "app.identidad.routes.confirmar_correo",
            return_value={"estado": "VERIFICADO", "usuario_id": USUARIO_ID},
        ):
            response = self.client.post(
                "/identidad/verificacion",
                data={"csrf_token": TOKEN_CSRF, "token": "token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Correo verificado", response.get_data(as_text=True))

    def test_checkout_nuevo_pendiente_es_bloqueado_en_backend(self):
        with self.client.session_transaction() as session:
            session.update({
                "autenticado": True, "usuario_id": USUARIO_ID,
                "correo": "cliente@sulpaa.test", "roles": ["CLIENTE"],
                "correo_verificado": False,
                "requiere_verificacion_correo": True,
                "_csrf_token": TOKEN_CSRF,
            })
        contexto = {
            "id": USUARIO_ID, "correo": "cliente@sulpaa.test",
            "estado": "ACTIVO", "roles": ["CLIENTE"],
            "correo_verificado": False,
            "requiere_verificacion_correo": True,
        }
        with patch(
            "app.identidad.services.obtener_contexto_sesion", return_value=contexto
        ), patch("app.comercio.routes.confirmar_checkout_con_entrega") as checkout:
            response = self.client.post(
                "/api/checkout/confirmar", json={},
                headers={"X-CSRF-Token": TOKEN_CSRF},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["codigo"], "CORREO_NO_VERIFICADO")
        checkout.assert_not_called()

    def test_checkout_historico_en_transicion_conserva_acceso(self):
        with self.client.session_transaction() as session:
            session.update({
                "autenticado": True, "usuario_id": USUARIO_ID,
                "correo": "historico@sulpaa.test", "roles": ["CLIENTE"],
                "correo_verificado": False,
                "requiere_verificacion_correo": False,
                "_csrf_token": TOKEN_CSRF,
            })
        contexto = {
            "id": USUARIO_ID, "correo": "historico@sulpaa.test",
            "estado": "ACTIVO", "roles": ["CLIENTE"],
            "correo_verificado": False,
            "requiere_verificacion_correo": False,
        }
        with patch(
            "app.identidad.services.obtener_contexto_sesion", return_value=contexto
        ), patch(
            "app.comercio.routes.confirmar_checkout_con_entrega",
            return_value={"ok": False, "mensaje": "checkout simulado"},
        ) as checkout:
            response = self.client.post(
                "/api/checkout/confirmar", json={},
                headers={"X-CSRF-Token": TOKEN_CSRF},
            )
        self.assertEqual(response.status_code, 400)
        checkout.assert_called_once()

    def test_cuenta_administrativa_nueva_pendiente_no_elude_restriccion(self):
        with self.client.session_transaction() as session:
            session.update({
                "autenticado": True, "usuario_id": USUARIO_ID,
                "correo": "admin@sulpaa.test", "roles": ["ADMINISTRADOR"],
                "correo_verificado": False,
                "requiere_verificacion_correo": True,
            })
        contexto = {
            "id": USUARIO_ID, "correo": "admin@sulpaa.test",
            "estado": "ACTIVO", "roles": ["ADMINISTRADOR"],
            "correo_verificado": False,
            "requiere_verificacion_correo": True,
        }
        with patch(
            "app.identidad.services.obtener_contexto_sesion", return_value=contexto
        ):
            response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/identidad/verificacion/pendiente", response.headers["Location"])


class CheckoutCorreoTest(unittest.TestCase):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False

    class Conexion:
        def __init__(self): self.esquemas = []
        def select_db(self, esquema): self.esquemas.append(esquema)
        def cursor(self): return CheckoutCorreoTest.Cursor()

    def test_compra_encola_evento_sin_contactar_proveedor(self):
        conexion = self.Conexion()
        entrega = {"ok": True, "direccion_entrega": "Dirección sintética"}
        with patch.object(comercio_services, "eventos_pedido_habilitados", return_value=True), patch.object(
            comercio_services, "reservar_stock_pedido", return_value={"ok": True}
        ), patch.object(
            comercio_services, "crear_pedido", return_value={"ok": True}
        ), patch.object(
            comercio_services, "crear_pago_checkout", return_value={"ok": True}
        ), patch.object(
            comercio_services, "crear_entrega_pedido", return_value="entrega-1"
        ), patch.object(
            comercio_services, "cerrar_carrito_usuario", return_value=True
        ), patch.object(
            comercio_services, "confirmar_stock_pedido", return_value={"ok": True}
        ), patch.object(
            comercio_services, "insertar_confirmacion_pedido", return_value=True
        ) as outbox:
            result = comercio_services._checkout_escrituras(
                conexion,
                {"inventario": "inv", "comercio": "com", "operaciones": "ops", "identidad": "id"},
                "pedido-1", "pago-1", "PED-1", USUARIO_ID,
                "RECOJO_LOCAL", "metodo-1", 20, 0, 20,
                [{"nombre": "Kombucha", "cantidad": 2, "precio": 10}],
                [{"variante_id": "v", "cantidad": 2}], entrega,
            )
        self.assertTrue(result["ok"])
        outbox.assert_called_once()
        self.assertEqual(conexion.esquemas[-1], "id")


class PlantillasYMigracionTest(unittest.TestCase):
    def test_plantillas_html_y_texto_renderizan(self):
        app = create_app()
        configurar_correo(app)
        with app.app_context():
            verificacion = render_email("verificacion_correo", {
                "nombre": "Ana", "verification_url": "https://sulpaa.test/v",
                "verification_code": "codigo", "expires_hours": 24,
            })
            pedido = render_email("pedido_confirmado", {
                "nombre": "Ana", "numero_pedido": "PED-1",
                "fecha": "03/11/2026", "estado": "Confirmado",
                "items": [{"nombre": "Kombucha", "cantidad": 1, "precio": 10}],
                "total": 10, "order_url": "https://sulpaa.test/pedidos/1",
            })
        self.assertIn("Verifica tu correo", verificacion["html"])
        self.assertIn("https://sulpaa.test/v", verificacion["text"])
        self.assertIn("No constituye", pedido["html"])
        self.assertIn("PED-1", pedido["text"])

    def test_migracion_006_es_pasiva_y_secuencial(self):
        ruta = RAIZ / "migrations/006_fase44_correo_outbox.sql"
        texto = ruta.read_text(encoding="utf-8")
        self.assertIn("NO EJECUTAR EN PRODUCCIÓN", texto)
        self.assertIn("tokens_verificacion", texto)
        self.assertIn("correos_outbox", texto)
        self.assertIn("limites_correo", texto)
        self.assertIn("UNIQUE KEY uq_correos_outbox_idempotencia", texto)

    def test_documentacion_no_activa_cron_ni_produccion(self):
        texto = (RAIZ / "docs/correo_resend_outbox.md").read_text(encoding="utf-8")
        self.assertIn("Ninguna migración", texto)
        self.assertIn("MAIL_ENABLED=0", texto)
        self.assertIn("No se promete entrega", texto)
        self.assertIn("exactamente una vez", texto)

    def test_todos_los_flujos_de_alta_marcan_verificacion_requerida(self):
        archivos = (
            RAIZ / "app/identidad/repositories.py",
            RAIZ / "app/admin/usuarios/repositories.py",
            RAIZ / "app/operaciones/repositories.py",
        )
        for ruta in archivos:
            with self.subTest(ruta=ruta.name):
                texto = ruta.read_text(encoding="utf-8")
                self.assertIn("requiere_verificacion_correo", texto)
                self.assertIn("insertar_solicitud", texto)


if __name__ == "__main__":
    unittest.main()
