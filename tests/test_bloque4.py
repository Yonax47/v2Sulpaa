"""Pruebas del Bloque 4: flujo de caja, reportes gerenciales, encuestas y KPIs.

Estrategia (patrón de la casa):
- Los permisos HTTP se validan con roles reales (servidor TESTING).
- Las reglas de negocio y transacciones se prueban con mocks de
  repositorios y conexiones para no tocar MySQL.
- El dashboard del Bloque 4 (KPI-05, KPI-09, gráficos) se valida con
  las métricas reales de solo lectura parcheadas.
"""

import io
import os
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from app import create_app


def cliente_con_sesion(app, roles, usuario="actor-prueba"):
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion.update({
            "autenticado": True,
            "usuario_id": usuario,
            "correo": "actor@example.test",
            "roles": roles or [],
        })
    return cliente


# ============================================================
# PERMISOS HTTP — ADMIN FLUJO DE CAJA
# ============================================================

class PermisosHTTPCajaTest(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_listado_permite_roles_caja(self):
        for rol in ("GERENTE", "ADMINISTRADOR"):
            with self.subTest(rol=rol), patch(
                "app.admin.caja.routes.listar_movimientos",
                return_value=[],
            ), patch(
                "app.admin.caja.routes.resumen_caja",
                return_value={"total_movimientos": 0, "ingresos": 0,
                              "egresos": 0, "flujo_neto": 0},
            ), patch(
                "app.admin.caja.routes.listar_categorias",
                return_value=[],
            ):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/caja/"
                    ).status_code,
                    200,
                )

    def test_listado_rechaza_roles_sin_acceso(self):
        for rol in ("REPARTIDOR", "PEDIDOS_LOGISTICA", None):
            with self.subTest(rol=rol):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/caja/"
                    ).status_code,
                    403,
                )

    def test_formulario_nuevo_egreso_permite(self):
        with patch(
            "app.admin.caja.routes.listar_categorias", return_value=[]
        ), patch(
            "app.admin.caja.routes.listar_metodos_pago", return_value=[]
        ):
            self.assertEqual(
                cliente_con_sesion(self.app, ["GERENTE"]).get(
                    "/admin/caja/nuevo-egreso"
                ).status_code,
                200,
            )

    def test_registro_egreso_sin_permiso_rechazado(self):
        respuesta = cliente_con_sesion(self.app, ["INVENTARIO"]).post(
            "/admin/caja/nuevo-egreso",
            data={"categoria_id": "1", "monto": "50", "motivo": "Prueba"},
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_registro_egreso_exitoso_redirige(self):
        with patch(
            "app.admin.caja.routes.registrar_egreso_manual"
        ) as registrar:
            respuesta = cliente_con_sesion(self.app, ["GERENTE"]).post(
                "/admin/caja/nuevo-egreso",
                data={"categoria_id": "1", "monto": "50", "motivo": "Prueba"},
            )
            self.assertEqual(respuesta.status_code, 302)
            self.assertIn("/admin/caja/", respuesta.headers["Location"])
            registrar.assert_called_once()


# ============================================================
# PERMISOS HTTP — ADMIN REPORTES GERENCIALES
# ============================================================

class PermisosHTTPReportesTest(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_panel_permite_roles_reportes(self):
        for rol in ("GERENTE", "ADMINISTRADOR"):
            with self.subTest(rol=rol), patch(
                "app.admin.reportes.routes.tipos_reportes",
                return_value=[],
            ):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/reportes/"
                    ).status_code,
                    200,
                )

    def test_panel_rechaza_roles_sin_acceso(self):
        for rol in ("INVENTARIO", "REPARTIDOR", None):
            with self.subTest(rol=rol):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/reportes/"
                    ).status_code,
                    403,
                )

    def test_generar_sin_permiso_rechazado(self):
        respuesta = cliente_con_sesion(self.app, ["CLIENTE"]).post(
            "/admin/reportes/generar",
            data={"tipo": "KPI", "formato": "PDF"},
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_generar_exitoso_envia_archivo(self):
        with patch(
            "app.admin.reportes.routes.generar_reporte",
            return_value={
                "contenido": b"%PDF-1.4",
                "mimetype": "application/pdf",
                "nombre_archivo": "reporte-test.pdf",
            },
        ):
            respuesta = cliente_con_sesion(self.app, ["GERENTE"]).post(
                "/admin/reportes/generar",
                data={"tipo": "KPI", "formato": "PDF"},
            )
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn("application/pdf", respuesta.headers["Content-Type"])


# ============================================================
# PERMISOS HTTP — ADMIN ENCUESTAS
# ============================================================

class PermisosHTTPEncuestasAdminTest(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_listado_permite_roles_encuestas(self):
        for rol in ("GERENTE", "ADMINISTRADOR"):
            with self.subTest(rol=rol), patch(
                "app.admin.encuestas.routes.listar_encuestas",
                return_value=[],
            ):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/encuestas/"
                    ).status_code,
                    200,
                )

    def test_listado_rechaza_roles_sin_acceso(self):
        for rol in ("REPARTIDOR", "INVENTARIO", None):
            with self.subTest(rol=rol):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/encuestas/"
                    ).status_code,
                    403,
                )

    def test_detalle_invalido_responde_404(self):
        from app.admin.encuestas.services import ReglaEncuestaError
        with patch(
            "app.admin.encuestas.routes.obtener_detalle",
            side_effect=ReglaEncuestaError("No existe"),
        ):
            self.assertEqual(
                cliente_con_sesion(self.app, ["GERENTE"]).get(
                    "/admin/encuestas/999"
                ).status_code,
                404,
            )

    def test_detalle_valido_renderiza_encuesta(self):
        from datetime import datetime
        encuesta = {
            "id": 1, "pedido_id": "p1", "usuario_id": "u1",
            "estado": "RESPONDIDA", "canal": "PORTAL",
            "numero_pedido": "P-100", "origen": "TIENDA",
            "creado_en": datetime(2026, 3, 1, 10, 0),
            "enviado_en": datetime(2026, 3, 1, 11, 0),
            "respondido_en": datetime(2026, 3, 2, 9, 0),
            "calificacion_general": 5, "calificacion_producto": 4,
            "calificacion_entrega": 5, "calificacion_atencion": 4,
            "recomendaria": "SI", "comentario": "Muy buen servicio",
            "eventos": [
                {"tipo": "INVITACION_OK", "detalle": "Enlace disponible",
                 "usuario_responsable_id": None,
                 "creado_en": datetime(2026, 3, 1, 11, 0)},
            ],
        }
        with patch(
            "app.admin.encuestas.routes.obtener_detalle",
            return_value=encuesta,
        ):
            respuesta = cliente_con_sesion(self.app, ["GERENTE"]).get(
                "/admin/encuestas/1"
            )
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn(b"INVITACION_OK", respuesta.data)


# ============================================================
# PORTAL PÚBLICO DE LA ENCUESTA
# ============================================================

