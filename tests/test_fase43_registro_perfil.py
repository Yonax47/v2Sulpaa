# -*- coding: utf-8 -*-
"""Pruebas de la Fase 4.3 sin tocar las bases de datos reales.

Cubren el registro con DNI validado por APIsPERU (siempre con mocks), el
límite local de consultas, el autoservicio de Mi perfil y la integración de
sus enlaces. Ninguna prueba consume cuotas reales ni escribe datos.
"""

import inspect
import re
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import create_app
from app.config.testing import configurar_como_produccion
from app.identidad import services as identidad_services
from app.identidad import repositories as identidad_repositories
from app.identidad import apisperu
from app.perfil import repositories as perfil_repositories
from app.perfil import services as perfil_services
from app.shared import rate_limit


RAIZ = Path(__file__).resolve().parents[1]
TOKEN_VALIDO = "token-csrf-fase43"
USUARIO_ID = "usuario-fase43"


def contexto_activo(roles=None):
    return {
        "id": USUARIO_ID,
        "correo": "perfil@sulpaa.test",
        "estado": "ACTIVO",
        "roles": list(roles or []),
    }


def persona_valida(dni="12345678"):
    return {
        "ok": True,
        "dni": dni,
        "nombres": "ANA MARIA",
        "apellido_paterno": "PEREZ",
        "apellido_materno": "GOMEZ",
    }


def perfil_sintetico():
    return {
        "perfil": {
            "usuario_id": USUARIO_ID,
            "correo": "perfil@sulpaa.test",
            "correo_verificado": 1,
            "estado": "ACTIVO",
            "nombres": "ANA MARIA",
            "apellido_paterno": "PEREZ",
            "apellido_materno": "GOMEZ",
            "dni": "12345678",
            "telefono": "987654321",
        },
        "direcciones": [],
        "facturacion": [],
        "departamentos": [],
    }


class RegistroDniServicioTest(unittest.TestCase):
    """La verificación de DNI no depende de datos enviados por el navegador."""

    def test_dni_debe_tener_ocho_digitos(self):
        for dni in ("", "1234567", "123456789", "1234ABCD"):
            with self.subTest(dni=dni):
                with patch(
                    "app.identidad.services.consultar_dni"
                ) as consultar:
                    resultado = identidad_services.verificar_dni_registro(dni)
                self.assertFalse(resultado["ok"])
                self.assertEqual(resultado["estado"], "INVALIDO")
                consultar.assert_not_called()

    def test_duplicado_usa_mensaje_generico_y_no_consulta_api(self):
        with patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value={"id": "perfil-existente"},
        ), patch(
            "app.identidad.services.consultar_dni"
        ) as consultar:
            resultado = identidad_services.verificar_dni_registro("12345678")

        self.assertFalse(resultado["ok"])
        mensaje = resultado["mensaje"].lower()
        self.assertNotIn("registrado", mensaje)
        self.assertNotIn("duplicado", mensaje)
        consultar.assert_not_called()

    def test_servicio_no_disponible_se_informa_de_forma_controlada(self):
        with patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value=None,
        ), patch(
            "app.identidad.services.consultar_dni",
            return_value={
                "ok": False,
                "tipo_error": "NO_DISPONIBLE",
                "mensaje": "detalle interno que no debe mostrarse",
            },
        ):
            resultado = identidad_services.verificar_dni_registro("12345678")

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["estado"], "ERROR")
        self.assertIn("no está disponible", resultado["mensaje"])
        self.assertNotIn("detalle interno", resultado["mensaje"])

    def test_respuesta_incompleta_no_se_acepta(self):
        incompleta = persona_valida()
        incompleta["apellido_paterno"] = ""
        with patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value=None,
        ), patch(
            "app.identidad.services.consultar_dni",
            return_value=incompleta,
        ):
            resultado = identidad_services.verificar_dni_registro("12345678")

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["estado"], "ERROR")

    def test_respuesta_valida_devuelve_persona_y_aviso(self):
        with patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value=None,
        ), patch(
            "app.identidad.services.consultar_dni",
            return_value=persona_valida(),
        ):
            resultado = identidad_services.verificar_dni_registro("12345678")

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["estado"], "VERIFICADO")
        self.assertEqual(resultado["persona"]["nombres"], "ANA MARIA")
        self.assertIn("titular", resultado["aviso"].lower())


