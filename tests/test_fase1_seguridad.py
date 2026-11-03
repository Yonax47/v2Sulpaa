# -*- coding: utf-8 -*-
"""Pruebas de Fase 1 con reloj y repositorios dobles, sin escribir en MySQL."""

import threading
import unittest
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from flask import Flask, render_template, request, session

from app import create_app
from app.admin.seguridad import services as seguridad_admin
from app.config.security import configurar_seguridad_accesos
from app.identidad import services as identidad
from app.identidad.access_control import evaluar_fallo_contador
from app.shared.network import obtener_ip_cliente


AHORA = datetime(2026, 10, 29, 12, 0, 0)
CORREO = "persona@sulpaa.test"
IP = "192.0.2.10"
HASH = "$2b$12$D0j.JGrC8NcnYP/4f6T2S.f82K3/jicG/ApQF/CvbGrwKCgCyLwz6"


def aplicar_fallo(estado, ahora=AHORA, limite=3):
    """Aplica el cálculo real a un estado pequeño usado por varias pruebas."""

    return evaluar_fallo_contador(
        intentos=estado.get("intentos", 0),
        ventana_inicia_en=estado.get("ventana_inicia_en"),
        bloqueado_hasta=estado.get("bloqueado_hasta"),
        ahora=ahora,
        limite=limite,
        ventana_minutos=15,
        bloqueo_minutos=15,
    )