class PortalEncuestaTest(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_portal_requiere_sesion(self):
        respuesta = self.app.test_client().get("/encuesta/TOKEN-PRUEBA")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])

    def test_formulario_muestra_pendiente(self):
        with patch(
            "app.encuestas.routes.obtener_encuesta_publica",
            return_value={"estado": "ENVIADA",
                          "numero_pedido": "P-100", "encuesta_id": "e1"},
        ):
            respuesta = cliente_con_sesion(
                self.app, ["CLIENTE"]
            ).get("/encuesta/TOKEN-PRUEBA")
            self.assertEqual(respuesta.status_code, 200)

    def test_ya_respondida_muestra_agradecimiento(self):
        with patch(
            "app.encuestas.routes.obtener_encuesta_publica",
            return_value={"estado": "RESPONDIDA",
                          "numero_pedido": "P-100", "encuesta_id": "e1"},
        ):
            respuesta = cliente_con_sesion(
                self.app, ["CLIENTE"]
            ).get("/encuesta/TOKEN-PRUEBA")
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn("¡Gracias por responder".encode("utf-8"),
                          respuesta.data)

    def test_token_invalido_redirige_inicio(self):
        from app.encuestas.services import ReglaEncuestaError
        with patch(
            "app.encuestas.routes.obtener_encuesta_publica",
            side_effect=ReglaEncuestaError("Enlace no válido"),
        ):
            respuesta = cliente_con_sesion(
                self.app, ["CLIENTE"]
            ).get("/encuesta/TOKEN-PRUEBA")
            self.assertEqual(respuesta.status_code, 302)
            self.assertEqual(respuesta.headers["Location"], "/")

    def test_responder_exitoso_redirige(self):
        with patch("app.encuestas.routes.responder_encuesta"):
            respuesta = cliente_con_sesion(
                self.app, ["CLIENTE"]
            ).post(
                "/encuesta/TOKEN-PRUEBA",
                data={
                    "calificacion_general": "5",
                    "calificacion_producto": "4",
                    "calificacion_entrega": "5",
                    "calificacion_atencion": "4",
                    "recomendaria": "SI",
                    "comentario": "Excelente",
                },
            )
            self.assertEqual(respuesta.status_code, 302)
            self.assertIn("/encuesta/TOKEN-PRUEBA",
                          respuesta.headers["Location"])

    def test_responder_con_regla_invalida_redirige(self):
        from app.encuestas.services import ReglaEncuestaError
        with patch(
            "app.encuestas.routes.responder_encuesta",
            side_effect=ReglaEncuestaError("Ya fue respondida"),
        ):
            respuesta = cliente_con_sesion(
                self.app, ["CLIENTE"]
            ).post("/encuesta/TOKEN-PRUEBA", data={})
            self.assertEqual(respuesta.status_code, 302)


# ============================================================
# REGLAS DE NEGOCIO — VALIDACIÓN DE RESPUESTAS
# ============================================================

class ServicioEncuestaValidacionTest(unittest.TestCase):

    def _validar(self, **datos):
        from app.encuestas.services import validar_respuestas
        base = {
            "calificacion_general": "5",
            "calificacion_producto": "5",
            "calificacion_entrega": "5",
            "calificacion_atencion": "5",
            "recomendaria": "SI",
            "comentario": "",
        }
        base.update(datos)
        return validar_respuestas(base)

    def test_respuesta_valida_se_normaliza(self):
        resultado = self._validar(
            calificacion_producto="3",
            recomendaria="  si  ",
            comentario="   Buen servicio   ",
        )
        self.assertEqual(resultado["calificacion_general"], 5)
        self.assertEqual(resultado["calificacion_producto"], 3)
        self.assertEqual(resultado["recomendaria"], "SI")
        self.assertEqual(resultado["comentario"], "Buen servicio")

    def test_calificacion_fuera_de_rango_rechazada(self):
        from app.encuestas.services import ReglaEncuestaError
        with self.assertRaises(ReglaEncuestaError):
            self._validar(calificacion_general="0")
        with self.assertRaises(ReglaEncuestaError):
            self._validar(calificacion_general="6")

    def test_recomendaria_invalida_rechazada(self):
        from app.encuestas.services import ReglaEncuestaError
        with self.assertRaises(ReglaEncuestaError):
            self._validar(recomendaria="QUIZAS")
        with self.assertRaises(ReglaEncuestaError):
            self._validar(recomendaria="")

    def test_comentario_muy_largo_rechazado(self):
        from app.encuestas.services import ReglaEncuestaError
        with self.assertRaises(ReglaEncuestaError):
            self._validar(comentario="a" * 501)

    def test_reenviar_sin_rol_rechazado(self):
        from app.encuestas.services import (ReglaEncuestaError,
                                            reenviar_invitacion)
        with self.assertRaises(ReglaEncuestaError):
            reenviar_invitacion("u1", ["INVENTARIO"], "e1")


# ============================================================
# TRANSACCIONES — INVITACIÓN PORTAL Y REINTENTO (mock BD)
# ============================================================

class InvitacionEncuestaTest(unittest.TestCase):

    def _conexion_falsa(self):
        conexion = MagicMock()
        mocursor = MagicMock()
        mocursor.__enter__.return_value = mocursor
        conexion.cursor.return_value = mocursor
        return conexion

    def test_publicar_invitacion_pendiente_pasa_a_enviada(self):
        from app.encuestas import services as svc
        encuesta = {
            "id": "e1", "pedido_id": "p1", "usuario_id": "u1",
            "estado": "PENDIENTE", "canal": "PORTAL",
            "token_cifrado": b"cifrado", "enviado_en": None,
            "respondido_en": None,
        }
        with patch.object(
            svc, "esquemas_sulpaa",
            return_value={"operaciones": "op", "comercio": "co"},
        ), patch.object(svc, "conexion_operaciones") as conector, patch(
            "app.encuestas.repositories.buscar_por_pedido",
            return_value=encuesta,
        ), patch(
            "app.encuestas.repositories.bloquear_por_pedido",
            return_value=encuesta,
        ), patch(
            "app.encuestas.repositories.ya_fue_publicada",
            return_value=False,
        ), patch(
            "app.encuestas.repositories.marcar_estado",
        ) as marcar, patch(
            "app.encuestas.repositories.registrar_evento",
        ) as evento, patch.object(svc, "codigos_token") as codigos:
            codigos.descifrar_token.return_value = "TOKEN-XYZ"
            conector.return_value = self._conexion_falsa()

            resultado = svc.publicar_invitacion_lectura("p1", "u1")

            self.assertTrue(resultado["disponible"])
            self.assertEqual(resultado["estado"], "ENVIADA")
            self.assertEqual(resultado["url"], "/encuesta/TOKEN-XYZ")
            marcar.assert_called_once()
            self.assertEqual(marcar.call_args[0][3], "ENVIADA")
            tipos = [llamada.args[3] for llamada in evento.call_args_list]
            self.assertEqual(tipos, ["INVITACION_OK"])

    def test_reenviar_error_envio_rehabilita_invitacion(self):
        from app.encuestas import services as svc
        with patch.object(
            svc, "esquemas_sulpaa",
            return_value={"operaciones": "op", "comercio": "co"},
        ), patch.object(svc, "conexion_operaciones") as conector, patch(
            "app.encuestas.repositories.buscar_por_id",
            return_value={"id": "e1", "estado": "ERROR_ENVIO"},
        ), patch(
            "app.encuestas.repositories.ya_fue_publicada",
            return_value=False,
        ), patch(
            "app.encuestas.repositories.marcar_estado",
        ) as marcar, patch(
            "app.encuestas.repositories.registrar_evento",
        ) as evento:
            conector.return_value = self._conexion_falsa()

            resultado = svc.reenviar_invitacion("u1", ["GERENTE"], "e1")

            self.assertTrue(resultado["ok"])
            self.assertEqual(resultado["estado"], "ENVIADA")
            marcar.assert_called_once()
            self.assertEqual(marcar.call_args[0][3], "ENVIADA")
            tipos = [llamada.args[3] for llamada in evento.call_args_list]
            self.assertIn("REINTENTO", tipos)
            self.assertIn("INVITACION_OK", tipos)