class ClienteApisPeruTest(unittest.TestCase):
    """El cliente externo falla cerrado y nunca devuelve su credencial."""

    def test_token_ausente_no_inicia_una_peticion(self):
        with patch.object(
            apisperu, "_obtener_token", side_effect=RuntimeError("sin token")
        ), patch.object(apisperu.requests, "get") as get:
            resultado = apisperu.consultar_dni("12345678")
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["tipo_error"], "NO_DISPONIBLE")
        get.assert_not_called()

    def test_token_solo_viaja_al_proveedor_y_no_regresa_en_resultado(self):
        respuesta = Mock(status_code=200)
        respuesta.json.return_value = {
            "dni": "12345678",
            "nombres": "ANA",
            "apellidoPaterno": "PEREZ",
            "apellidoMaterno": "GOMEZ",
        }
        with patch.object(
            apisperu, "_obtener_token", return_value="token-super-secreto"
        ), patch.object(
            apisperu.requests, "get", return_value=respuesta
        ) as get:
            resultado = apisperu.consultar_dni("12345678")

        self.assertTrue(resultado["ok"])
        self.assertNotIn("token", resultado)
        self.assertNotIn("token-super-secreto", repr(resultado))
        self.assertEqual(get.call_args.kwargs["allow_redirects"], False)
        self.assertEqual(get.call_args.kwargs["timeout"], apisperu.APISPERU_TIMEOUT)

    def test_json_invalido_se_clasifica_como_no_disponible(self):
        respuesta = Mock(status_code=200)
        respuesta.json.side_effect = ValueError("json roto")
        with patch.object(
            apisperu, "_obtener_token", return_value="token"
        ), patch.object(apisperu.requests, "get", return_value=respuesta):
            resultado = apisperu.consultar_dni("12345678")
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["tipo_error"], "NO_DISPONIBLE")


