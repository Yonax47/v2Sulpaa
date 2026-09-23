"""Pruebas del Bloque 3: inventario, contenido (Aprende), favoritos y KPIs.

Estrategia (patrón de la casa):
- Los permisos HTTP se validan con roles reales (servidor TESTING).
- Las reglas de negocio se prueban parcheando los repositorios para
  no tocar MySQL.
- Los KPI del dashboard ejercitan las métricas reales SOLO de lectura.
"""

import unittest
from datetime import datetime
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

    def test_ficha_producto_existente_muestra_estado_favorito(self):
        ficha = {
            "variante_id": "v-cafe",
            "sku": "KOM-01-01",
            "nombre_comercial": "Kombucha SULPAA - Café - Botella 330 ml",
            "sabor": "Café",
            "presentacion": "Botella 330 ml",
            "precio": None,
            "moneda": "PEN",
            "peso_gramos": 380,
            "articulo_venta_id": None,
            "stock_disponible": 10,
            "disponible": True,
            "presentaciones": [],
            "es_favorito": True,
        }
        with patch(
            "app.comercio.routes.obtener_ficha_producto",
            return_value=ficha,
        ):
            respuesta = cliente_con_sesion(
                self.app, ["CLIENTE"]
            ).get("/producto/KOM-01-01")

        cuerpo = respuesta.get_data(as_text=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("KOM-01-01", cuerpo)
        self.assertIn("data-active=\"true\"", cuerpo)
        self.assertIn("♥", cuerpo)

    def test_tienda_muestra_detalle_real_y_favorito(self):
        datos = {
            "catalogo": [],
            "variantes_330": [{
                "variante_id": "v-cafe",
                "sku": "KOM-01-01",
                "nombre_comercial": "Kombucha Café 330 ml",
                "sabor": "Café",
                "presentacion": "Botella 330 ml",
                "stock_disponible": 10,
                "disponible": True,
            }],
            "packs": [],
            "packs_personalizados": [],
        }
        carrito = {
            "items": [],
            "cantidad_items": 0,
            "subtotal": 0.0,
        }
        favoritos = [{"variante_id": "v-cafe"}]

        with patch(
            "app.comercio.routes.obtener_datos_tienda",
            return_value=datos,
        ), patch(
            "app.comercio.routes.obtener_carrito_usuario",
            return_value=carrito,
        ), patch(
            "app.comercio.routes.listar_favoritos_del_usuario",
            return_value=favoritos,
        ):
            respuesta = cliente_con_sesion(
                self.app, ["CLIENTE"]
            ).get("/tienda")

        cuerpo = respuesta.get_data(as_text=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("/producto/KOM-01-01", cuerpo)
        self.assertIn("Ver detalles", cuerpo)
        self.assertIn("data-variante-id=\"v-cafe\"", cuerpo)
        self.assertIn("data-active=\"true\"", cuerpo)

    def test_api_agregar_favorito_valida_entrada(self):
        cliente = cliente_con_sesion(self.app, ["CLIENTE"])
        respuesta = cliente.post(
            "/api/favoritos/agregar",
            json={},
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_apis_favoritos_requieren_autenticacion(self):
        cliente = self.app.test_client()
        for ruta in (
            "/api/favoritos/agregar",
            "/api/favoritos/quitar",
        ):
            with self.subTest(ruta=ruta):
                respuesta = cliente.post(
                    ruta,
                    json={"variante_id": "v-cafe"},
                )
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(
                    "/identidad/login",
                    respuesta.headers["Location"],
                )


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


class FragmentoPublicadoContenidoTest(unittest.TestCase):
    """
    Regresión del bug al editar contenido ya publicado.

    Cuando un contenido ya tenía fecha de publicación (objeto datetime
    que devuelve DictCursor), la regresión anterior interpolaba ese
    valor directamente en el SQL generando sintaxis inválida. Este test
    garantiza que el sello viaje como parámetro seguro.
    """

    def _fragmento(self, estado, publicado_en_actual):
        from app.admin.contenido.repositories import (
            _fragmento_publicado_en,
        )
        return _fragmento_publicado_en(
            estado,
            publicado_en_actual,
        )

    def test_primera_publicacion_usa_now(self):
        fragmento = self._fragmento("PUBLICADO", None)
        self.assertEqual(fragmento["fragmento"], "NOW()")

    def test_ya_publicado_conserva_sello_como_parametro(self):
        publicado = datetime(2026, 9, 20, 15, 30, 0)
        fragmento = self._fragmento("PUBLICADO", publicado)
        self.assertEqual(fragmento["fragmento"], "%s")

    def test_borrador_sin_publicar_limpia_null(self):
        fragmento = self._fragmento("BORRADOR", None)
        self.assertEqual(fragmento["fragmento"], "%s")

    def test_borrador_ya_publicado_conserva_sello(self):
        publicado = datetime(2026, 9, 20, 15, 30, 0)
        fragmento = self._fragmento("BORRADOR", publicado)
        self.assertEqual(fragmento["fragmento"], "%s")

    def _ejecutar_actualizacion(self, publicado_en, titulo):
        from app.admin.contenido.repositories import actualizar_contenido

        conexion = MagicMock()
        cursor = MagicMock()
        conexion.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {
            "id": "contenido-1",
            "estado": "PUBLICADO",
            "publicado_en": publicado_en,
        }

        with patch(
            "app.admin.contenido.repositories._esquema",
            return_value="comercio_prueba",
        ), patch(
            "app.admin.contenido.repositories.conexion_comercio",
            return_value=conexion,
        ):
            resultado = actualizar_contenido(
                contenido_id="contenido-1",
                titulo=titulo,
                slug="que-es-la-kombucha",
                resumen="Resumen",
                contenido="Contenido educativo",
                tipo="QUE_ES",
                imagen_ruta="img/QueesKombucha.jpg",
                estado="PUBLICADO",
                orden=1,
            )

        consulta_update, parametros = cursor.execute.call_args_list[1].args
        return resultado, consulta_update, parametros, conexion

    def test_update_modificado_parametriza_datetime_y_confirma(self):
        publicado = datetime(2026, 9, 20, 15, 30, 0)
        resultado, consulta, parametros, conexion = (
            self._ejecutar_actualizacion(publicado, "Título modificado")
        )

        self.assertTrue(resultado["ok"])
        self.assertIn("publicado_en = %s", consulta)
        self.assertNotIn(str(publicado), consulta)
        self.assertEqual(parametros[-2], publicado)
        conexion.commit.assert_called_once_with()
        conexion.rollback.assert_not_called()

    def test_update_sin_cambios_tambien_es_exitoso(self):
        publicado = datetime(2026, 9, 20, 15, 30, 0)
        resultado, consulta, parametros, conexion = (
            self._ejecutar_actualizacion(publicado, "¿Qué es la kombucha?")
        )

        self.assertTrue(resultado["ok"])
        self.assertIn("publicado_en = %s", consulta)
        self.assertEqual(parametros[-2], publicado)
        conexion.commit.assert_called_once_with()

    def test_primera_publicacion_update_conserva_now(self):
        resultado, consulta, parametros, conexion = (
            self._ejecutar_actualizacion(None, "Contenido publicado")
        )

        self.assertTrue(resultado["ok"])
        self.assertIn("publicado_en = NOW()", consulta)
        self.assertEqual(parametros[-1], "contenido-1")
        self.assertEqual(len(parametros), 9)
        conexion.commit.assert_called_once_with()


class VisibilidadContenidoPublicadoTest(unittest.TestCase):
    """El repositorio público excluye borradores sin generar accesos KPI-10."""

    def test_listado_publico_filtra_publicado_con_fecha(self):
        from app.aprende.repositories import listar_contenido_publicado

        conexion = MagicMock()
        cursor = MagicMock()
        conexion.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.return_value = []

        with patch(
            "app.aprende.repositories._esquema",
            return_value="comercio_prueba",
        ), patch(
            "app.aprende.repositories.conexion_comercio",
            return_value=conexion,
        ):
            listar_contenido_publicado()

        consulta = cursor.execute.call_args.args[0]
        self.assertIn("ce.estado = 'PUBLICADO'", consulta)
        self.assertIn("ce.publicado_en IS NOT NULL", consulta)
        self.assertNotIn("accesos_contenido", consulta)

    def test_detalle_publico_no_admite_borrador(self):
        from app.aprende.repositories import obtener_contenido_publicado

        conexion = MagicMock()
        cursor = MagicMock()
        conexion.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = None

        with patch(
            "app.aprende.repositories._esquema",
            return_value="comercio_prueba",
        ), patch(
            "app.aprende.repositories.conexion_comercio",
            return_value=conexion,
        ):
            resultado = obtener_contenido_publicado("borrador")

        consulta = cursor.execute.call_args.args[0]
        self.assertIsNone(resultado)
        self.assertIn("ce.estado = 'PUBLICADO'", consulta)
        self.assertIn("ce.publicado_en IS NOT NULL", consulta)


# ============================================================
# REGLAS DE NEGOCIO — DETALLE DE PRODUCTO (KPI-03)
# ============================================================

class ServicioFichaProductoTest(unittest.TestCase):
    """Cada navegación registra una sola evidencia lógica KPI-03."""

    def test_detalle_existente_registra_exito_una_vez(self):
        from app.comercio.services import obtener_ficha_producto

        variante = {
            "variante_id": "v-cafe",
            "sku": "KOM-01-01",
            "nombre_comercial": "Kombucha Café 330 ml",
            "sabor": "Café",
            "presentacion": "Botella 330 ml",
            "precio": None,
            "moneda": None,
            "peso_gramos": 380,
            "articulo_venta_id": None,
        }
        stock = {
            "v-cafe": {
                "stock_fisico": 12,
                "stock_reservado": 2,
                "stock_disponible": 10,
                "disponible": True,
            },
        }

        with patch(
            "app.comercio.services.obtener_variante_por_sku",
            return_value=variante,
        ), patch(
            "app.comercio.services.obtener_disponibilidad_variantes",
            return_value=stock,
        ), patch(
            "app.comercio.services._presentaciones_del_sabor",
            return_value=[],
        ), patch(
            "app.comercio.services.listar_favoritos_usuario",
            return_value=[{"variante_id": "v-cafe"}],
        ), patch(
            "app.comercio.services.registrar_consulta_producto",
        ) as registrar:
            resultado = obtener_ficha_producto(
                "KOM-01-01",
                usuario_id="usuario-1",
            )

        self.assertEqual(resultado["sku"], "KOM-01-01")
        self.assertTrue(resultado["es_favorito"])
        self.assertEqual(resultado["stock_disponible"], 10)
        registrar.assert_called_once_with(
            sku="KOM-01-01",
            variante_id="v-cafe",
            usuario_id="usuario-1",
            resultado="EXITO",
        )

    def test_detalle_inexistente_registra_fallo_una_vez(self):
        from app.comercio.services import obtener_ficha_producto

        with patch(
            "app.comercio.services.obtener_variante_por_sku",
            return_value=None,
        ), patch(
            "app.comercio.services.registrar_consulta_producto",
        ) as registrar:
            resultado = obtener_ficha_producto(
                "SKU-INEXISTENTE",
                usuario_id="usuario-1",
            )

        self.assertIsNone(resultado)
        registrar.assert_called_once_with(
            sku="SKU-INEXISTENTE",
            variante_id=None,
            usuario_id="usuario-1",
            resultado="FALLO",
        )

    def test_presentaciones_provienen_de_catalogos_reales(self):
        from app.comercio.services import _presentaciones_del_sabor

        botella = {
            "variante_id": "v-330",
            "sku": "KOM-01-01",
            "sabor": "Café",
            "presentacion": "Botella 330 ml",
            "stock_disponible": 8,
            "disponible": True,
        }
        litro = {
            "variante_id": "v-1l",
            "sku": "KOM-01-02",
            "sabor": "Café",
            "presentacion": "Botella 1 L",
            "precio": 30,
            "moneda": "PEN",
            "articulo_venta_id": "av-1l",
            "stock_disponible": 4,
            "disponible": True,
        }

        with patch(
            "app.comercio.services.obtener_variantes_330ml_con_stock",
            return_value=[botella],
        ), patch(
            "app.comercio.services.obtener_catalogo_tienda",
            return_value=[litro],
        ):
            resultado = _presentaciones_del_sabor(
                "Café",
                "KOM-01-01",
            )

        self.assertEqual(
            [item["sku"] for item in resultado],
            ["KOM-01-01", "KOM-01-02"],
        )
        self.assertTrue(resultado[0]["es_actual"])
        self.assertEqual(resultado[1]["precio"], 30.0)


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

    def test_agregar_favorito_repetido_es_idempotente(self):
        from app.comercio.services import agregar_variante_a_favoritos

        with patch(
            "app.comercio.services.obtener_variante_por_id",
            return_value={"variante_id": "v-real"},
        ), patch(
            "app.comercio.services.agregar_favorito",
            return_value=True,
        ) as guardar, patch(
            "app.comercio.services.registrar_auditoria_favorito",
        ) as auditoria, patch(
            "app.comercio.services.listar_favoritos_del_usuario",
            return_value=[{"variante_id": "v-real"}],
        ):
            primero = agregar_variante_a_favoritos("usuario-1", "v-real")
            segundo = agregar_variante_a_favoritos("usuario-1", "v-real")

        self.assertTrue(primero["ok"])
        self.assertTrue(segundo["ok"])
        self.assertEqual(guardar.call_count, 2)
        self.assertEqual(auditoria.call_count, 2)
        for llamada in auditoria.call_args_list:
            self.assertEqual(llamada.args[2], "AGREGAR")
            self.assertEqual(llamada.args[3], "EXITO")

    def test_quitar_favorito_exitoso_registra_exito(self):
        from app.comercio.services import quitar_variante_de_favoritos

        with patch(
            "app.comercio.services.obtener_variante_por_id",
            return_value={"variante_id": "v-real"},
        ), patch(
            "app.comercio.services.quitar_favorito",
            return_value=True,
        ), patch(
            "app.comercio.services.registrar_auditoria_favorito",
        ) as auditoria, patch(
            "app.comercio.services.listar_favoritos_del_usuario",
            return_value=[],
        ):
            resultado = quitar_variante_de_favoritos(
                "usuario-1",
                "v-real",
            )

        self.assertTrue(resultado["ok"])
        auditoria.assert_called_once_with(
            "usuario-1",
            "v-real",
            "QUITAR",
            "EXITO",
        )


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