# ============================================================
# KPI — DASHBOARD BLOQUE 4 (05 y 09)
# ============================================================

def _parchear_dashboard(metrica_kpi09, satisfaccion, reportes):
    """Parchea las métricas del dashboard para validar solo lectura."""
    return (
        patch("app.admin.services.obtener_metrica_pedidos_procesados",
              return_value={"pedidos_iniciados": 100,
                            "pedidos_completados": 96}),
        patch("app.admin.services.obtener_metrica_historial_pedidos",
              return_value={"total_pedidos": 100,
                            "pedidos_con_historial": 98}),
        patch("app.admin.services.obtener_metrica_consistencia_estados",
              return_value={"total_pedidos_historial": 100,
                            "estados_consistentes": 98}),
        patch("app.admin.services.obtener_metrica_verificaciones_fisicas",
              return_value={"disponible": True,
                            "total_verificaciones": 100,
                            "verificaciones_ok": 99}),
        patch("app.admin.services.obtener_metrica_consultas_producto",
              return_value={"disponible": True,
                            "total_consultas": 100,
                            "consultas_exitosas": 96}),
        patch("app.admin.services.obtener_metrica_favoritos",
              return_value={"disponible": True,
                            "total_favoritos_ops": 100,
                            "favoritos_exitosos": 96}),
        patch("app.admin.services.obtener_metrica_accesos_contenido",
              return_value={"disponible": True,
                            "total_accesos": 100,
                            "accesos_exitosos": 96}),
        patch("app.admin.services.obtener_metrica_kpi09",
              return_value=metrica_kpi09),
        patch("app.admin.services.obtener_metrica_satisfaccion",
              return_value=satisfaccion),
        patch("app.admin.services.obtener_metrica_reportes",
              return_value=reportes),
        patch("app.admin.caja.services.serie_flujo_mensual",
              return_value=[
                  {"periodo": "2026-03", "ingresos": 500.0, "egresos": 50.0},
                  {"periodo": "2026-04", "ingresos": 700.0, "egresos": 80.0},
              ]),
        # Bloque operativo del resumen ejecutivo (datos reales defensivos):
        patch(
            "app.admin.inventario.repositories.listar_existencias_detalladas",
            return_value=[],
        ),
        patch(
            "app.admin.caja.services.resumen_caja",
            return_value={"ingresos": 0.0, "egresos": 0.0,
                          "flujo_neto": 0.0},
        ),
    )


def _resumen_dashboard(metrica_kpi09, satisfaccion, reportes):
    """Ejecuta resumen_dashboard con las métricas del Bloque 4 parcheadas."""
    from app.admin.services import resumen_dashboard
    with ExitStack() as pila:
        for parche in _parchear_dashboard(metrica_kpi09, satisfaccion,
                                          reportes):
            pila.enter_context(parche)
        return resumen_dashboard()


class KPIDashboardBloque4Test(unittest.TestCase):
    """KPI-09 con la fórmula OFICIAL (invitaciones OK / entregados elegibles)."""

    def _satisfaccion(self):
        return {
            "disponible": True,
            "total_encuestas": 100,
            "encuestas_completadas": 100,
            "encuestas_enviadas": 90,
            "satisfaccion_promedio": 4.2,
            "promedio_producto": 4.3,
            "promedio_entrega": 4.1,
            "promedio_atencion": 4.4,
            "recomendacion_porcentaje": 92.0,
            "tasa_respuesta_porcentaje": 90.0,
            "respuestas_satisfactorias": 92,
        }

    def _reportes(self):
        return {
            "disponible": True,
            "total_solicitudes": 100,
            "solicitudes_exitosas": 96,
        }

    def _por_codigo(self, resumen):
        return {kpi["codigo"]: kpi
                for kpi in resumen["kpis_funcionales"]}

    def test_kpi05_y_kpi09_usan_metas_reales(self):
        metrica_kpi09 = {
            "disponible": True,
            "invitaciones_ok": 9,
            "pedidos_entregados": 10,
        }
        resumen = _resumen_dashboard(
            metrica_kpi09, self._satisfaccion(), self._reportes())

        por_codigo = self._por_codigo(resumen)
        self.assertIn("KPI-05", por_codigo)
        self.assertIn("KPI-09", por_codigo)
        self.assertEqual(por_codigo["KPI-05"]["valor"], 96.0)
        self.assertEqual(por_codigo["KPI-05"]["estado"], "cumple")
        self.assertEqual(por_codigo["KPI-09"]["valor"], 90.0)
        self.assertEqual(por_codigo["KPI-09"]["estado"], "cumple")
        self.assertEqual(por_codigo["KPI-09"]["numerador"], 9)
        self.assertEqual(por_codigo["KPI-09"]["denominador"], 10)

        graficos = resumen["graficos"]
        self.assertEqual(len(graficos["flujo_caja"]), 2)
        self.assertEqual(graficos["flujo_caja"][0]["periodo"], "2026-03")
        self.assertEqual(graficos["kpi09"]["invitaciones_ok"], 9)
        self.assertEqual(graficos["kpi09"]["pedidos_entregados"], 10)
        self.assertEqual(graficos["kpi09"]["valor"], 90.0)

    def test_kpi09_ocho_de_diez_no_cumple(self):
        metrica_kpi09 = {
            "disponible": True,
            "invitaciones_ok": 8,
            "pedidos_entregados": 10,
        }
        resumen = _resumen_dashboard(
            metrica_kpi09, self._satisfaccion(), self._reportes())

        kpi09 = self._por_codigo(resumen)["KPI-09"]
        self.assertEqual(kpi09["valor"], 80.0)
        self.assertEqual(kpi09["estado"], "no_cumple")

    def test_kpi09_pendiente_cuando_no_hay_entregados(self):
        metrica_kpi09 = {
            "disponible": True,
            "invitaciones_ok": 4,
            "pedidos_entregados": 0,
        }
        resumen = _resumen_dashboard(
            metrica_kpi09, self._satisfaccion(), self._reportes())

        kpi09 = self._por_codigo(resumen)["KPI-09"]
        self.assertIsNone(kpi09["valor"])
        self.assertEqual(kpi09["estado"], "pendiente")
        self.assertIsNone(resumen["graficos"]["kpi09"]["valor"])

    def test_kpi09_pendiente_sin_evidencia(self):
        metrica_kpi09 = {
            "disponible": False,
            "invitaciones_ok": None,
            "pedidos_entregados": None,
        }
        resumen = _resumen_dashboard(
            metrica_kpi09, {"disponible": False}, self._reportes())

        kpi09 = self._por_codigo(resumen)["KPI-09"]
        self.assertIsNone(kpi09["valor"])
        self.assertEqual(kpi09["estado"], "pendiente")
        self.assertIsNone(resumen["graficos"]["kpi09"])
        self.assertIsNone(resumen["graficos"]["satisfaccion"])

    def test_kpi09_no_lo_altera_la_satisfaccion(self):
        metrica_kpi09 = {
            "disponible": True,
            "invitaciones_ok": 6,
            "pedidos_entregados": 10,
        }
        satisfaccion = self._satisfaccion()
        satisfaccion["satisfaccion_promedio"] = 5.0
        satisfaccion["respuestas_satisfactorias"] = 100
        resumen = _resumen_dashboard(
            metrica_kpi09, satisfaccion, self._reportes())

        kpi09 = self._por_codigo(resumen)["KPI-09"]
        self.assertEqual(kpi09["valor"], 60.0)
        self.assertEqual(kpi09["estado"], "no_cumple")
        self.assertEqual(
            resumen["graficos"]["satisfaccion"]["satisfaccion_promedio"],
            5.0)