class RegistroUsuarioServicioTest(unittest.TestCase):
    """El registro definitivo ignora nombres del navegador y revalida el DNI."""

    def _registrar(self, nombres="NOMBRE MANIPULADO"):
        return identidad_services.registrar_usuario(
            correo="nuevo@sulpaa.test",
            password="ClaveSegura123",
            nombres=nombres,
            apellido_paterno="APELLIDO MANIPULADO",
            apellido_materno="OTRO MANIPULADO",
            dni="12345678",
            telefono="987 654 321",
        )

    def test_nombres_del_navegador_se_ignoran_y_se_revalida_dni(self):
        with patch(
            "app.identidad.services.buscar_usuario_por_correo",
            return_value=None,
        ), patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value=None,
        ), patch(
            "app.identidad.services.consultar_dni",
            return_value=persona_valida(),
        ) as consultar, patch(
            "app.identidad.services.crear_usuario_y_perfil"
        ) as crear, patch(
            "app.identidad.services.bcrypt.hashpw",
            return_value=b"hash-de-prueba",
        ):
            resultado = self._registrar()

        self.assertTrue(resultado["ok"])
        consultar.assert_called_once_with("12345678")
        datos = crear.call_args.kwargs
        self.assertEqual(datos["nombres"], "ANA MARIA")
        self.assertEqual(datos["apellido_paterno"], "PEREZ")
        self.assertEqual(datos["apellido_materno"], "GOMEZ")
        self.assertEqual(datos["telefono"], "987654321")
        self.assertEqual(datos["rol_codigo"], "CLIENTE")

    def test_si_apisperu_falla_no_se_crea_la_cuenta(self):
        with patch(
            "app.identidad.services.buscar_usuario_por_correo",
            return_value=None,
        ), patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value=None,
        ), patch(
            "app.identidad.services.consultar_dni",
            return_value={
                "ok": False,
                "tipo_error": "NO_DISPONIBLE",
                "mensaje": "sin servicio",
            },
        ), patch(
            "app.identidad.services.crear_usuario_y_perfil"
        ) as crear:
            resultado = self._registrar()

        self.assertFalse(resultado["ok"])
        self.assertIn("no está disponible", resultado["mensaje"])
        crear.assert_not_called()

    def test_duplicado_de_correo_o_dni_no_revela_cual_existe(self):
        with patch(
            "app.identidad.services.buscar_usuario_por_correo",
            return_value={"id": "existente"},
        ), patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value=None,
        ):
            por_correo = self._registrar()

        with patch(
            "app.identidad.services.buscar_usuario_por_correo",
            return_value=None,
        ), patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value={"id": "perfil-existente"},
        ):
            por_dni = self._registrar()

        self.assertFalse(por_correo["ok"])
        self.assertFalse(por_dni["ok"])
        self.assertEqual(por_correo["mensaje"], por_dni["mensaje"])

    def test_dos_registros_concurrentes_dependen_del_indice_unico(self):
        """Simula la carrera: ambos prechecks pasan, solo un INSERT gana.

        La exclusión del doble DNI la representa el almacén atómico del mock,
        equivalente al UNIQUE pendiente. Sin aplicar la migración 003 esta
        garantía todavía no existe en MariaDB.
        """

        barrera = threading.Barrier(2)
        cerrojo = threading.Lock()
        dni_guardados = set()

        def crear_atomico(**datos):
            barrera.wait(timeout=2)
            with cerrojo:
                if datos["dni"] in dni_guardados:
                    raise RuntimeError("duplicate key")
                dni_guardados.add(datos["dni"])

        resultados = []

        def registrar():
            resultados.append(self._registrar())

        with patch(
            "app.identidad.services.buscar_usuario_por_correo",
            return_value=None,
        ), patch(
            "app.identidad.services.buscar_perfil_por_dni",
            return_value=None,
        ), patch(
            "app.identidad.services.consultar_dni",
            return_value=persona_valida(),
        ), patch(
            "app.identidad.services.crear_usuario_y_perfil",
            side_effect=crear_atomico,
        ), patch(
            "app.identidad.services.bcrypt.hashpw",
            return_value=b"hash-de-prueba",
        ), patch.object(identidad_services.logger, "error"):
            hilos = [threading.Thread(target=registrar) for _ in range(2)]
            for hilo in hilos:
                hilo.start()
            for hilo in hilos:
                hilo.join(timeout=3)

        self.assertEqual(len(resultados), 2)
        self.assertEqual(sum(item["ok"] for item in resultados), 1)
        self.assertEqual(len(dni_guardados), 1)


