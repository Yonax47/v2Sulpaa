# -*- coding: utf-8 -*-
"""Contrato del carrito lateral y los favoritos.

Estas pruebas comprueban dos cosas sin abrir un navegador:

1. El backend entrega los datos que el carrito lateral necesita
   (sabor, presentación y variante) además de lo que ya entregaba.

2. La interfaz cumple el contrato acordado:
   - el carrito vive en un solo componente y un solo archivo;
   - la tienda, los favoritos y la ficha agregan al carrito real;
   - ya no quedan copias antiguas de la lógica del carrito.
"""
from __future__ import unicode_literals

import unittest
from pathlib import Path
from unittest.mock import patch

from app.comercio import services


RAIZ = Path(__file__).resolve().parents[1]

CART_JS = RAIZ / "static" / "js" / "modules" / "cart.js"
STORE_JS = RAIZ / "static" / "js" / "modules" / "store.js"
CART_DRAWER = RAIZ / "templates" / "components" / "cart_drawer.html"
NAVBAR = RAIZ / "templates" / "components" / "navbar.html"
BASE = RAIZ / "templates" / "base.html"
TIENDA = RAIZ / "templates" / "cliente" / "tienda.html"
FAVORITOS = RAIZ / "templates" / "cliente" / "favoritos.html"
FICHA = RAIZ / "templates" / "cliente" / "ficha_producto.html"
CART_CSS = RAIZ / "static" / "css" / "components" / "cart.css"
STORE_CSS = RAIZ / "static" / "css" / "pages" / "store.css"


def _leer(ruta):
    return ruta.read_text(encoding="utf-8")


class ContratoBackendCarritoTest(unittest.TestCase):
    """El servicio del carrito debe exponer datos descriptivos."""

    def setUp(self):
        self.peso = {
            "peso_total_gramos": 0.0,
            "peso_total_kg": 0.0,
            "peso_completo": True,
            "variantes_sin_peso": [],
        }

    def test_item_variante_incluye_sabor_presentacion_y_variante(self):
        detalle = {
            "carrito_detalle_id": "d-1",
            "articulo_venta_id": "av-1",
            "cantidad": 2,
            "tipo": "VARIANTE",
            "nombre_comercial": "Kombucha SULPAA - Café - Botella 330 ml",
            "pack_nombre": None,
            "precio": 10.5,
            "moneda": "PEN",
            "variante_id": "v-1",
            "sabor": "Café",
            "presentacion": "Botella 330 ml",
        }
        with patch.object(
            services, "obtener_detalles_carrito_usuario", return_value=[detalle]
        ):
            with patch.object(
                services, "obtener_composiciones_carrito", return_value=[]
            ):
                with patch.object(
                    services, "_calcular_peso_carrito", return_value=self.peso
                ):
                    carrito = services.obtener_carrito_usuario("usuario-1")

        item = carrito["items"][0]
        self.assertEqual(item["sabor"], "Café")
        self.assertEqual(item["presentacion"], "Botella 330 ml")
        self.assertEqual(item["variante_id"], "v-1")
        self.assertEqual(item["tipo"], "VARIANTE")
        self.assertEqual(item["subtotal"], 21.0)

    def test_item_pack_tiene_sabor_y_presentacion_nulos(self):
        detalle = {
            "carrito_detalle_id": "d-2",
            "articulo_venta_id": "av-2",
            "cantidad": 1,
            "tipo": "PACK",
            "nombre_comercial": None,
            "pack_nombre": "Pack 6 - Jamaica - 330 ml",
            "precio": 55.0,
            "moneda": "PEN",
            "variante_id": None,
            "sabor": None,
            "presentacion": None,
        }
        with patch.object(
            services, "obtener_detalles_carrito_usuario", return_value=[detalle]
        ):
            with patch.object(
                services, "obtener_composiciones_carrito", return_value=[]
            ):
                with patch.object(
                    services, "_calcular_peso_carrito", return_value=self.peso
                ):
                    carrito = services.obtener_carrito_usuario("usuario-1")

        item = carrito["items"][0]
        self.assertIsNone(item["sabor"])
        self.assertIsNone(item["presentacion"])
        self.assertEqual(item["nombre"], "Pack 6 - Jamaica - 330 ml")
        self.assertEqual(carrito["cantidad_items"], 1)


class ContratoComponenteCarritoTest(unittest.TestCase):
    """El carrito debe ser un componente reutilizable y único."""

    def test_drawer_existe_y_tiene_los_anclajes(self):
        html = _leer(CART_DRAWER)
        for anclaje in (
            "data-cart-drawer",
            "data-cart-overlay",
            "data-cart-close",
            "data-cart-content",
            "data-cart-subtotal",
            "data-cart-continue",
            "data-cart-static",
            "data-cart-store-url",
        ):
            self.assertIn(anclaje, html)

    def test_navbar_incluye_carrito_y_lo_abre(self):
        html = _leer(NAVBAR)
        self.assertIn('include "components/cart_drawer.html"', html)
        self.assertIn("data-cart-open", html)
        self.assertIn("data-cart-count", html)

    def test_base_carga_el_modulo_del_carrito(self):
        html = _leer(BASE)
        self.assertIn("js/modules/cart.js", html)

    def test_tienda_ya_no_define_otro_carrito(self):
        html = _leer(TIENDA)
        self.assertNotIn("data-cart-drawer", html)
        self.assertNotIn("data-cart-overlay", html)
        self.assertIn('id="store-cart-data"', html)