class RepositorioKPI09Test(unittest.TestCase):
    """El SQL oficial del KPI-09 (COUNT DISTINCT e INVITACION_OK)."""

    def test_kpi09_usa_count_distinct_pedidos_invitacion_ok(self):
        import app.admin.repositories as repo

        tablas_reales = [{"total": 2}]
        conteos = [{"invitaciones_ok": 9, "pedidos_entregados": 10}]
        filas = iter(tablas_reales + conteos)
        queries = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *extras):
                return False

            def execute(self, sql, parametros=None):
                queries.append(sql)

            def fetchone(self):
                return next(filas)

        conexion = MagicMock()
        conexion.cursor.return_value = Cursor()
        with patch.object(repo, "conexion_operaciones",
                          return_value=conexion) as conecta, patch.dict(
            os.environ, {"DB_OPERACIONES": "op_v2"}, clear=False,
        ):
            metrica = repo.obtener_metrica_kpi09()

        self.assertTrue(metrica["disponible"])
        self.assertEqual(metrica["invitaciones_ok"], 9)
        self.assertEqual(metrica["pedidos_entregados"], 10)
        sql = queries[1]
        self.assertIn("COUNT(DISTINCT e.pedido_id)", sql)
        self.assertIn("'INVITACION_OK'", sql)
        self.assertIn("'ENTREGADO'", sql)
        self.assertNotIn("RESPONDIDA", sql)
        self.assertNotIn("encuesta_respuestas", sql)


# ============================================================
# RONDA FINAL — DASHBOARD EJECUTIVO Y PÁGINA INDICADORES KPI
# ============================================================

class DashboardEjecutivoBloque4Test(unittest.TestCase):
    """Concepto corregido: instrumentado vs evidencia y regla del 0%."""

    def _satisfaccion(self):
        return {
            "disponible": True,
            "total_encuestas": 100,
            "encuestas_completadas": 100,
            "encuestas_enviadas": 90,
            "satisfaccion_promedio": 4.2,
            "promedio_producto": 4.3,
            "promedio_entrega": 4.1,
            "promedio_atencion": 4.4,
            "recomendacion_porcentaje": 92.0,
            "tasa_respuesta_porcentaje": 90.0,
            "respuestas_satisfactorias": 92,
        }

    def test_diez_kpi_instrumentados(self):
        metrica_kpi09 = {
            "disponible": True, "invitaciones_ok": 9,
            "pedidos_entregados": 10,
        }
        resumen = _resumen_dashboard(
            metrica_kpi09, self._satisfaccion(), self._reportes())

        por_codigo = {
            kpi["codigo"] for kpi in resumen["kpis_funcionales"]
        }
        self.assertEqual(por_codigo, {f"KPI-{i:02d}" for i in range(1, 11)})
        self.assertEqual(resumen["resumen"]["total"], 10)
        self.assertEqual(resumen["resumen"]["instrumentados"], 10)
        self.assertEqual(resumen["resumen"]["con_evidencia"], 9)

    def test_estado_por_codigo_incluye_detalle_nuevo(self):
        metrica_kpi09 = {
            "disponible": True, "invitaciones_ok": 9,
            "pedidos_entregados": 10,
        }
        resumen = _resumen_dashboard(
            metrica_kpi09, self._satisfaccion(), self._reportes())
        por_codigo = {
            kpi["codigo"]: kpi
            for kpi in resumen["kpis_funcionales"]
        }
        kpi = por_codigo["KPI-05"]
        self.assertIn("numerador", kpi)
        self.assertIn("denominador", kpi)
        self.assertIn("formula", kpi)
        self.assertIn("evidencia_requerida", kpi)
        self.assertEqual(kpi["numerador"], 96)
        self.assertEqual(kpi["denominador"], 100)

    def test_denominador_cero_queda_pendiente(self):
        # KPI-01/04/07/08 con denominador 0 NUNCA muestran 0%: PENDIENTE.
        from app.admin.services import resumen_dashboard
        parametros = {
            "metrica_kpi09": {"disponible": True, "invitaciones_ok": 9,
                              "pedidos_entregados": 10},
            "satisfaccion": self._satisfaccion(),
            "reportes": self._reportes(),
        }
        parches = _parchear_dashboard(**parametros)
        ceros = (
            # Denominadores en cero en las cuatro métricas base afectadas.
            patch("app.admin.services.obtener_metrica_pedidos_procesados",
                  return_value={"pedidos_iniciados": 0,
                                "pedidos_completados": 0}),
            patch("app.admin.services.obtener_metrica_historial_pedidos",
                  return_value={"total_pedidos": 0,
                                "pedidos_con_historial": 0}),
            patch("app.admin.services.obtener_metrica_consistencia_estados",
                  return_value={"total_pedidos_historial": 0,
                                "estados_consistentes": 0}),
        )
        with ExitStack() as pila:
            for parche in (*parches, *ceros):
                pila.enter_context(parche)
            resumen = resumen_dashboard()
        por_codigo = {
            kpi["codigo"]: kpi
            for kpi in resumen["kpis_funcionales"]
        }
        for codigo in ("KPI-01", "KPI-04", "KPI-07", "KPI-08"):
            self.assertIsNone(por_codigo[codigo]["valor"], codigo)
            self.assertEqual(
                por_codigo[codigo]["estado"], "pendiente", codigo)

    def test_pendiente_no_cuenta_como_no_cumple(self):
        # KPI-09 sin evidencia: nada de PENDIENTE debe inflar no_cumplen.
        resumen = _resumen_dashboard(
            {"disponible": False}, {"disponible": False},
            {"disponible": False})
        res = resumen["resumen"]
        pendientes = res["pendientes_de_datos"]
        self.assertEqual(
            pendientes + res["con_evidencia"], res["total"])
        # Ninguna tarjeta reporta "no instrumentado": los 10 están
        # instrumentados y la diferencia solo es "pendiente de datos".
        self.assertEqual(res["instrumentados"], 10)
        self.assertEqual(
            res["no_cumplen"],
            10 - res["cumplen"] - pendientes,
        )

    def _reportes(self):
        return {
            "disponible": True,
            "total_solicitudes": 100,
            "solicitudes_exitosas": 96,
        }