class RegistroTransaccionalRepositorioTest(unittest.TestCase):
    """Usuario, perfil y CLIENTE se confirman o revierten juntos."""

    class Cursor:
        def __init__(self, rol={"id": "rol-cliente"}, fallar_rol=False):
            self.rol = rol
            self.fallar_rol = fallar_rol
            self.consultas = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, parametros=None):
            self.consultas.append((" ".join(sql.split()), parametros))
            if "INSERT INTO usuario_roles" in sql and self.fallar_rol:
                raise RuntimeError("fallo vínculo")

        def fetchone(self):
            return self.rol

    class Conexion:
        def __init__(self, cursor):
            self._cursor = cursor
            self.commits = 0
            self.rollbacks = 0
            self.cerrada = False

        def cursor(self):
            return self._cursor

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.cerrada = True

    def _crear(self, conexion):
        with patch.object(
            identidad_repositories, "conexion_identidad", return_value=conexion
        ):
            return identidad_repositories.crear_usuario_y_perfil(
                usuario_id="usuario",
                perfil_id="perfil",
                correo="nuevo@sulpaa.test",
                password_hash="hash",
                nombres="ANA",
                apellido_paterno="PEREZ",
                apellido_materno="GOMEZ",
                dni="12345678",
                telefono="987654321",
                rol_codigo="CLIENTE",
            )

    def test_inserta_cliente_y_confirma_una_sola_vez(self):
        cursor = self.Cursor()
        conexion = self.Conexion(cursor)
        self._crear(conexion)

        texto = " ".join(sql for sql, _ in cursor.consultas)
        self.assertIn("INSERT INTO usuarios", texto)
        self.assertIn("INSERT INTO perfiles", texto)
        self.assertIn("INSERT INTO usuario_roles", texto)
        self.assertTrue(any(params == ("CLIENTE",) for _, params in cursor.consultas))
        self.assertEqual(conexion.commits, 1)
        self.assertEqual(conexion.rollbacks, 0)

    def test_rol_cliente_ausente_revierte_toda_la_transaccion(self):
        cursor = self.Cursor(rol=None)
        conexion = self.Conexion(cursor)
        with self.assertRaises(RuntimeError):
            self._crear(conexion)
        self.assertEqual(conexion.commits, 0)
        self.assertEqual(conexion.rollbacks, 1)

    def test_fallo_del_vinculo_revierte_usuario_y_perfil(self):
        cursor = self.Cursor(fallar_rol=True)
        conexion = self.Conexion(cursor)
        with self.assertRaises(RuntimeError):
            self._crear(conexion)
        self.assertEqual(conexion.commits, 0)
        self.assertEqual(conexion.rollbacks, 1)