class ContratoCssGlobalCarritoTest(unittest.TestCase):
    """El carrito debe verse bien en TODAS las páginas, no solo en la tienda.

    Regresión: el panel se mostraba como contenido suelto (bloque
    gigante) fuera de la tienda porque sus estilos vivían en
    store.css, que solo se carga en las páginas de tienda.
    """

    def test_base_carga_el_css_global_del_carrito(self):
        html = _leer(BASE)
        self.assertIn("css/components/cart.css", html)

    def test_existe_el_css_global_del_carrito(self):
        self.assertTrue(CART_CSS.exists(), "Falta static/css/components/cart.css")

    def test_el_panel_esta_oculto_por_defecto(self):
        css = _leer(CART_CSS)
        self.assertIn(".store-cart-drawer", css)
        self.assertIn("position: fixed", css)
        self.assertIn("translateX(105%)", css)
        self.assertIn("visibility: hidden", css)

    def test_el_css_global_incluye_overlay_contador_y_toast(self):
        css = _leer(CART_CSS)
        self.assertIn(".store-cart-overlay", css)
        self.assertIn("[data-cart-count][hidden]", css)
        self.assertIn(".store-toast", css)
        self.assertIn(".store-cart-btn-primary", css)
        self.assertIn(".store-cart-btn-secondary", css)

    def test_la_tienda_ya_no_define_el_panel(self):
        css = _leer(STORE_CSS)
        self.assertNotIn(".store-cart-drawer {", css)
        self.assertNotIn(".store-toast {", css)
        self.assertNotIn("[data-cart-count] {", css)

    def test_drawer_no_depende_de_los_botones_de_tienda(self):
        html = _leer(CART_DRAWER)
        self.assertIn("store-cart-btn", html)
        self.assertNotIn("store-btn", html)


class ContratoModuloCarritoTest(unittest.TestCase):
    """cart.js concentra toda la lógica del carrito."""

    def setUp(self):
        self.source = _leer(CART_JS)

    def test_expone_api_publica(self):
        self.assertIn("window.SulpaaCart", self.source)
        for funcion in ("open:", "close:", "refresh:", "render:", "add:"):
            self.assertIn(funcion, self.source)

    def test_expone_toast_reutilizable(self):
        self.assertIn("window.SulpaaToast", self.source)

    def test_usa_los_endpoints_reales(self):
        for ruta in (
            "/api/carrito",
            "/api/carrito/agregar",
            "/api/carrito/actualizar",
            "/api/carrito/eliminar",
        ):
            self.assertIn(ruta, self.source)

    def test_se_desactiva_si_no_hay_carrito_en_la_pagina(self):
        self.assertIn("if (!elemento.drawer", self.source)

    def test_resuelve_imagenes_reales_y_placeholder(self):
        self.assertIn("resolverImagen", self.source)
        self.assertIn("placeholderImagen", self.source)


class ContratoStoreDelegaTest(unittest.TestCase):
    """store.js ya no duplica la lógica del carrito."""

    def setUp(self):
        self.source = _leer(STORE_JS)

    def test_addtocart_delega_en_el_modulo(self):
        self.assertIn("window.SulpaaCart.add", self.source)

    def test_ya_no_hay_render_de_carrito_duplicado(self):
        self.assertNotIn("function renderCart", self.source)
        self.assertNotIn("function refreshCart", self.source)

    def test_ya_no_llama_directo_al_endpoint_de_agregar(self):
        self.assertNotIn("/api/carrito/agregar", self.source)


class ContratoFavoritosCompraTest(unittest.TestCase):
    """El botón Comprar de favoritos agrega al carrito real."""

    def setUp(self):
        self.html = _leer(FAVORITOS)

    def test_boton_compra_usa_el_carrito(self):
        self.assertIn("data-fav-buy", self.html)
        self.assertIn("window.SulpaaCart.add", self.html)

    def test_compra_envia_el_articulo_de_venta(self):
        self.assertIn("data-articulo-venta-id", self.html)

    def test_agotado_queda_deshabilitado(self):
        self.assertIn("Agotado", self.html)


class ContratoFichaCompraTest(unittest.TestCase):
    """La ficha agrega al carrito con el mismo módulo."""

    def setUp(self):
        self.html = _leer(FICHA)

    def test_boton_usa_el_carrito(self):
        self.assertIn("data-ficha-buy", self.html)
        self.assertIn("window.SulpaaCart.add", self.html)

    def test_ya_no_existe_la_funcion_antigua(self):
        self.assertNotIn("agregarProducto", self.html)


if __name__ == "__main__":
    unittest.main()