class RutaIndicadoresKPITest(unittest.TestCase):
    """Página analítica independiente (fuente única de resumen_dashboard)."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_ruta_kpi_permite_roles_administrativos(self):
        for rol in ("GERENTE", "ADMINISTRADOR"):
            with self.subTest(rol=rol), patch(
                "app.admin.routes.resumen_dashboard",
                return_value={
                    "kpis_funcionales": [],
                    "resumen": {
                        "total": 10, "instrumentados": 10,
                        "con_evidencia": 5, "pendientes_de_datos": 5,
                        "cumplen": 3, "no_cumplen": 2,
                    },
                },
            ):
                respuesta = cliente_con_sesion(self.app, [rol]).get(
                    "/admin/kpi/")
                self.assertEqual(respuesta.status_code, 200)

    def test_ruta_kpi_rechaza_roles_sin_acceso(self):
        for rol in ("INVENTARIO", "REPARTIDOR", None):
            with self.subTest(rol=rol):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/kpi/").status_code,
                    403,
                )

    def test_dashboard_y_kpi_comparten_fuente(self):
        # Ambos endpoints consumen resumen_dashboard() (fuente única):
        # un mismo resumen aparece en el dashboard y en /admin/kpi/.
        resumen_compartido = {
            "kpis_funcionales": [
                {"codigo": "KPI-01", "nombre": "Pedidos correctos",
                 "clasificacion": "RF-01", "meta": "≥95%",
                 "valor": None, "numerador": 0, "denominador": 0,
                 "formula": "x/y", "estado": "pendiente",
                 "evidencia_requerida": "pedidos con historial",
                 "fuente": "comercio.pedidos"},
            ],
            "resumen": {
                "total": 10, "instrumentados": 10,
                "con_evidencia": 0, "pendientes_de_datos": 10,
                "cumplen": 0, "no_cumplen": 0,
            },
            "graficos": {"flujo_caja": [], "kpi09": None,
                         "satisfaccion": None},
            "operativo": {
                "pedidos_iniciados": 0, "pedidos_completados": 0,
                "entregas": 0, "productos_con_stock_bajo": 0,
                "ingresos": 0.0, "egresos": 0.0, "flujo_neto": 0.0,
                "encuestas_completadas": 0, "satisfaccion_promedio": None,
            },
        }
        with patch("app.admin.routes.resumen_dashboard",
                   return_value=resumen_compartido):
            cliente = cliente_con_sesion(self.app, ["GERENTE"])
            dashboard = cliente.get("/admin/dashboard")
            kpi = cliente.get("/admin/kpi/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(kpi.status_code, 200)
        self.assertIn(b"KPI-01", dashboard.data)
        self.assertIn(b"KPI-01", kpi.data)
        self.assertIn(b"Sin evidencia suficiente", kpi.data)


class SidebarSinProximamenteTest(unittest.TestCase):
    """El sidebar nuevo no ofrece "Próximamente" ni anclas obsoletas."""

    def test_componente_sin_proximamente_ni_ancla_indicadores(self):
        with open("templates/admin/components/sidebar.html",
                  encoding="utf-8") as archivo:
            contenido = archivo.read()
        self.assertNotIn("Próximamente", contenido)
        self.assertNotIn("#indicadores", contenido)
        self.assertIn("admin.indicadores", contenido)

    def test_dashboard_render_sin_proximamente(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)
        with patch(
            "app.admin.routes.resumen_dashboard",
            return_value={
                "kpis_funcionales": [],
                "resumen": {
                    "total": 10, "instrumentados": 10,
                    "con_evidencia": 0, "pendientes_de_datos": 10,
                    "cumplen": 0, "no_cumplen": 0,
                },
                "graficos": {"flujo_caja": [], "kpi09": None,
                             "satisfaccion": None},
                "operativo": {
                    "pedidos_iniciados": 0, "pedidos_completados": 0,
                    "entregas": 0, "productos_con_stock_bajo": 0,
                    "ingresos": 0.0, "egresos": 0.0, "flujo_neto": 0.0,
                    "encuestas_completadas": 0,
                    "satisfaccion_promedio": None,
                },
            },
        ):
            respuesta = cliente_con_sesion(self.app, ["GERENTE"]).get(
                "/admin/dashboard")
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn(b"Pr\u00f3ximamente", respuesta.data)


# ============================================================
# RONDA FINAL — REPORTES PEDIDOS / INVENTARIO / ENTREGAS
# ============================================================

class ReportesNuevosTiposTest(unittest.TestCase):
    """Los tres reportes nuevos generan archivos reales (PDF/XLSX/CSV)."""

    def _datos_ventas_mock(self, desde=None, hasta=None):
        from datetime import datetime
        return [
            {"numero_pedido": "P-100", "origen": "TIENDA",
             "estado": "COMPLETADO", "total": 125.5, "moneda": "PEN",
             "creado_en": datetime(2026, 1, 10, 10, 0)},
            {"numero_pedido": "P-101", "origen": "WEB",
             "estado": "EN_PREPARACION", "total": 60.0,
             "moneda": "PEN", "creado_en": datetime(2026, 1, 11, 11, 0)},
        ]

    def _existencias_mock(self, busqueda=None, solo_bajo_minimo=False):
        return [
            {"almacen_codigo": "SUR", "sku": "KB-500",
             "nombre_comercial": "Kombucha Jengibre",
             "sabor": "Jengibre", "presentacion": "500 ml",
             "stock_fisico": 4, "stock_reservado": 1,
             "stock_disponible": 3, "stock_minimo": 5,
             "bajo_minimo": True},
        ]

    def _entregas_mock(self, desde=None, hasta=None):
        from datetime import datetime
        return [
            {"numero_pedido": "P-100", "tipo_entrega": "DELIVERY_LOCAL",
             "estado": "ENTREGADO",
             "fecha_programada": datetime(2026, 1, 10, 9, 0),
             "completado_en": datetime(2026, 1, 10, 12, 0),
             "repartidor_detalle": "Juan Pérez",
             "moneda": "PEN", "costo_cobrado_cliente": 8.0},
        ]

    def test_pedidos_genera_en_todos_los_formatos(self):
        for formato in ("PDF", "XLSX", "CSV"):
            with self.subTest(formato=formato), patch(
                "app.admin.reportes.services.obtener_datos_ventas",
                side_effect=self._datos_ventas_mock,
            ), patch(
                "app.admin.reportes.repositories.registrar_solicitud_reporte",
                return_value=True,
            ):
                resultado = _generar("PEDIDOS", formato)
            self.assertTrue(resultado["ok"], formato)
            self.assertTrue(resultado["contenido"], formato)
            self.assertIn("reporte_pedidos", resultado["nombre_archivo"])

    def test_inventario_genera_en_todos_los_formatos(self):
        for formato in ("PDF", "XLSX", "CSV"):
            with self.subTest(formato=formato), patch(
                "app.admin.inventario.repositories."
                "listar_existencias_detalladas",
                return_value=self._existencias_mock(),
            ), patch(
                "app.admin.reportes.repositories.registrar_solicitud_reporte",
                return_value=True,
            ):
                resultado = _generar("INVENTARIO", formato)
            self.assertTrue(resultado["ok"], formato)
            self.assertTrue(resultado["contenido"], formato)

    def test_entregas_genera_en_todos_los_formatos(self):
        for formato in ("PDF", "XLSX", "CSV"):
            with self.subTest(formato=formato), patch(
                "app.admin.reportes.services.listar_entregas_reporte",
                side_effect=self._entregas_mock,
            ), patch(
                "app.admin.reportes.repositories.registrar_solicitud_reporte",
                return_value=True,
            ):
                resultado = _generar("ENTREGAS", formato)
            self.assertTrue(resultado["ok"], formato)
            self.assertTrue(resultado["contenido"], formato)

    def test_los_tres_auditan_kpi05(self):
        # Cada generación registra la solicitud (denominador KPI-05) y el
        # EXITO alimenta el numerador (mismo mecanismo que los 4 previos).
        casos = [
            ("PEDIDOS", "app.admin.reportes.services.obtener_datos_ventas",
             self._datos_ventas_mock),
            ("INVENTARIO",
             "app.admin.inventario.repositories."
             "listar_existencias_detalladas",
             lambda **x: self._existencias_mock()),
            ("ENTREGAS", "app.admin.reportes.services.listar_entregas_reporte",
             self._entregas_mock),
        ]
        for tipo, ruta, datos in casos:
            with self.subTest(tipo=tipo), patch(ruta, side_effect=datos), \
                 patch(
                    "app.admin.reportes.repositories."
                    "registrar_solicitud_reporte",
                ) as registrar:
                _generar(tipo, "CSV")
            self.assertEqual(registrar.call_count, 1, tipo)
            llamada = registrar.call_args.kwargs
            self.assertEqual(llamada["tipo_reporte"], tipo)
            self.assertEqual(llamada["resultado"], "EXITO")

    def test_tipo_invalido_rechazado(self):
        from app.admin.reportes.services import (
            ReglaReporteError, generar_reporte,
        )
        with self.assertRaises(ReglaReporteError):
            generar_reporte("NO_EXISTE", "CSV", "u1")


class PermisosReportesNuevosTest(unittest.TestCase):
    """Los tres reportes nuevos exigen GERENTE/ADMINISTRADOR (backend)."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_generar_nuevos_tipos_rechaza_roles_sin_acceso(self):
        from tests.test_bloque4 import cliente_con_sesion as ccs
        for tipo in ("PEDIDOS", "INVENTARIO", "ENTREGAS"):
            with self.subTest(tipo=tipo):
                respuesta = ccs(self.app, ["INVENTARIO"]).post(
                    "/admin/reportes/generar",
                    data={"tipo": tipo, "formato": "PDF"},
                )
                self.assertEqual(respuesta.status_code, 403)

    def test_generar_nuevos_tipos_permite_gerente(self):
        for tipo in ("PEDIDOS", "INVENTARIO", "ENTREGAS"):
            with self.subTest(tipo=tipo), patch(
                "app.admin.reportes.routes.generar_reporte",
                return_value={
                    "contenido": b"archivo", "mimetype": "text/csv",
                    "nombre_archivo": f"reporte_{tipo.lower()}.csv",
                },
            ):
                respuesta = cliente_con_sesion(self.app, ["GERENTE"]).post(
                    "/admin/reportes/generar",
                    data={"tipo": tipo, "formato": "CSV"},
                )
                self.assertEqual(respuesta.status_code, 200)