class EndpointDniTest(unittest.TestCase):
    """El endpoint público exige CSRF y aplica el límite local."""

    def setUp(self):
        rate_limit.limpiar_limites()
        self.app = create_app()
        configurar_como_produccion(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as sesion:
            sesion["_csrf_token"] = TOKEN_VALIDO

    def tearDown(self):
        rate_limit.limpiar_limites()

    def _post(self, datos, con_token=True):
        cabeceras = {"X-CSRF-Token": TOKEN_VALIDO} if con_token else {}
        return self.client.post(
            "/identidad/api/registro/verificar-dni",
            json=datos,
            headers=cabeceras,
        )

    def test_sin_csrf_no_consulta_la_api(self):
        with patch(
            "app.identidad.routes.verificar_dni_registro"
        ) as verificar:
            respuesta = self._post({"dni": "12345678"}, con_token=False)

        self.assertEqual(respuesta.status_code, 400)
        verificar.assert_not_called()

    def test_respuesta_exitosa_no_se_almacena_en_cache(self):
        with patch(
            "app.identidad.routes.verificar_dni_registro",
            return_value={
                "ok": True,
                "estado": "VERIFICADO",
                "persona": persona_valida(),
            },
        ):
            respuesta = self._post({"dni": "12345678"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers.get("Cache-Control"), "no-store")
        self.assertTrue(respuesta.get_json()["ok"])

    def test_cuerpo_no_objeto_se_rechaza(self):
        respuesta = self._post(["12345678"])
        self.assertEqual(respuesta.status_code, 400)

    def test_limite_local_bloquea_la_sexta_consulta(self):
        with patch(
            "app.identidad.routes.verificar_dni_registro",
            return_value={"ok": True, "persona": persona_valida()},
        ) as verificar:
            estados = [self._post({"dni": "12345678"}).status_code for _ in range(6)]

        self.assertEqual(estados[:5], [200] * 5)
        self.assertEqual(estados[5], 429)
        self.assertEqual(verificar.call_count, 5)


class LimiteLocalTest(unittest.TestCase):
    """Documenta el alcance real del limitador en memoria."""

    def tearDown(self):
        rate_limit.limpiar_limites()

    def test_ventana_deslizante_y_reintento(self):
        self.assertEqual(
            rate_limit.consumir_limite("ip", 2, 60, ahora=1000)[0], True
        )
        self.assertEqual(
            rate_limit.consumir_limite("ip", 2, 60, ahora=1000)[0], True
        )
        permitido, espera = rate_limit.consumir_limite("ip", 2, 60, ahora=1001)
        self.assertFalse(permitido)
        self.assertEqual(espera, 59)
        self.assertTrue(
            rate_limit.consumir_limite("ip", 2, 60, ahora=1061)[0]
        )

    def test_el_modulo_advierte_que_no_es_global(self):
        texto = inspect.getsource(rate_limit).lower()
        self.assertIn("no es un límite global", texto)


class PerfilPermisosTest(unittest.TestCase):
    """Todos los roles listados y las cuentas nuevas acceden a su propio perfil."""

    def setUp(self):
        self.app = create_app()
        configurar_como_produccion(self.app)
        self.client = self.app.test_client()

    def _sesion(self, roles=None):
        with self.client.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": USUARIO_ID,
                "correo": "perfil@sulpaa.test",
                "roles": list(roles or []),
                "_csrf_token": TOKEN_VALIDO,
            })

    def _get_perfil(self, roles):
        self._sesion(roles)
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto_activo(roles),
        ), patch(
            "app.perfil.routes.obtener_mi_perfil",
            return_value=perfil_sintetico(),
        ):
            return self.client.get("/mi-perfil/")

    def test_los_cinco_roles_pueden_entrar(self):
        for rol in ("CLIENTE", "REPARTIDOR", "VENDEDOR",
                    "ADMINISTRADOR", "GERENTE"):
            with self.subTest(rol=rol):
                self.assertEqual(self._get_perfil([rol]).status_code, 200)

    def test_cuenta_nueva_sin_rol_puede_completar_su_perfil(self):
        respuesta = self._get_perfil([])
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers.get("Cache-Control"), "no-store")

    def test_sin_sesion_redirige_al_login(self):
        respuesta = self.client.get("/mi-perfil/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])

    def test_post_sin_csrf_se_rechaza(self):
        self._sesion(["CLIENTE"])
        respuesta = self.client.post(
            "/mi-perfil/telefono", data={"telefono": "987654321"}
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_usuario_id_de_formulario_se_ignora(self):
        self._sesion(["CLIENTE"])
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto_activo(["CLIENTE"]),
        ), patch(
            "app.perfil.routes.actualizar_mi_telefono",
            return_value={"ok": True, "mensaje": "Teléfono actualizado."},
        ) as actualizar:
            respuesta = self.client.post(
                "/mi-perfil/telefono",
                data={
                    "csrf_token": TOKEN_VALIDO,
                    "usuario_id": "otro-usuario",
                    "telefono": "987654321",
                },
            )

        self.assertEqual(respuesta.status_code, 302)
        actualizar.assert_called_once_with(
            USUARIO_ID,
            ["CLIENTE"],
            telefono="987654321",
        )

    def test_recurso_de_otro_usuario_se_rechaza_sin_romper_la_sesion(self):
        self._sesion(["CLIENTE"])
        with patch(
            "app.identidad.services.obtener_contexto_sesion",
            return_value=contexto_activo(["CLIENTE"]),
        ), patch(
            "app.perfil.routes.elegir_direccion_principal",
            side_effect=perfil_services.ErrorPerfil(
                "La dirección indicada no está disponible."
            ),
        ), patch(
            "app.perfil.routes.obtener_mi_perfil",
            return_value=perfil_sintetico(),
        ):
            respuesta = self.client.post(
                "/mi-perfil/direcciones/direccion-ajena/principal",
                data={"csrf_token": TOKEN_VALIDO},
                follow_redirects=True,
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(
            "La dirección indicada no está disponible.",
            respuesta.get_data(as_text=True),
        )


class PerfilServiciosTest(unittest.TestCase):
    """Reglas del perfil sin acceso real a MariaDB."""

    def test_telefono_valido_normaliza_y_actualiza_solo_la_sesion(self):
        with patch.object(
            perfil_services.repositories,
            "obtener_perfil",
            return_value={"usuario_id": USUARIO_ID},
        ), patch.object(
            perfil_services.repositories,
            "actualizar_telefono",
        ) as actualizar:
            resultado = perfil_services.actualizar_mi_telefono(
                USUARIO_ID, ["CLIENTE"], "987 654 321"
            )

        self.assertTrue(resultado["ok"])
        actualizar.assert_called_once_with(USUARIO_ID, "987654321")

    def test_telefono_invalido_no_llega_al_repositorio(self):
        with patch.object(
            perfil_services.repositories, "actualizar_telefono"
        ) as actualizar:
            with self.assertRaises(perfil_services.ErrorPerfil):
                perfil_services.actualizar_mi_telefono(
                    USUARIO_ID, ["CLIENTE"], "12345"
                )
        actualizar.assert_not_called()

    def test_primera_direccion_es_principal_aunque_no_se_marque(self):
        with patch.object(
            perfil_services, "listar_direcciones_usuario", return_value=[]
        ), patch.object(
            perfil_services, "registrar_direccion_usuario",
            return_value={"ok": True, "mensaje": "ok"},
        ) as registrar:
            perfil_services.crear_mi_direccion(
                USUARIO_ID,
                ["CLIENTE"],
                {
                    "distrito_id": "150101",
                    "direccion": "Av. Siempre Viva 123",
                    "alias": "Casa",
                },
            )

        self.assertTrue(registrar.call_args.kwargs["es_principal"])

    def test_direccion_adicional_conserva_la_eleccion_del_usuario(self):
        with patch.object(
            perfil_services,
            "listar_direcciones_usuario",
            return_value=[{"id": "direccion-1", "es_principal": 1}],
        ), patch.object(
            perfil_services, "registrar_direccion_usuario",
            return_value={"ok": True, "mensaje": "ok"},
        ) as registrar:
            perfil_services.crear_mi_direccion(
                USUARIO_ID,
                ["CLIENTE"],
                {
                    "distrito_id": "150101",
                    "direccion": "Av. Siempre Viva 123",
                    "alias": "Casa",
                },
            )

        self.assertFalse(registrar.call_args.kwargs["es_principal"])

    def test_si_no_hay_principal_la_siguiente_asume_el_valor(self):
        with patch.object(
            perfil_services,
            "listar_direcciones_usuario",
            return_value=[{"id": "direccion-1", "es_principal": 0}],
        ), patch.object(
            perfil_services,
            "registrar_direccion_usuario",
            return_value={"ok": True, "mensaje": "ok"},
        ) as registrar:
            perfil_services.crear_mi_direccion(
                USUARIO_ID,
                ["CLIENTE"],
                {
                    "distrito_id": "150101",
                    "direccion": "Av. Siempre Viva 123",
                    "alias": "Casa",
                },
            )

        self.assertTrue(registrar.call_args.kwargs["es_principal"])

    def test_facturacion_se_crea_para_el_titular_de_la_sesion(self):
        with patch.object(
            perfil_services,
            "registrar_facturacion_checkout",
            return_value={"ok": True, "mensaje": "guardado"},
        ) as registrar:
            perfil_services.crear_mi_facturacion(
                USUARIO_ID, ["CLIENTE"], "BOLETA", "12345678"
            )

        registrar.assert_called_once_with(
            usuario_id=USUARIO_ID,
            tipo_comprobante="BOLETA",
            documento="12345678",
        )

    def test_error_de_facturacion_se_traduce_en_error_de_perfil(self):
        with patch.object(
            perfil_services,
            "registrar_facturacion_checkout",
            return_value={"ok": False, "mensaje": "Documento inválido."},
        ):
            with self.assertRaises(perfil_services.ErrorPerfil):
                perfil_services.crear_mi_facturacion(
                    USUARIO_ID, ["CLIENTE"], "BOLETA", "00000000"
                )

    def test_sin_identificador_no_se_permite_operar(self):
        with self.assertRaises(perfil_services.ErrorPerfil):
            perfil_services.obtener_mi_perfil(None, ["CLIENTE"])


class SemanticaFacturacionTest(unittest.TestCase):
    """Comprobante y contribuyente no se mezclan al persistir."""

    def test_boleta_se_persiste_como_persona(self):
        with patch(
            "app.identidad.services.validar_dni_con_perfil",
            return_value={
                "ok": True,
                "persona": {
                    "dni": "12345678",
                    "nombre_completo": "ANA PEREZ GOMEZ",
                },
            },
        ), patch(
            "app.identidad.services.guardar_datos_facturacion",
            return_value="facturacion-persona",
        ) as guardar:
            resultado = identidad_services.registrar_facturacion_checkout(
                usuario_id=USUARIO_ID,
                tipo_comprobante="BOLETA",
                documento="12345678",
            )

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["tipo_comprobante"], "BOLETA")
        self.assertEqual(resultado["tipo_contribuyente"], "PERSONA")
        self.assertEqual(
            guardar.call_args.kwargs["tipo_contribuyente"], "PERSONA"
        )

    def test_factura_se_persiste_como_empresa(self):
        with patch(
            "app.identidad.services.validar_ruc_facturacion",
            return_value={
                "ok": True,
                "empresa": {
                    "ruc": "20123456789",
                    "razon_social": "EMPRESA SULPAA SAC",
                    "direccion": "LIMA",
                },
            },
        ), patch(
            "app.identidad.services.guardar_datos_facturacion",
            return_value="facturacion-empresa",
        ) as guardar:
            resultado = identidad_services.registrar_facturacion_checkout(
                usuario_id=USUARIO_ID,
                tipo_comprobante="FACTURA",
                documento="20123456789",
            )

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["tipo_comprobante"], "FACTURA")
        self.assertEqual(resultado["tipo_contribuyente"], "EMPRESA")
        self.assertEqual(
            guardar.call_args.kwargs["tipo_contribuyente"], "EMPRESA"
        )

    def test_alias_tipo_sigue_compatible_con_checkout_anterior(self):
        with patch(
            "app.identidad.services.validar_dni_con_perfil",
            return_value={
                "ok": True,
                "persona": {
                    "dni": "12345678",
                    "nombre_completo": "ANA PEREZ GOMEZ",
                },
            },
        ), patch(
            "app.identidad.services.guardar_datos_facturacion",
            return_value="facturacion-persona",
        ):
            resultado = identidad_services.registrar_facturacion_checkout(
                usuario_id=USUARIO_ID,
                tipo="BOLETA",
                documento="12345678",
            )
        self.assertTrue(resultado["ok"])

    def test_tipo_de_comprobante_invalido_no_persiste(self):
        with patch(
            "app.identidad.services.guardar_datos_facturacion"
        ) as guardar:
            resultado = identidad_services.registrar_facturacion_checkout(
                usuario_id=USUARIO_ID,
                tipo_comprobante="PERSONA",
                documento="12345678",
            )
        self.assertFalse(resultado["ok"])
        guardar.assert_not_called()


