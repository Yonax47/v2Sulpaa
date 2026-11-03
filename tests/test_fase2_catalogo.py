# -*- coding: utf-8 -*-
"""Pruebas seguras de Fase 2 para el catálogo administrativo.

Estas pruebas no usan MySQL. Las reglas puras se ejecutan directamente y los
servicios reemplazan repositorios, auditoría e inventario por dobles en memoria.
Las pruebas HTTP activan de forma explícita la excepción de seguridad destinada
al entorno TESTING; fuera de pruebas esa excepción no funciona.
"""

import io
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from app import create_app
from app.admin.catalogo import imagenes
from app.admin.catalogo import services
from app.admin.catalogo.validaciones import (
    ErrorCatalogo,
    calcular_stock_pack_fijo,
    generar_slug,
    rangos_se_superponen,
    validar_componentes_pack,
    validar_monto,
    validar_reglas_pack,
)


def cliente_con_sesion(app, roles):
    """Crea un cliente autenticado con roles ficticios solo para TESTING."""

    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion.update({
            "autenticado": True,
            "usuario_id": "actor-prueba",
            "correo": "actor@example.test",
            "roles": roles,
        })
    return cliente


class ValidacionesCatalogoTest(unittest.TestCase):
    """Comprueba reglas puras sin Flask ni base de datos."""

    def test_slug_quita_tildes_y_signos(self):
        self.assertEqual(generar_slug("Kombucha Limón & Kion"), "kombucha-limon-kion")

    def test_precio_debe_ser_mayor_que_cero(self):
        for valor in ("0", "-1"):
            with self.subTest(valor=valor):
                with self.assertRaises(ErrorCatalogo):
                    validar_monto(valor)
        self.assertEqual(validar_monto("12,5"), Decimal("12.50"))

    def test_vigencias_adyacentes_no_se_superponen(self):
        inicio = datetime(2026, 1, 1, 10)
        corte = datetime(2026, 1, 2, 10)
        fin = datetime(2026, 1, 3, 10)
        self.assertFalse(rangos_se_superponen(inicio, corte, corte, fin))
        self.assertTrue(rangos_se_superponen(inicio, fin, corte, None))

    def test_pack_fijo_exige_suma_exacta_y_no_repetidos(self):
        componentes = [
            {"variante_id": "v1", "cantidad": 2},
            {"variante_id": "v2", "cantidad": 4},
        ]
        self.assertEqual(validar_componentes_pack(6, componentes), 6)
        with self.assertRaises(ErrorCatalogo):
            validar_componentes_pack(5, componentes)
        with self.assertRaises(ErrorCatalogo):
            validar_componentes_pack(4, [
                {"variante_id": "v1", "cantidad": 2},
                {"variante_id": "v1", "cantidad": 2},
            ])

    def test_pack_personalizable_exige_reglas_consistentes(self):
        reglas = [{"numero_sabores": 3, "unidades_por_sabor": 4}]
        self.assertEqual(validar_reglas_pack(12, reglas), 12)
        with self.assertRaises(ErrorCatalogo):
            validar_reglas_pack(10, reglas)

    def test_stock_pack_usa_el_componente_limitante(self):
        componentes = [
            {"variante_id": "v1", "cantidad": 2},
            {"variante_id": "v2", "cantidad": 3},
        ]
        disponibilidad = {
            "v1": {"stock_disponible": 10},
            "v2": {"stock_disponible": 7},
        }
        self.assertEqual(
            calcular_stock_pack_fijo(componentes, disponibilidad), 2
        )

    def test_tienda_no_filtra_sql_a_solo_cuatro_sabores(self):
        """Los sabores nuevos activos deben llegar a la tienda real."""

        raiz = Path(__file__).resolve().parents[1]
        repositorio = (raiz / "app/comercio/repositories.py").read_text(
            encoding="utf-8"
        )
        tienda = (raiz / "templates/cliente/tienda.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("AND s.nombre IN", repositorio)
        self.assertNotIn("AND p.nombre IN", repositorio)
        self.assertIn("Cualquier sabor activo nuevo", tienda)


class ImagenesCatalogoTest(unittest.TestCase):
    """Valida firmas, rutas y escritura usando una carpeta temporal simulada."""

    def test_rutas_externas_y_recorridos_se_rechazan(self):
        for ruta in ("https://example.test/foto.jpg", "img/../secreto.jpg"):
            with self.subTest(ruta=ruta):
                with self.assertRaises(ErrorCatalogo):
                    imagenes.normalizar_ruta_imagen(ruta)

    def test_ruta_estatica_y_persistente_se_aceptan(self):
        self.assertEqual(
            imagenes.normalizar_ruta_imagen("img/catalogo/foto.webp"),
            "img/catalogo/foto.webp",
        )
        self.assertEqual(
            imagenes.nombre_archivo_persistente(
                "uploads/catalogo/abc123.png"
            ),
            "abc123.png",
        )

    def test_carga_valida_firma_real_y_genera_nombre_aleatorio(self):
        contenido_png = b"\x89PNG\r\n\x1a\n" + b"datos-seguros"
        archivo = FileStorage(
            stream=io.BytesIO(contenido_png),
            filename="foto.png",
            content_type="image/png",
        )
        with tempfile.TemporaryDirectory() as temporal:
            with patch.object(imagenes, "directorio_imagenes", return_value=Path(temporal)):
                ruta = imagenes.guardar_imagen_segura(archivo)
                self.assertTrue(ruta.startswith("uploads/catalogo/"))
                self.assertTrue(ruta.endswith(".png"))
                self.assertTrue((Path(temporal) / ruta.split("/")[-1]).exists())

    def test_extension_que_no_coincide_con_firma_se_rechaza(self):
        archivo = FileStorage(
            stream=io.BytesIO(b"\xff\xd8\xff" + b"jpeg"),
            filename="falsa.png",
            content_type="image/png",
        )
        with self.assertRaises(ErrorCatalogo):
            imagenes.guardar_imagen_segura(archivo)


class ServiciosCatalogoTest(unittest.TestCase):
    """Prueba permisos, publicación, auditoría y stock mediante dobles."""

    def test_permiso_rechaza_un_rol_no_autorizado(self):
        with self.assertRaises(ErrorCatalogo):
            services.obtener_resumen(["INVENTARIO"])

    @patch("app.admin.catalogo.services.repos.contar_catalogo")
    def test_permiso_acepta_gerente(self, contar):
        contar.return_value = {"productos": 2}
        self.assertEqual(
            services.obtener_resumen(["GERENTE"]), {"productos": 2}
        )

    @patch("app.admin.catalogo.services.repos.obtener_simple")
    @patch("app.admin.catalogo.services.repos.obtener_producto")
    def test_variante_activa_rechaza_producto_inactivo(self, producto, simple):
        producto.return_value = {"estado": "INACTIVO"}
        detalle = {
            "producto_id": "p1",
            "presentacion_id": 1,
            "sabor_id": 1,
            "estado": "ACTIVO",
        }
        with self.assertRaisesRegex(ErrorCatalogo, "producto inactivo"):
            services._validar_relaciones_variante(detalle)
        simple.assert_not_called()

    @patch("app.admin.catalogo.services.repos.obtener_simple")
    @patch("app.admin.catalogo.services.repos.obtener_producto")
    def test_variante_activa_rechaza_presentacion_inactiva(self, producto, simple):
        producto.return_value = {"estado": "ACTIVO"}
        simple.return_value = {"estado": "INACTIVO"}
        detalle = {
            "producto_id": "p1",
            "presentacion_id": 1,
            "sabor_id": None,
            "estado": "ACTIVO",
        }
        with self.assertRaisesRegex(ErrorCatalogo, "presentación inactiva"):
            services._validar_relaciones_variante(detalle)

    @patch("app.admin.catalogo.services._auditar")
    @patch("app.admin.catalogo.services.repos.crear_simple")
    @patch("app.admin.catalogo.services.repos.slug_disponible", return_value=True)
    def test_creacion_audita_despues_de_guardar(self, _slug, crear, auditar):
        crear.return_value = {"ok": True, "id": 7}
        resultado = services.crear_catalogo_simple(
            "actor", ["ADMINISTRADOR"], "categorias",
            {"nombre": "Bebidas", "orden": "1", "estado": "ACTIVO"},
        )
        self.assertEqual(resultado["id"], 7)
        crear.assert_called_once()
        auditar.assert_called_once()

    @patch("app.admin.catalogo.services.obtener_disponibilidad_variantes")
    @patch("app.admin.catalogo.services.repos.obtener_pack")
    def test_stock_pack_es_solo_calculado(self, obtener_pack, disponibilidad):
        obtener_pack.return_value = {
            "tipo": "FIJO",
            "componentes": [
                {"variante_id": "v1", "cantidad": 2},
                {"variante_id": "v2", "cantidad": 3},
            ],
        }
        disponibilidad.return_value = {
            "v1": {"stock_fisico": 10, "stock_reservado": 0,
                   "stock_disponible": 10, "disponible": True},
            "v2": {"stock_fisico": 8, "stock_reservado": 2,
                   "stock_disponible": 6, "disponible": True},
        }
        resultado = services.obtener_stock_pack(["GERENTE"], "pack-1")
        self.assertEqual(resultado["packs_disponibles"], 2)
        disponibilidad.assert_called_once_with(["v1", "v2"])

    @patch("app.admin.catalogo.services.repos.obtener_variante")
    @patch("app.admin.catalogo.services.repos.obtener_producto")
    def test_imagen_exige_un_solo_destino(self, producto, variante):
        producto.return_value = {"producto_id": "p1"}
        variante.return_value = {"variante_id": "v1"}
        with self.assertRaises(ErrorCatalogo):
            services._validar_destino_imagen("p1", "v1")
        with self.assertRaises(ErrorCatalogo):
            services._validar_destino_imagen(None, None)
        self.assertEqual(
            services._validar_destino_imagen("p1", None), ("p1", None)
        )

    @patch("app.admin.catalogo.services.repos.actualizar_pack")
    @patch("app.admin.catalogo.services.repos.pack_tiene_pedidos", return_value=True)
    @patch("app.admin.catalogo.services.repos.obtener_variante")
    @patch("app.admin.catalogo.services.repos.obtener_pack")
    def test_pack_con_pedidos_no_cambia_composicion(
        self, obtener_pack, obtener_variante, _tiene_pedidos, actualizar
    ):
        obtener_pack.return_value = {
            "tipo": "FIJO", "nombre": "Pack", "slug": "pack",
            "estado": "ACTIVO",
            "componentes": [{"variante_id": "v1", "cantidad": 6}],
            "reglas": [], "permitidas": [],
        }
        obtener_variante.return_value = {"estado": "ACTIVO"}
        datos = {
            "nombre": "Pack", "tipo": "FIJO", "cantidad_unidades": 6,
            "peso_embalaje_gramos": 0, "estado": "ACTIVO",
            "componentes": [{"variante_id": "v2", "cantidad": 6}],
            "reglas": [], "permitidas": [],
        }
        with self.assertRaisesRegex(ErrorCatalogo, "pedidos históricos"):
            services.actualizar_pack(
                "actor", ["GERENTE"], "pk1", datos
            )
        actualizar.assert_not_called()


class RutasCatalogoTest(unittest.TestCase):
    """Comprueba registro y permisos HTTP sin consultar repositorios reales."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            OMITIR_SEGURIDAD_EN_PRUEBAS=True,
        )

    def test_blueprint_y_media_estan_registrados(self):
        reglas = {regla.rule for regla in self.app.url_map.iter_rules()}
        self.assertIn("/admin/catalogo/", reglas)
        self.assertIn("/admin/catalogo/variantes/<variante_id>", reglas)
        self.assertIn("/media/catalogo/<filename>", reglas)

    def test_panel_sin_sesion_redirige_al_login(self):
        respuesta = self.app.test_client().get("/admin/catalogo/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("login", respuesta.headers["Location"])

    def test_panel_rechaza_rol_no_autorizado(self):
        cliente = cliente_con_sesion(self.app, ["INVENTARIO"])
        respuesta = cliente.get("/admin/catalogo/")
        self.assertEqual(respuesta.status_code, 403)

    @patch("app.admin.catalogo.routes.listar_precios_por_vencer", return_value=[])
    @patch("app.admin.catalogo.routes.obtener_resumen")
    def test_panel_permite_administrador(self, resumen, _precios):
        resumen.return_value = {
            "productos": 0, "productos_activos": 0,
            "variantes": 0, "variantes_activas": 0,
            "packs": 0, "packs_activos": 0,
            "precios_vigentes": 0, "variantes_sin_precio": 0,
            "categorias": 0, "sabores": 0,
            "presentaciones": 0, "imagenes": 0,
        }
        cliente = cliente_con_sesion(self.app, ["ADMINISTRADOR"])
        respuesta = cliente.get("/admin/catalogo/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b"Cat\xc3\xa1logo comercial", respuesta.data)

    def test_media_sin_volumen_configurado_devuelve_404(self):
        self.app.config.pop("CATALOGO_IMAGENES_DIR", None)
        with patch.dict("os.environ", {}, clear=True):
            respuesta = self.app.test_client().get(
                "/media/catalogo/archivo.png"
            )
        self.assertEqual(respuesta.status_code, 404)

    def test_listados_y_formularios_nuevos_renderizan_con_dobles(self):
        """Renderiza todas las entradas principales sin abrir MySQL."""

        selectores = {
            "categorias": [], "sabores": [], "presentaciones": [],
            "variantes": [], "productos": [], "tipos_precio": [],
            "tipos_unidad": [("ML", "Mililitros")],
            "tipos_pack": ["FIJO", "PERSONALIZABLE"],
        }
        cliente = cliente_con_sesion(self.app, ["GERENTE"])

        with patch("app.admin.catalogo.routes.listar_catalogo_simple", return_value=[]), \
             patch("app.admin.catalogo.routes.listar_productos", return_value=[]), \
             patch("app.admin.catalogo.routes.listar_variantes", return_value=[]), \
             patch("app.admin.catalogo.routes.listar_imagenes", return_value=[]), \
             patch("app.admin.catalogo.routes.listar_packs", return_value=[]), \
             patch("app.admin.catalogo.routes.obtener_selectores", return_value=selectores):
            rutas = (
                "/admin/catalogo/categorias/",
                "/admin/catalogo/sabores/",
                "/admin/catalogo/presentaciones/",
                "/admin/catalogo/productos/",
                "/admin/catalogo/productos/nuevo",
                "/admin/catalogo/variantes/",
                "/admin/catalogo/variantes/nuevo",
                "/admin/catalogo/imagenes/",
                "/admin/catalogo/imagenes/nueva",
                "/admin/catalogo/packs/",
                "/admin/catalogo/packs/nuevo",
            )
            for ruta in rutas:
                with self.subTest(ruta=ruta):
                    respuesta = cliente.get(ruta)
                    self.assertEqual(respuesta.status_code, 200)

    def test_detalles_principales_renderizan_con_dobles(self):
        """Comprueba las plantillas de edición con datos mínimos seguros."""

        selectores = {
            "categorias": [], "sabores": [], "presentaciones": [],
            "variantes": [], "productos": [], "tipos_precio": [],
            "tipos_unidad": [("ML", "Mililitros")],
            "tipos_pack": ["FIJO", "PERSONALIZABLE"],
        }
        producto = {
            "producto_id": "p1", "nombre": "Kombucha", "slug": "kombucha",
            "categoria_id": 1, "descripcion": None, "estado": "ACTIVO",
            "variantes": [], "imagenes": [],
        }
        variante = {
            "variante_id": "v1", "producto_id": "p1", "sabor_id": 1,
            "presentacion_id": 1, "sku": "SKU-1",
            "nombre_comercial": "Kombucha 330", "peso_gramos": None,
            "largo_cm": None, "ancho_cm": None, "alto_cm": None,
            "estado": "ACTIVO", "imagenes": [], "precios": [],
        }
        imagen = {
            "id": "i1", "producto_id": "p1", "variante_id": None,
            "ruta": "img/BotellaCafe.webp", "texto_alternativo": "Botella",
            "es_principal": 1, "orden": 0, "estado": "ACTIVO",
        }
        pack = {
            "pack_id": "pk1", "nombre": "Pack 6", "slug": "pack-6",
            "tipo": "FIJO", "cantidad_unidades": 6, "descripcion": None,
            "peso_embalaje_gramos": Decimal("0"), "estado": "ACTIVO",
            "componentes": [], "reglas": [], "permitidas": [], "precios": [],
        }
        stock_variante = {
            "stock_fisico": 0, "stock_reservado": 0,
            "stock_disponible": 0, "disponible": False,
        }
        stock_pack = {
            "tipo": "FIJO", "packs_disponibles": 0, "componentes": [],
        }
        cliente = cliente_con_sesion(self.app, ["ADMINISTRADOR"])

        with patch("app.admin.catalogo.routes.obtener_selectores", return_value=selectores), \
             patch("app.admin.catalogo.routes.obtener_producto", return_value=producto), \
             patch("app.admin.catalogo.routes.obtener_variante", return_value=variante), \
             patch("app.admin.catalogo.routes.obtener_imagen", return_value=imagen), \
             patch("app.admin.catalogo.routes.obtener_pack", return_value=pack), \
             patch("app.admin.catalogo.routes.obtener_stock_variante", return_value=stock_variante), \
             patch("app.admin.catalogo.routes.obtener_stock_pack", return_value=stock_pack):
            rutas = (
                "/admin/catalogo/productos/p1",
                "/admin/catalogo/variantes/v1",
                "/admin/catalogo/imagenes/i1",
                "/admin/catalogo/packs/pk1",
            )
            for ruta in rutas:
                with self.subTest(ruta=ruta):
                    respuesta = cliente.get(ruta)
                    self.assertEqual(respuesta.status_code, 200)


if __name__ == "__main__":
    unittest.main()