def _generar(tipo, formato):
    """Genera un reporte realista sin BD (repos parcheados)."""
    from app.admin.reportes.services import generar_reporte
    filtros = {"desde": "2026-01-01", "hasta": "2026-01-31"}
    return generar_reporte(tipo, formato, "actor-prueba", filtros)


# ============================================================
# RONDA FINAL — FILTROS DE CAJA CONSISTENTES (cards = tabla)
# ============================================================

class FiltrosCajaConsistentesTest(unittest.TestCase):
    """El resumen (cards) respeta los mismos filtros que la tabla."""

    def test_resumen_caja_pasa_todos_los_filtros(self):
        from app.admin.caja import services as svc
        filtros = {
            "desde": "2026-01-01", "hasta": "2026-01-31",
            "tipo": "EGRESO", "origen": "MANUAL",
            "categoria_id": "3",
        }
        with patch.object(svc.repos, "resumen_movimientos",
                          return_value={
                              "ingresos": 0, "egresos": 50,
                              "flujo_neto": -50, "total_movimientos": 1,
                          }) as resumen:
            svc.resumen_caja(filtros)
        kwargs = resumen.call_args.kwargs
        self.assertEqual(kwargs["tipo"], "EGRESO")
        self.assertEqual(kwargs["origen"], "MANUAL")
        self.assertEqual(kwargs["categoria_id"], "3")
        self.assertEqual(kwargs["desde"], "2026-01-01")
        self.assertEqual(kwargs["hasta"], "2026-01-31")

    def test_listado_y_resumen_usan_los_mismos_filtros(self):
        from app.admin.caja.services import (
            listar_movimientos, resumen_caja,
        )
        filtros = {
            "desde": "2026-01-01", "hasta": "2026-01-31",
            "tipo": "INGRESO", "origen": "AUTOMATICO",
            "categoria_id": None,
        }
        with patch.object(
            listar_movimientos.__globals__["repos"],
            "listar_movimientos", return_value=[],
        ) as lista, patch.object(
            resumen_caja.__globals__["repos"],
            "resumen_movimientos", return_value={},
        ) as resumen:
            listar_movimientos(filtros)
            resumen_caja(filtros)
        args_lista = lista.call_args
        args_resumen = resumen.call_args
        for campo in ("desde", "hasta", "tipo", "origen"):
            self.assertEqual(args_lista.kwargs[campo],
                             args_resumen.kwargs[campo], campo)


# ============================================================
# RONDA FINAL — REGRESIÓN: ENTREGA → PAGO → CAJA → ENCUESTA
# ============================================================

class RegresionFlujoPagoCajaEncuestaTest(unittest.TestCase):
    """El cierre de entrega cobra, pasa el pago PAGADO, crea ingreso de
    caja y habilita la encuesta (flujo extremo a extremo con mocks)."""

    def _unidad_falsa(self):
        unidad = MagicMock()
        unidad.esquemas = {
            "operaciones": "op", "comercio": "co", "identidad": "id",
        }
        return unidad

    def test_gestionar_cobro_contra_entrega_marca_pagado_e_ingresa(self):
        from app.operaciones import services as svc
        unidad = self._unidad_falsa()
        pago = {"id": "pg1", "modalidad": "CONTRA_ENTREGA",
                "estado": "PENDIENTE"}
        with patch.object(svc._repos, "confirmar_pago_operativo",
                          return_value=True) as confirmar, patch.object(
            svc._repos, "insertar_ingreso_caja_desde_pago",
        ) as ingreso:
            svc._gestionar_cobro(
                unidad, pago, "CONTRA_ENTREGA", "DELIVERY_LOCAL",
                "actor-1", "Cobro contra entrega.",
            )
        confirmar.assert_called_once()
        ingreso.assert_called_once_with(
            unidad.conexion, unidad.esquemas, pago)

    def test_gestionar_cobro_anticipado_ya_pagado_no_duplica_pago(self):
        from app.operaciones import services as svc
        unidad = self._unidad_falsa()
        pago = {"id": "pg2", "modalidad": "ANTICIPADO",
                "estado": "PAGADO"}
        with patch.object(svc._repos, "confirmar_pago_operativo") as confirmar, \
             patch.object(svc._repos, "insertar_ingreso_caja_desde_pago",
                          ) as ingreso:
            svc._gestionar_cobro(
                unidad, pago, None, "DELIVERY_LOCAL", "actor-1", "")
        confirmar.assert_not_called()
        ingreso.assert_called_once_with(
            unidad.conexion, unidad.esquemas, pago)

    def test_finalizar_pedido_habilita_encuesta(self):
        from app.operaciones import services as svc
        unidad = self._unidad_falsa()
        pedido = {"id": "pd1", "estado": "EN_PREPARACION"}
        filas = iter([
            {"estado": "ENTREGADO", "completado_en": "2026-01-10"},
            {"estado": "PAGADO", "pagado_en": "2026-01-10"},
            {"total": 0},
            None, None, {"total": 0},
        ])

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *extras):
                return False

            def execute(self, sql, parametros=None):
                pass

            def fetchone(self):
                return next(filas, None)

        conexion = MagicMock()
        conexion.cursor.return_value = Cursor()
        unidad.conexion = conexion

        with patch.object(
            svc, "cursor_pedido_estado", return_value=pedido,
        ), patch.object(
            svc._repos, "fetchone_safe",
            side_effect=lambda cursor: cursor.fetchone(),
        ), patch.object(
            svc._repos, "actualizar_pedido_completado",
            return_value=True,
        ) as completar, patch(
            "app.encuestas.services.crear_encuesta_tras_completar",
        ) as crear_encuesta:
            resultado = svc._evaluar_finalizacion_pedido(
                unidad, "pd1", "actor-1", "Entrega confirmada.")

        self.assertTrue(resultado)
        completar.assert_called_once()
        crear_encuesta.assert_called_once_with(unidad, "pd1")