class PoliticaBloqueosTest(unittest.TestCase):
    """Comprueba límites, ventanas, expiración e independencia de claves."""

    def test_primer_y_segundo_fallo_no_bloquean(self):
        primero = aplicar_fallo({})
        segundo = aplicar_fallo(primero, AHORA + timedelta(minutes=1))
        self.assertEqual(primero["intentos"], 1)
        self.assertFalse(primero["bloqueo_nuevo"])
        self.assertEqual(segundo["intentos"], 2)
        self.assertFalse(segundo["bloqueo_nuevo"])

    def test_tercer_fallo_bloquea_exactamente_quince_minutos(self):
        estado = aplicar_fallo({})
        estado = aplicar_fallo(estado, AHORA + timedelta(minutes=1))
        tercero = aplicar_fallo(estado, AHORA + timedelta(minutes=2))
        self.assertTrue(tercero["bloqueo_nuevo"])
        self.assertEqual(
            tercero["bloqueado_hasta"], AHORA + timedelta(minutes=17)
        )

    def test_expiracion_inicia_una_ventana_nueva(self):
        bloqueado = {
            "intentos": 3,
            "ventana_inicia_en": AHORA,
            "bloqueado_hasta": AHORA + timedelta(minutes=15),
        }
        nuevo = aplicar_fallo(bloqueado, AHORA + timedelta(minutes=15))
        self.assertEqual(nuevo["intentos"], 1)
        self.assertFalse(nuevo["bloqueo_nuevo"])
        self.assertEqual(nuevo["ventana_inicia_en"], AHORA + timedelta(minutes=15))

    def test_limite_adicional_por_ip_es_veinte(self):
        estado = {}
        for numero in range(1, 21):
            estado = aplicar_fallo(
                estado, AHORA + timedelta(seconds=numero), limite=20
            )
        self.assertEqual(estado["intentos"], 20)
        self.assertTrue(estado["bloqueo_nuevo"])

    def test_otra_ip_mantiene_un_contador_independiente(self):
        contadores = {}
        for _ in range(3):
            contadores[(CORREO, IP)] = aplicar_fallo(
                contadores.get((CORREO, IP), {})
            )
        otra = aplicar_fallo(contadores.get((CORREO, "198.51.100.8"), {}))
        self.assertTrue(contadores[(CORREO, IP)]["bloqueo_nuevo"])
        self.assertEqual(otra["intentos"], 1)
        self.assertFalse(otra["bloqueo_nuevo"])

    def test_incrementos_concurrentes_no_se_pierden_con_cerrojo(self):
        estado = {}
        cerrojo = threading.Lock()

        def fallar():
            with cerrojo:
                hasta = estado.get("bloqueado_hasta")
                if hasta and hasta > AHORA:
                    return
                estado.update(aplicar_fallo(estado, limite=20))

        hilos = [threading.Thread(target=fallar) for _ in range(20)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(estado["intentos"], 20)
        self.assertTrue(estado["bloqueo_nuevo"])


class ConfiguracionProxyTest(unittest.TestCase):
    """Comprueba que staging no confíe cabeceras sin aprobación explícita."""

    def test_staging_no_activa_bloqueo_sin_proxy_validado(self):
        app = Flask(__name__)
        app.config.update(ENTORNO="staging", ES_PRODUCCION=False)
        entorno = {
            "LOGIN_BLOQUEO_HABILITADO": "1",
            "RAILWAY_PROXY_VALIDADO": "0",
            "TRUSTED_PROXY_HOPS": "0",
        }
        with patch.dict(os.environ, entorno, clear=False):
            configurar_seguridad_accesos(app)
        self.assertFalse(app.config["LOGIN_BLOQUEO_HABILITADO"])
        self.assertFalse(app.config["CENTRO_SEGURIDAD_HABILITADO"])

    def test_centro_solo_se_habilita_con_migracion_aprobada(self):
        app = Flask(__name__)
        app.config.update(ENTORNO="production", ES_PRODUCCION=True)
        with patch.dict(
            os.environ,
            {
                "LOGIN_MIGRACION_APROBADA": "1",
                "LOGIN_BLOQUEO_HABILITADO": "0",
                "RAILWAY_PROXY_VALIDADO": "0",
                "TRUSTED_PROXY_HOPS": "0",
            },
            clear=False,
        ):
            configurar_seguridad_accesos(app)
        self.assertTrue(app.config["CENTRO_SEGURIDAD_HABILITADO"])
        self.assertFalse(app.config["LOGIN_BLOQUEO_HABILITADO"])

    def test_ip_no_confia_en_x_forwarded_for_sin_proxyfix(self):
        app = Flask(__name__)
        with app.test_request_context(
            "/", environ_base={"REMOTE_ADDR": "192.0.2.30"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        ):
            self.assertEqual(obtener_ip_cliente(request), "192.0.2.30")

    def test_produccion_tambien_exige_migracion_aprobada(self):
        app = Flask(__name__)
        app.config.update(ENTORNO="production", ES_PRODUCCION=True)
        entorno = {
            "LOGIN_BLOQUEO_HABILITADO": "1",
            "RAILWAY_PROXY_VALIDADO": "1",
            "LOGIN_MIGRACION_APROBADA": "0",
            "TRUSTED_PROXY_HOPS": "1",
        }
        with patch.dict(os.environ, entorno, clear=False):
            configurar_seguridad_accesos(app)
        self.assertFalse(app.config["LOGIN_BLOQUEO_HABILITADO"])

    def test_desarrollo_tambien_exige_migracion_aprobada(self):
        app = Flask(__name__)
        app.config.update(ENTORNO="development", ES_PRODUCCION=False)
        entorno = {
            "LOGIN_BLOQUEO_HABILITADO": "1",
            "LOGIN_MIGRACION_APROBADA": "0",
            "RAILWAY_PROXY_VALIDADO": "0",
            "TRUSTED_PROXY_HOPS": "0",
        }
        with patch.dict(os.environ, entorno, clear=False):
            configurar_seguridad_accesos(app)
        self.assertFalse(app.config["LOGIN_BLOQUEO_HABILITADO"])

class LoginProtegidoTest(unittest.TestCase):
    """Ejercita el flujo protegido sin conexiones ni contraseñas reales."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            LOGIN_BLOQUEO_HABILITADO=True,
            LOGIN_MAX_FALLOS_CUENTA_IP=3,
            LOGIN_MAX_FALLOS_IP=20,
            LOGIN_VENTANA_MINUTOS=15,
            LOGIN_BLOQUEO_MINUTOS=15,
        )

    def _autenticar(self, usuario, password_correcto=False):
        with self.app.app_context(), patch.object(
            identidad, "obtener_bloqueo_vigente", return_value=None
        ), patch.object(
            identidad, "buscar_usuario_por_correo", return_value=usuario
        ), patch.object(
            identidad.bcrypt, "checkpw", return_value=password_correcto
        ), patch.object(
            identidad, "registrar_fallo_login"
        ) as fallo, patch.object(
            identidad, "registrar_login_exitoso"
        ) as exito:
            resultado = identidad.autenticar_usuario(
                CORREO, "clave-no-real", IP, "Navegador de prueba"
            )
        return resultado, fallo, exito

    def test_correo_inexistente_registra_fallo_generico(self):
        resultado, fallo, _ = self._autenticar(None)
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["mensaje"], identidad._MENSAJE_LOGIN_GENERICO)
        fallo.assert_called_once()
        self.assertIsNone(fallo.call_args.kwargs["usuario_id"])

    def test_cuenta_inactiva_registra_el_mismo_fallo(self):
        usuario = {
            "id": "usuario-1", "correo": CORREO,
            "password_hash": HASH, "estado": "INACTIVO",
        }
        resultado, fallo, _ = self._autenticar(usuario, True)
        self.assertFalse(resultado["ok"])
        fallo.assert_called_once()

    def test_login_valido_reinicia_contador_correspondiente(self):
        usuario = {
            "id": "usuario-1", "correo": CORREO,
            "password_hash": HASH, "estado": "ACTIVO",
        }
        resultado, fallo, exito = self._autenticar(usuario, True)
        self.assertTrue(resultado["ok"])
        fallo.assert_not_called()
        exito.assert_called_once_with(
            usuario_id="usuario-1",
            correo=CORREO,
            direccion_ip=IP,
            user_agent="Navegador de prueba",
        )

    def test_bloqueo_impide_verificar_credenciales(self):
        with self.app.app_context(), patch.object(
            identidad,
            "obtener_bloqueo_vigente",
            return_value={"id": 8, "usuario_id": None},
        ), patch.object(
            identidad, "registrar_intento_bloqueado"
        ) as auditar, patch.object(
            identidad, "buscar_usuario_por_correo"
        ) as buscar:
            resultado = identidad.autenticar_usuario(
                CORREO, "cualquier-valor", IP, None
            )
        self.assertFalse(resultado["ok"])
        buscar.assert_not_called()
        auditar.assert_called_once()

    def test_error_de_base_falla_cerrado(self):
        with self.assertLogs(identidad.logger, level="ERROR"), self.app.app_context(), patch.object(
            identidad, "obtener_bloqueo_vigente", side_effect=RuntimeError("db")
        ), patch.object(identidad, "buscar_usuario_por_correo") as buscar:
            resultado = identidad.autenticar_usuario(CORREO, "x", IP, None)
        self.assertFalse(resultado["ok"])
        buscar.assert_not_called()

    def test_reinicio_de_app_conserva_bloqueo_persistente(self):
        segunda_app = create_app()
        segunda_app.config.update(TESTING=True, LOGIN_BLOQUEO_HABILITADO=True)
        for app in (self.app, segunda_app):
            with app.app_context(), patch.object(
                identidad,
                "obtener_bloqueo_vigente",
                return_value={"id": 9, "usuario_id": None},
            ), patch.object(identidad, "registrar_intento_bloqueado"):
                resultado = identidad.autenticar_usuario(CORREO, "x", IP, None)
            self.assertFalse(resultado["ok"])


class CentroSeguridadTest(unittest.TestCase):
    """Valida permisos, desbloqueo, CSRF y el contrato de auditoría."""

    def test_desbloqueo_autorizado_exige_motivo(self):
        with patch.object(
            seguridad_admin.repos,
            "desbloquear_bloqueo",
            return_value="DESBLOQUEADO",
        ) as desbloquear:
            invalido = seguridad_admin.desbloquear_acceso(
                ["GERENTE"], 4, "gerente-1", "no", IP
            )
            valido = seguridad_admin.desbloquear_acceso(
                ["GERENTE"], 4, "gerente-1", "Cuenta verificada", IP
            )
        self.assertFalse(invalido["ok"])
        self.assertTrue(valido["ok"])
        desbloquear.assert_called_once()

    def test_desbloqueo_sin_permiso_es_rechazado(self):
        with self.assertRaises(PermissionError):
            seguridad_admin.desbloquear_acceso(
                ["ADMINISTRADOR"], 4, "admin-1", "Motivo válido", IP
            )

    def test_post_desbloqueo_exige_csrf(self):
        app = create_app()
        app.config.update(
            TESTING=True,
            OMITIR_SEGURIDAD_EN_PRUEBAS=False,
            CSRF_ENABLED=True,
            CENTRO_SEGURIDAD_HABILITADO=True,
        )
        cliente = app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "gerente-1",
                "correo": "gerente@sulpaa.test",
                "roles": ["GERENTE"],
            })
        respuesta = cliente.post("/admin/seguridad/accesos/4/desbloquear")
        self.assertEqual(respuesta.status_code, 400)

    def test_ruta_desbloqueo_solo_permite_gerente(self):
        app = create_app()
        app.config.update(
            TESTING=True,
            OMITIR_SEGURIDAD_EN_PRUEBAS=False,
            CSRF_ENABLED=True,
            CENTRO_SEGURIDAD_HABILITADO=True,
        )
        cliente = app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "admin-1",
                "correo": "admin@sulpaa.test",
                "roles": ["ADMINISTRADOR"],
                "_csrf_token": "csrf-fase1",
            })
        contexto = {
            "id": "admin-1", "correo": "admin@sulpaa.test",
            "estado": "ACTIVO", "roles": ["ADMINISTRADOR"],
        }
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto,
        ):
            respuesta = cliente.post(
                "/admin/seguridad/accesos/4/desbloquear",
                data={
                    "csrf_token": "csrf-fase1",
                    "confirmar": "1",
                    "motivo": "Motivo de prueba",
                },
            )
        self.assertEqual(respuesta.status_code, 403)

    def test_panel_renderiza_indicadores_y_filtros(self):
        app = create_app()
        app.config.update(
            TESTING=True,
            OMITIR_SEGURIDAD_EN_PRUEBAS=True,
            CENTRO_SEGURIDAD_HABILITADO=True,
        )
        cliente = app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "gerente-1",
                "correo": "gerente@sulpaa.test",
                "roles": ["GERENTE"],
            })
        datos = {
            "indicadores": {
                "fallos": 12, "activos": 2,
                "expirados": 3, "desbloqueados": 1,
            },
            "bloqueos": [],
            "desbloqueos": [],
            "filtros": {
                "cuenta": "", "ip": "", "estado": "",
                "desde": "", "hasta": "",
            },
            "total": 0,
            "pagina": 1,
            "paginas": 1,
            "por_pagina": 25,
        }
        with patch(
            "app.admin.seguridad.routes.listar_centro_seguridad",
            return_value=datos,
        ):
            respuesta = cliente.get("/admin/seguridad/accesos")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b"Centro de seguridad", respuesta.data)
        self.assertIn(b"Intentos fallidos", respuesta.data)

    def test_centro_desactivado_no_ejecuta_consultas(self):
        """Todas las URL se detienen antes de Servicios y repositorios."""

        app = create_app()
        app.config.update(
            TESTING=True,
            OMITIR_SEGURIDAD_EN_PRUEBAS=True,
            CSRF_ENABLED=True,
            CENTRO_SEGURIDAD_HABILITADO=False,
        )
        cliente = app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "gerente-1",
                "correo": "gerente@sulpaa.test",
                "roles": ["GERENTE"],
                "_csrf_token": "csrf-centro-desactivado",
            })

        with patch(
            "app.admin.seguridad.routes.listar_centro_seguridad"
        ) as listar, patch(
            "app.admin.seguridad.routes.obtener_detalle_bloqueo"
        ) as detalle, patch(
            "app.admin.seguridad.routes.desbloquear_acceso"
        ) as desbloquear, patch(
            "app.admin.seguridad.repositories.conexion_identidad",
            side_effect=AssertionError("No debe abrir una conexión"),
        ):
            respuestas = (
                cliente.get("/admin/seguridad/accesos"),
                cliente.get("/admin/seguridad/accesos/4"),
                cliente.post(
                    "/admin/seguridad/accesos/4/desbloquear",
                    data={
                        "csrf_token": "csrf-centro-desactivado",
                        "confirmar": "1",
                        "motivo": "Motivo de prueba",
                    },
                ),
            )

        self.assertEqual([item.status_code for item in respuestas], [404, 404, 404])
        listar.assert_not_called()
        detalle.assert_not_called()
        desbloquear.assert_not_called()

    def test_menu_oculta_centro_y_panel_general_sigue_disponible(self):
        """El enlace desaparece sin afectar la entrada del panel."""

        app = create_app()
        app.config.update(
            TESTING=True,
            OMITIR_SEGURIDAD_EN_PRUEBAS=True,
            CENTRO_SEGURIDAD_HABILITADO=False,
        )
        cliente = app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "gerente-1",
                "correo": "gerente@sulpaa.test",
                "roles": ["GERENTE"],
            })

        with app.test_request_context("/admin/"):
            session.update({
                "autenticado": True,
                "usuario_id": "gerente-1",
                "roles": ["GERENTE"],
            })
            html = render_template(
                "admin/components/sidebar.html", admin_activo=""
            )

        self.assertNotIn("Seguridad de accesos", html)
        self.assertIn("Auditoría", html)
        respuesta = cliente.get("/admin/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/admin/dashboard", respuesta.headers["Location"])

    def test_migracion_y_repositorio_conservan_auditoria_y_concurrencia(self):
        migracion = Path(
            "migrations/002_identidad_seguridad_accesos.sql"
        ).read_text(encoding="utf-8")
        repositorio = Path(
            "app/admin/seguridad/repositories.py"
        ).read_text(encoding="utf-8")
        identidad_repo = Path(
            "app/identidad/repositories.py"
        ).read_text(encoding="utf-8")
        self.assertIn("UNIQUE KEY uq_desbloqueos_bloqueo", migracion)
        self.assertIn("FOR UPDATE", repositorio)
        self.assertIn("FOR UPDATE", identidad_repo)
        self.assertIn("DESBLOQUEO_MANUAL", repositorio)
        self.assertNotIn("DELETE FROM auditoria_accesos", repositorio)


if __name__ == "__main__":
    unittest.main()
