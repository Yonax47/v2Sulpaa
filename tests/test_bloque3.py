"""Pruebas del Bloque 3: inventario, contenido (Aprende), favoritos y KPIs.

Estrategia (patrón de la casa):
- Los permisos HTTP se validan con roles reales (servidor TESTING).
- Las reglas de negocio se prueban parcheando los repositorios para
  no tocar MySQL.
- Los KPI del dashboard ejercitan las métricas reales SOLO de lectura.
"""

import unittest
from unittest.mock import patch

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
# PERMISOS HTTP — ADMIN INVENTARIO
# ============================================================

class PermisosHTTPAdminInventarioTest(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_listado_permite_roles_inventario(self):
        for rol in ("GERENTE", "ADMINISTRADOR", "INVENTARIO"):
            with self.subTest(rol=rol), patch(
                "app.admin.inventario.routes.listar_existencias",
                return_value=[],
            ):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/inventario/"
                    ).status_code,
                    200,
                )

    def test_listado_rechaza_roles_sin_acceso(self):
        for rol in ("REPARTIDOR", "PEDIDOS_LOGISTICA", None):
            with self.subTest(rol=rol):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/inventario/"
                    ).status_code,
                    403,
                )

    def test_detalle_inexistente_responde_404(self):
        with patch("app.admin.inventario.routes.obtener_detalle_existencia",
                   return_value=None):
            respuesta = cliente_con_sesion(
                self.app, ["GERENTE"]
            ).get("/admin/inventario/existencia-no-existe")
            self.assertEqual(respuesta.status_code, 404)

    def test_sin_sesion_redirige_login(self):
        respuesta = self.app.test_client().get("/admin/inventario/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])


# ============================================================
# PERMISOS HTTP — ADMIN CONTENIDO
# ============================================================

class PermisosHTTPAdminContenidoTest(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_listado_permite_roles_contentino(self):
        with patch("app.admin.contenido.routes.listar_para_admin",
                   return_value=[]):
            for rol in ("GERENTE", "ADMINISTRADOR"):
                with self.subTest(rol=rol):
                    self.assertEqual(
                        cliente_con_sesion(self.app, [rol]).get(
                            "/admin/contenido/"
                        ).status_code,
                        200,
                    )

    def test_listado_rechaza_roles_sin_acceso(self):
        for rol in ("INVENTARIO", "REPARTIDOR", None):
            with self.subTest(rol=rol):
                self.assertEqual(
                    cliente_con_sesion(self.app, [rol]).get(
                        "/admin/contenido/"
                    ).status_code,
                    403,
                )

    def test_nuevo_formulario_permite_admin(self):
        self.assertEqual(
            cliente_con_sesion(self.app, ["GERENTE"]).get(
                "/admin/contenido/nuevo"
            ).status_code,
            200,
        )

    def test_nuevo_rechazado_sin_permiso(self):
        self.assertEqual(
            cliente_con_sesion(self.app, ["INVENTARIO"]).get(
                "/admin/contenido/nuevo"
            ).status_code,
            403,
        )

    def test_detalle_inexistente_responde_404(self):
        with patch("app.admin.contenido.routes.obtener_para_admin",
                   return_value=None):
            self.assertEqual(
                cliente_con_sesion(self.app, ["GERENTE"]).get(
                    "/admin/contenido/no-existe"
                ).status_code,
                404,
            )


# ============================================================
# RUTAS PÚBLICAS — APRENDE
# ============================================================

class RutasAprendeTest(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def test_portada_accesible_sin_sesion(self):
        with patch("app.aprende.routes.listar_publico", return_value=[]):
            self.assertEqual(
                self.app.test_client().get("/aprende").status_code,
                200,
            )

    def test_slug_inexistente_responde_404(self):
        with patch("app.aprende.routes.obtener_detalle_publico",
                   return_value=None):
            self.assertEqual(
                self.app.test_client().get(
                    "/aprende/contenido-eliminado"
                ).status_code,
                404,
            )


# ============================================================
# RUTAS CLIENTE — FAVORITOS Y FICHA DE PRODUCTO
# ============================================================

class RutasClienteFavoritosProductoTest(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_favoritos_requiere_sesion(self):
        respuesta = self.app.test_client().get("/favoritos")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])

    def test_favoritos_lista_vacia_sin_registros(self):
        with patch("app.comercio.routes.listar_favoritos_del_usuario",
                   return_value=[]):
            self.assertEqual(
                cliente_con_sesion(self.app, ["CLIENTE"]).get(
                    "/favoritos"
                ).status_code,
                200,
            )

    def test_ficha_producto_inexistente_404(self):
        with patch("app.comercio.routes.obtener_ficha_producto",
                   return_value=None):
            self.assertEqual(
                cliente_con_sesion(self.app, ["CLIENTE"]).get(
                    "/producto/SKU-FALSO"
                ).status_code,
                404,
            )

    def test_api_agregar_favorito_valida_entrada(self):
        cliente = cliente_con_sesion(self.app, ["CLIENTE"])
        respuesta = cliente.post(
            "/api/favoritos/agregar",
            json={},
        )
        self.assertEqual(respuesta.status_code, 400)


# ============================================================
# REGLAS DE NEGOCIO — CONTENIDO EDUCATIVO
# ============================================================

class ServicioContenidoTest(unittest.TestCase):
    """Las reglas del Service de contenido se validan sin tocar MySQL."""

    def test_crear_publicado_sin_cuerpo_rechazado(self):
        from app.admin.contenido.services import (
            ErrorContenido,
            crear_para_admin,
        )
        with self.assertRaises(ErrorContenido):
            crear_para_admin(
                actor_id="a1",
                roles=["GERENTE"],
                titulo="Un título",
                tipo="QUE_ES",
                estado="PUBLICADO",
                contenido="   ",
            )

    def test_crear_sin_permiso_rechazado(self):
        from app.admin.contenido.services import (
            ErrorContenido,
            crear_para_admin,
        )
        with self.assertRaises(ErrorContenido):
            crear_para_admin(
                actor_id="a1",
                roles=["INVENTARIO"],
                titulo="Un título",
                tipo="QUE_ES",
                estado="BORRADOR",
            )

    def test_titulo_vacio_rechazado(self):
        from app.admin.contenido.services import (
            ErrorContenido,
            crear_para_admin,
        )
        with self.assertRaises(ErrorContenido):
            crear_para_admin(
                actor_id="a1",
                roles=["GERENTE"],
                titulo="   ",
                tipo="QUE_ES",
                estado="BORRADOR",
            )

    def test_estado_invalido_rechazado(self):
        from app.admin.contenido.services import (
            ErrorContenido,
            crear_para_admin,
        )
        with self.assertRaises(ErrorContenido):
            crear_para_admin(
                actor_id="a1",
                roles=["GERENTE"],
                titulo="Título válido",
                tipo="QUE_ES",
                estado="LIVE",
            )

    def test_etiqueta_tipo_legible(self):
        from app.admin.contenido.services import etiqueta_tipo
        self.assertEqual(
            etiqueta_tipo("QUE_ES"), "¿Qué es la kombucha?"
        )
        self.assertEqual(
            etiqueta_tipo("NO_EXISTE"), "NO_EXISTE"
        )
        self.assertIsInstance(etiqueta_tipo(None), str)


# ============================================================
# REGLAS DE NEGOCIO — FAVORITOS
# ============================================================

class ServicioFavoritosTest(unittest.TestCase):

    def test_agregar_favorito_valida_usuario(self):
        from app.comercio.services import agregar_variante_a_favoritos
        resultado = agregar_variante_a_favoritos(None, "v1")
        self.assertFalse(resultado["ok"])
        self.assertIn("iniciar sesión", resultado["mensaje"])

    def test_agregar_favorito_variante_inexistente_deja_fallo(self):
        from app.comercio.services import agregar_variante_a_favoritos
        with patch(
            "app.comercio.services.obtener_variante_por_id",
            return_value=None,
        ), patch(
            "app.comercio.services.registrar_auditoria_favorito",
        ) as auditoria:
            resultado = agregar_variante_a_favoritos("usuario-1", "v-zzz")
            self.assertFalse(resultado["ok"])
            auditoria.assert_called_once()
            operacion, resultado_aud = auditoria.call_args[0][2], \
                auditoria.call_args[0][3]
            self.assertEqual(operacion, "AGREGAR")
            self.assertEqual(resultado_aud, "FALLO")

    def test_agregar_favorito_exitoso_registra_exito(self):
        from app.comercio.services import agregar_variante_a_favoritos
        with patch(
            "app.comercio.services.obtener_variante_por_id",
            return_value={"variante_id": "v-real"},
        ), patch(
            "app.comercio.services.agregar_favorito",
            return_value=True,
        ), patch(
            "app.comercio.services.registrar_auditoria_favorito",
        ) as auditoria, patch(
            "app.comercio.services.listar_favoritos_del_usuario",
            return_value=[],
        ):
            resultado = agregar_variante_a_favoritos("usuario-1", "v-real")
            self.assertTrue(resultado["ok"])
            auditoria.assert_called_once()
            self.assertEqual(auditoria.call_args[0][2], "AGREGAR")
            self.assertEqual(auditoria.call_args[0][3], "EXITO")

    def test_quitar_favorito_inexistente_deja_fallo(self):
        from app.comercio.services import quitar_variante_de_favoritos
        with patch(
            "app.comercio.services.obtener_variante_por_id",
            return_value=None,
        ), patch(
            "app.comercio.services.quitar_favorito",
            return_value=False,
        ), patch(
            "app.comercio.services.registrar_auditoria_favorito",
        ) as auditoria:
            resultado = quitar_variante_de_favoritos("usuario-1", "v-zzz")
            self.assertFalse(resultado["ok"])
            auditoria.assert_called_once()
            self.assertEqual(auditoria.call_args[0][2], "QUITAR")
            self.assertEqual(auditoria.call_args[0][3], "FALLO")


# ============================================================
# KPI — DASHBOARD (02/03/06/10)
# ============================================================

class KPIDashboardBloque3Test(unittest.TestCase):

    def test_dashboard_incluye_catalogo_funcional_completo(self):
        resumen = {}
        with patch(
            "app.admin.services.obtener_metrica_verificaciones_fisicas",
            return_value={"disponible": True,
                          "total_verificaciones": 0, "verificaciones_ok": 0},
        ), patch(
            "app.admin.services.obtener_metrica_consultas_producto",
            return_value={"disponible": True,
                          "total_consultas": 0, "consultas_exitosas": 0},
        ), patch(
            "app.admin.services.obtener_metrica_favoritos",
            return_value={"disponible": True,
                          "total_favoritos_ops": 0, "favoritos_exitosos": 0},
        ), patch(
            "app.admin.services.obtener_metrica_accesos_contenido",
            return_value={"disponible": True,
                          "total_accesos": 0, "accesos_exitosos": 0},
        ), patch(
            "app.admin.services.obtener_metrica_pedidos_procesados",
            return_value={"pedidos_iniciados": 0, "pedidos_completados": 0},
        ), patch(
            "app.admin.services.obtener_metrica_historial_pedidos",
            return_value={"total_pedidos": 0, "pedidos_con_historial": 0},
        ), patch(
            "app.admin.services.obtener_metrica_consistencia_estados",
            return_value={"total_pedidos_historial": 0,
                          "estados_consistentes": 0},
        ), patch(
            "app.admin.services.obtener_metrica_programacion_entregas",
            return_value={"total_entregas": 0, "entregas_programadas": 0},
        ), patch(
            "app.admin.services.obtener_metrica_satisfaccion",
            return_value={"disponible": False},
        ):
            from app.admin.services import resumen_dashboard
            resumen = resumen_dashboard()

        codigos = {kpi["codigo"] for kpi in resumen["kpis_funcionales"]}
        self.assertIn("KPI-02", codigos)
        self.assertIn("KPI-03", codigos)
        self.assertIn("KPI-06", codigos)
        self.assertIn("KPI-10", codigos)

        por_codigo = {
            kpi["codigo"]: kpi for kpi in resumen["kpis_funcionales"]
        }
        self.assertIsNone(por_codigo["KPI-02"]["valor"])
        self.assertIsNone(por_codigo["KPI-03"]["valor"])
        self.assertIsNone(por_codigo["KPI-06"]["valor"])
        self.assertIsNone(por_codigo["KPI-10"]["valor"])
        self.assertEqual(por_codigo["KPI-02"]["estado"], "pendiente")

    def test_kpi_valores_se_calculan_con_metas_reales(self):
        with patch(
            "app.admin.services.obtener_metrica_verificaciones_fisicas",
            return_value={"disponible": True,
                          "total_verificaciones": 100,
                          "verificaciones_ok": 99},
        ), patch(
            "app.admin.services.obtener_metrica_consultas_producto",
            return_value={"disponible": True,
                          "total_consultas": 100,
                          "consultas_exitosas": 96},
        ), patch(
            "app.admin.services.obtener_metrica_favoritos",
            return_value={"disponible": True,
                          "total_favoritos_ops": 100,
                          "favoritos_exitosos": 96},
        ), patch(
            "app.admin.services.obtener_metrica_accesos_contenido",
            return_value={"disponible": True,
                          "total_accesos": 100,
                          "accesos_exitosos": 96},
        ), patch(
            "app.admin.services.obtener_metrica_pedidos_procesados",
            return_value={"pedidos_iniciados": 100, "pedidos_completados": 96},
        ), patch(
            "app.admin.services.obtener_metrica_historial_pedidos",
            return_value={"total_pedidos": 100, "pedidos_con_historial": 98},
        ), patch(
            "app.admin.services.obtener_metrica_consistencia_estados",
            return_value={"total_pedidos_historial": 100,
                          "estados_consistentes": 98},
        ), patch(
            "app.admin.services.obtener_metrica_programacion_entregas",
            return_value={"total_entregas": 100, "entregas_programadas": 96},
        ), patch(
            "app.admin.services.obtener_metrica_satisfaccion",
            return_value={"disponible": False},
        ):
            from app.admin.services import resumen_dashboard
            resumen = resumen_dashboard()

        por_codigo = {
            kpi["codigo"]: kpi for kpi in resumen["kpis_funcionales"]
        }
        self.assertEqual(por_codigo["KPI-02"]["valor"], 99.0)
        self.assertEqual(por_codigo["KPI-03"]["valor"], 96.0)
        self.assertEqual(por_codigo["KPI-06"]["valor"], 96.0)
        self.assertEqual(por_codigo["KPI-10"]["valor"], 96.0)
        # KPI-02 meta ≥98% -> cumple; KPI-03/06/10 meta ≥95% -> cumple.
        self.assertEqual(por_codigo["KPI-02"]["estado"], "cumple")
        self.assertEqual(por_codigo["KPI-03"]["estado"], "cumple")
        self.assertEqual(por_codigo["KPI-06"]["estado"], "cumple")
        self.assertEqual(por_codigo["KPI-10"]["estado"], "cumple")


if __name__ == "__main__":
    unittest.main()