# ============================================================
# RONDA FINAL — CONTENIDO EDUCATIVO BORRADOR/PUBLICADO
# ============================================================

class ContenidoBorradorPublicadoTest(unittest.TestCase):
    """BORRADOR nunca es público; PUBLICADO sí (accesos KPI-10 reales)."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_borrador_no_aparece_en_portada(self):
        with patch(
            "app.aprende.routes.listar_publico",
            return_value=[
                {"id": 1, "slug": "que-es", "titulo": "Qué es",
                 "tipo": "QUE_ES"},  # BORRADOR excluido por repo
            ],
        ):
            respuesta = self.app.test_client().get("/aprende")
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn(b"borrador", respuesta.data.lower())

    def test_borrador_responde_404_publico(self):
        with patch(
            "app.aprende.routes.obtener_detalle_publico",
            return_value=None,
        ):
            respuesta = self.app.test_client().get("/aprende/borrador-x")
        self.assertEqual(respuesta.status_code, 404)

    def test_contenido_publicado_renderiza(self):
        with patch(
            "app.aprende.routes.obtener_detalle_publico",
            return_value={
                "id": 1, "slug": "que-es", "titulo": "Qué es la kombucha",
                "tipo": "QUE_ES", "contenido": "<p>Contenido real</p>",
            },
        ):
            respuesta = self.app.test_client().get("/aprende/que-es")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Qué es la kombucha".encode("utf-8"),
                      respuesta.data)


# ============================================================
# AJUSTE FINAL — LOS 7 REPORTES Y AUDITORÍA KPI-05
# ============================================================

def _resumen_kpi_minimo():
    """Resumen mínimo de KPI para el reporte (sin BD)."""
    return {
        "kpis_funcionales": [
            {"codigo": "KPI-01", "nombre": "Pedidos correctos",
             "clasificacion": "RF-01", "meta": "\u226595%",
             "valor": 96.0, "numerador": 96, "denominador": 100,
             "formula": "x/y * 100",
             "evidencia_requerida": "pedidos con historial",
             "estado": "cumple",
             "fuente": "comercio.pedidos"},
        ],
        "resumen": {
            "total": 1, "instrumentados": 1, "con_evidencia": 1,
            "pendientes_de_datos": 0, "cumplen": 1, "no_cumplen": 0,
        },
        "graficos": {"flujo_caja": [], "kpi09": None,
                     "satisfaccion": None},
        "operativo": {
            "pedidos_iniciados": 0, "pedidos_completados": 0,
            "entregas": 0, "productos_con_stock_bajo": 0,
            "ingresos": 0.0, "egresos": 0.0, "flujo_neto": 0.0,
            "encuestas_completadas": 0, "satisfaccion_promedio": None,
        },
    }


def _parches_para_cada_reporte():
    """Devuelve (tipo, lista de parches) para los 7 reportes sin BD."""
    from datetime import datetime

    def _ventas(desde=None, hasta=None):
        return [
            {"numero_pedido": "P-100", "origen": "WEB", "estado": "COMPLETADO",
             "total": 126.0, "moneda": "PEN",
             "creado_en": datetime(2026, 1, 10, 9, 0)},
        ]

    def _existencias():
        return [
            {"almacen_codigo": "A1", "sku": "S-1",
             "nombre_comercial": "Kombucha", "sabor": "Jengibre",
             "presentacion": "500ml", "stock_fisico": 20,
             "stock_reservado": 2, "stock_disponible": 18,
             "stock_minimo": 5, "bajo_minimo": False},
        ]

    def _entregas(desde=None, hasta=None):
        return [
            {"numero_pedido": "P-100", "tipo_entrega": "DELIVERY_LOCAL",
             "estado": "ENTREGADO",
             "fecha_programada": datetime(2026, 1, 10, 9, 0),
             "completado_en": datetime(2026, 1, 10, 12, 0),
             "repartidor_detalle": "Juan P\u00e9rez",
             "moneda": "PEN", "costo_cobrado_cliente": 8.0},
        ]

    def _movimientos(desde=None, hasta=None):
        return [
            {"fecha_movimiento": "2026-01-10", "tipo": "INGRESO",
             "origen": "ENTREGA", "categoria_nombre": "Ventas",
             "concepto": "Pago pedido P-100", "monto": 126.0,
             "moneda": "PEN", "metodo_nombre": "EFECTIVO",
             "estado": "ACTIVO"},
        ]

    def _resumen_caja(desde=None, hasta=None, **kwargs):
        return {"ingresos": 126.0, "egresos": 0.0, "flujo_neto": 126.0,
                "total_movimientos": 1}

    def _encuestas(estado=None, desde=None, hasta=None):
        return [
            {"numero_pedido": "P-100", "estado": "RESPONDIDA",
             "canal": "EMAIL", "calificacion_general": 5,
             "recomendaria": "SI",
             "creado_en": datetime(2026, 1, 10, 9, 0)},
        ]

    casos = [
        ("KPI", [
            patch("app.admin.reportes.services._datos_kpi",
                  return_value={
                      "titulo": "Resumen de indicadores KPI",
                      "columnas": ["C\u00f3digo", "Indicador", "Meta",
                                   "Valor", "Estado"],
                      "filas": [["KPI-01", "Pedidos correctos",
                                 "\u226595%", "96.00 %", "Cumple"]],
                      "anexo": None,
                  }),
        ]),
        ("VENTAS", [
            patch("app.admin.reportes.services.obtener_datos_ventas",
                  side_effect=_ventas),
        ]),
        ("PEDIDOS", [
            patch("app.admin.reportes.services.obtener_datos_ventas",
                  side_effect=_ventas),
        ]),
        ("INVENTARIO", [
            patch("app.admin.inventario.repositories."
                  "listar_existencias_detalladas",
                  side_effect=_existencias),
        ]),
        ("ENTREGAS", [
            patch("app.admin.reportes.services.listar_entregas_reporte",
                  side_effect=_entregas),
        ]),
        ("CAJA", [
            patch("app.admin.caja.repositories.listar_movimientos",
                  side_effect=_movimientos),
            patch("app.admin.caja.repositories.resumen_movimientos",
                  side_effect=_resumen_caja),
        ]),
        ("ENCUESTAS", [
            patch("app.encuestas.repositories.listar_encuestas",
                  side_effect=_encuestas),
        ]),
    ]
    return casos


class SieteReportesValidacionTest(unittest.TestCase):
    """Ajuste final: los 7 tipos generan PDF/XLSX/CSV válidos (Unicode)."""

    def setUp(self):
        self.auditor = patch(
            "app.admin.reportes.repositories.registrar_solicitud_reporte",
            return_value=True,
        )

    def _generar_parcheado(self, tipo, formato, parches):
        from app.admin.reportes.services import generar_reporte
        with ExitStack() as pila:
            pila.enter_context(self.auditor)
            for parche in parches:
                pila.enter_context(parche)
            return generar_reporte(
                tipo, formato, "actor-prueba",
                {"desde": "2026-01-01", "hasta": "2026-01-31"},
            )

    def test_siete_tipos_pdf_validos_y_unicode(self):
        for tipo, parches in _parches_para_cada_reporte():
            with self.subTest(tipo=tipo):
                resultado = self._generar_parcheado(tipo, "PDF", parches)
            self.assertTrue(resultado["ok"], tipo)
            self.assertEqual(resultado["mimetype"], "application/pdf")
            self.assertIn(b"%PDF", resultado["contenido"], tipo)
            self.assertIn(b"%%EOF", resultado["contenido"], tipo)

    def test_siete_tipos_xlsx_openpyxl(self):
        from openpyxl import load_workbook
        for tipo, parches in _parches_para_cada_reporte():
            with self.subTest(tipo=tipo):
                resultado = self._generar_parcheado(tipo, "XLSX", parches)
            self.assertTrue(resultado["ok"], tipo)
            self.assertIn("spreadsheetml", resultado["mimetype"], tipo)
            libro = load_workbook(
                io.BytesIO(resultado["contenido"]))
            self.assertIsNotNone(libro.active, tipo)

    def test_siete_tipos_csv_utf8(self):
        for tipo, parches in _parches_para_cada_reporte():
            with self.subTest(tipo=tipo):
                resultado = self._generar_parcheado(tipo, "CSV", parches)
            self.assertTrue(resultado["ok"], tipo)
            self.assertEqual(resultado["mimetype"], "text/csv")
            texto = resultado["contenido"].decode("utf-8-sig")
            self.assertNotIn("\ufffd", texto, tipo)  # sin reemplazos Unicode


class BaseVisualPdfTest(unittest.TestCase):
    """Parte B del ajuste final: base visual común del PDF.

    Verifica encabezado/pie institucionales, wrapping real (texto largo
    de KPI sin excepciones ni cortes) y que la resolución de fuentes no
    dependa de rutas absolutas de Windows.
    """

    def test_pdf_kpi_con_texto_largo_no_falla(self):
        from app.admin.reportes.services import _pdf_generar
        contenido = _pdf_generar(
            "Resumen de indicadores KPI",
            ["Código", "Indicador", "Meta", "Valor", "Estado"],
            [[
                "KPI-05",
                "Disponibilidad de historial clínico y de consultas "
                "de gestión para el área operativa completa",
                "1/2", "50.00 %", "No cumple",
            ], [
                "KPI-08",
                "Estados de pedido actualizados con evidencia suficiente "
                "de la programación de entregas en el período",
                "≥95%", "Sin evidencia", "Pendiente",
            ]],
            {"etiqueta": "KPI con evidencia", "valor": 9},
            rango="Período: 01/01/2026 → 31/01/2026",
            tipo="KPI",
        )
        self.assertIn(b"%PDF", contenido)
        self.assertIn(b"%%EOF", contenido)

    def test_encabezado_pie_institucional_presentes(self):
        from app.admin.reportes.pdf import PdfReporteUnicode
        pdf = PdfReporteUnicode()
        pdf.encabezado_institucional("Inventario actual")
        pdf.tabla(["Almacén", "SKU", "Nivel"],
                  [["A1", "S-1", "Correcto"]])
        pdf.anexo("Variantes totales", 42, "Con stock bajo el mínimo: 2")
        datos = bytes(pdf.output())
        self.assertIn(b"%PDF", datos)
        self.assertIn(b"%%EOF", datos)
        # La familia corporativa DejaVu Sans queda embebida (con sufijo
        # de subconjunto MPDFAA+) y NO se usa la fuente core latin-1.
        self.assertIn(b"MPDFAA+DejaVuSans", datos)
        self.assertNotIn(b"/BaseFont /Helvetica", datos)

    def test_fuentes_y_logo_son_rutas_relativas(self):
        from pathlib import Path

        from app.admin.reportes import pdf as pdf_modulo
        # Se resuelven de forma relativa al paquete (clonable), no con
        # una ruta absoluta de Windows escrita a mano.
        esperado_fuentes = (
            Path(pdf_modulo.__file__).resolve().parent / "fonts"
        )
        self.assertEqual(pdf_modulo.RUTA_FUENTES, esperado_fuentes)
        self.assertTrue(pdf_modulo.RUTA_LOGO.is_file())
        for archivo in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
                        "DejaVuSans-Oblique.ttf",
                        "DejaVuSans-BoldOblique.ttf"):
            with self.subTest(fuente=archivo):
                self.assertTrue(
                    (pdf_modulo.RUTA_FUENTES / archivo).is_file()
                )

    def test_kpi_tabla_anchos_no_desbordan(self):
        from app.admin.reportes.services import _PDF_ANCHOS
        for tipo, anchos in _PDF_ANCHOS.items():
            with self.subTest(tipo=tipo):
                self.assertGreaterEqual(len(anchos), 5, tipo)
                # La tabla se escala al ancho útil; solo debe ser finita.
                self.assertTrue(all(a > 0 for a in anchos), tipo)


class AuditoriaKPI05Test(unittest.TestCase):
    """KPI-05: solo el POST audita, una sola vez, EXITO o FALLO."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def _cliente(self):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({
                "autenticado": True,
                "usuario_id": "actor",
                "correo": "gerente@example.test",
                "roles": ["GERENTE"],
            })
        return cliente

    def test_panel_get_no_genera_evidencia(self):
        with patch(
            "app.admin.reportes.services.generar_reporte",
        ) as generar, patch(
            "app.admin.reportes.repositories.registrar_solicitud_reporte",
        ) as registrar:
            respuesta = self._cliente().get("/admin/reportes/")
        self.assertEqual(respuesta.status_code, 200)
        generar.assert_not_called()
        registrar.assert_not_called()

    def test_post_exitoso_audita_una_sola_vez(self):
        from app.admin.reportes.services import _GENERADORES
        with patch(
            "app.admin.reportes.services._datos_kpi",
            return_value={
                "titulo": "Resumen de indicadores KPI",
                "columnas": ["C\u00f3digo", "Indicador", "Meta",
                             "Valor", "Estado"],
                "filas": [["KPI-01", "Pedidos correctos", "\u226595%",
                           "96.00 %", "Cumple"]],
                "anexo": None,
            },
        ), patch(
            "app.admin.reportes.repositories.registrar_solicitud_reporte",
        ) as registrar:
            respuesta = self._cliente().post(
                "/admin/reportes/generar",
                data={"tipo": "KPI", "formato": "CSV"},
            )
        self.assertEqual(respuesta.status_code, 200)
        registrar.assert_called_once()
        self.assertEqual(registrar.call_args.kwargs["resultado"], "EXITO")
        self.assertEqual(registrar.call_args.kwargs["tipo_reporte"], "KPI")

    def test_fallo_audita_fallo_y_no_duplica(self):
        with patch(
            "app.admin.reportes.services._datos_kpi",
            side_effect=RuntimeError("falla técnica"),
        ), patch(
            "app.admin.reportes.repositories.registrar_solicitud_reporte",
        ) as registrar:
            respuesta = self._cliente().post(
                "/admin/reportes/generar",
                data={"tipo": "KPI", "formato": "PDF"},
            )
        self.assertEqual(respuesta.status_code, 302)
        registrar.assert_called_once()
        self.assertEqual(registrar.call_args.kwargs["resultado"], "FALLO")
        llamada = registrar.call_args.kwargs
        self.assertIn("falla técnica", llamada.get("error_tecnico") or "")


if __name__ == "__main__":
    unittest.main()