class PerfilPersistenciaTest(unittest.TestCase):
    """Comprueba que la baja sea lógica y que el SQL se acote al titular."""

    def test_no_existen_borrados_fisicos_en_el_modulo(self):
        fuente = inspect.getsource(perfil_repositories)
        self.assertNotIn("DELETE FROM direcciones", fuente)
        self.assertNotIn("DELETE FROM datos_facturacion", fuente)
        self.assertIn("estado = 'INACTIVA'", fuente)
        self.assertIn("estado = 'INACTIVO'", fuente)

    def test_consultas_de_direcciones_y_facturacion_filtran_por_usuario(self):
        fuente = inspect.getsource(perfil_repositories)
        self.assertGreaterEqual(
            fuente.count("usuario_id = %s"),
            6,
        )
        self.assertIn("WHERE id = %s AND usuario_id = %s", fuente)


class InterfazFase43Test(unittest.TestCase):
    """Contratos estáticos de menús, plantilla y migración."""

    def test_menus_enlazan_al_perfil_real(self):
        for ruta in (
            RAIZ / "templates/components/navbar.html",
            RAIZ / "templates/admin/components/sidebar.html",
            RAIZ / "templates/repartidor/components/cabecera.html",
        ):
            with self.subTest(ruta=ruta.name):
                contenido = ruta.read_text(encoding="utf-8")
                self.assertIn("url_for('perfil.inicio')", contenido)

    def test_navbar_no_deja_el_perfil_con_href_vacio(self):
        contenido = (
            RAIZ / "templates/components/navbar.html"
        ).read_text(encoding="utf-8")
        self.assertNotRegex(
            contenido,
            r'href="#"[^>]*class="navbar-(user|mobile-link)"[^>]*>\s*Mi perfil',
        )

    def test_plantilla_protege_dni_nombres_y_correo(self):
        contenido = (
            RAIZ / "templates/perfil/inicio.html"
        ).read_text(encoding="utf-8")
        self.assertIn("csrf_token()", contenido)
        self.assertNotIn('name="dni"', contenido)
        self.assertNotIn('name="nombres"', contenido)
        self.assertNotIn('name="correo"', contenido)
        self.assertIn("no pueden editarse", contenido)
        self.assertIn("no demuestra titularidad", contenido)
        self.assertIn("data-profile-form", contenido)

    def test_hoja_de_estilos_tiene_adaptacion_movil(self):
        contenido = (
            RAIZ / "static/css/pages/profile.css"
        ).read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 700px)", contenido)
        self.assertIn(".profile-tabs", contenido)

    def test_javascript_usa_las_notificaciones_globales(self):
        contenido = (
            RAIZ / "static/js/modules/profile.js"
        ).read_text(encoding="utf-8")
        self.assertIn("window.SulpaaToast.show", contenido)
        self.assertIn("validarFormulario", contenido)

    def test_migracion_prepara_indice_unico_sin_ejecutarse(self):
        ruta = RAIZ / "migrations/003_fase43_perfil_dni.sql"
        self.assertTrue(ruta.exists())
        contenido = ruta.read_text(encoding="utf-8")
        self.assertIn("NO EJECUTAR EN PRODUCCIÓN", contenido)
        self.assertIn("HAVING COUNT(*) > 1", contenido)
        self.assertIn("dni NOT REGEXP '^[0-9]{8}$'", contenido)
        self.assertIn("varios NULL", contenido)
        self.assertIn("ADD UNIQUE INDEX uq_perfiles_dni (dni)", contenido)

    def test_limite_compartido_queda_preparado_pero_no_activado(self):
        ruta = RAIZ / "migrations/005_fase43_limite_apisperu_compartido.sql"
        contenido = ruta.read_text(encoding="utf-8")
        self.assertIn("NO EJECUTAR NI ACTIVAR", contenido)
        self.assertIn("SELECT ... FOR UPDATE", contenido)
        self.assertIn("clave_hash", contenido)
        self.assertIn("HMAC-SHA256", contenido)

    def test_rol_cliente_tiene_precheck_sin_modificar_cuentas(self):
        ruta = RAIZ / "migrations/004_fase43_rol_cliente.sql"
        contenido = ruta.read_text(encoding="utf-8")
        self.assertIn("NO EJECUTAR EN PRODUCCIÓN", contenido)
        self.assertIn("WHERE codigo = 'CLIENTE'", contenido)
        self.assertIn("WHERE NOT EXISTS", contenido)
        self.assertNotIn("INSERT INTO usuario_roles", contenido)


if __name__ == "__main__":
    unittest.main()
