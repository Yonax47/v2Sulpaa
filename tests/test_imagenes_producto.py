# -*- coding: utf-8 -*-
"""Pruebas de las imágenes reales de producto.

Comprueban que:

1. La función resolver_imagen_producto() elige la imagen correcta
   por sabor y presentación, y devuelve None cuando no hay foto.

2. Favoritos, Ficha y la tarjeta de la tienda ya NO escriben la
   imagen a mano, sino que usan la misma fuente de verdad.

Regresión del bug: en Favoritos, Limón, Jamaica y Café mostraban
la misma imagen porque el HTML tenía fijo 'img/BotellaCafe.png'.
"""
from __future__ import unicode_literals

import unittest
from pathlib import Path

from app.comercio.imagenes import resolver_imagen_producto


RAIZ = Path(__file__).resolve().parents[1]

FAVORITOS = RAIZ / "templates" / "cliente" / "favoritos.html"
FICHA = RAIZ / "templates" / "cliente" / "ficha_producto.html"
PRODUCT_CARD = RAIZ / "templates" / "components" / "product_card.html"
FOTO_COMPONENTE = RAIZ / "templates" / "components" / "foto_producto.html"


def _leer(ruta):
    return ruta.read_text(encoding="utf-8")


class ResolverImagenTest(unittest.TestCase):
    """La función debe elegir la imagen correcta del catálogo."""

    def test_botellas_330ml_por_sabor(self):
        esperado = {
            "Café": "img/BotellaCafe.png",
            "Jamaica": "img/Botellaflordejamaica.png",
            "Kion": "img/Botellakion.png",
            "Limón": "img/Botellalimon.png",
        }
        for sabor, ruta in esperado.items():
            with self.subTest(sabor=sabor):
                self.assertEqual(
                    resolver_imagen_producto(
                        sabor=sabor, presentacion="Botella 330 ml"
                    ),
                    ruta,
                )

    def test_ignora_tildes_y_mayusculas(self):
        self.assertEqual(
            resolver_imagen_producto(sabor="CAFE", presentacion="botella 330 ml"),
            "img/BotellaCafe.png",
        )
        self.assertEqual(
            resolver_imagen_producto(sabor="limon", presentacion="Botella 330 ml"),
            "img/Botellalimon.png",
        )

    def test_botella_de_un_litro_usa_imagen_generica(self):
        self.assertEqual(
            resolver_imagen_producto(sabor="Café", presentacion="Botella 1 L"),
            "img/Botellalitrosulpaa.png",
        )

    def test_barril_usa_imagen_generica(self):
        for barril in ("Barril 30 L", "Barril 50 L"):
            with self.subTest(barril=barril):
                self.assertEqual(
                    resolver_imagen_producto(sabor="Café", presentacion=barril),
                    "img/Barrilsulpaa.png",
                )

    def test_pack_por_sabor(self):
        self.assertEqual(
            resolver_imagen_producto(tipo="PACK", nombre="Pack Café 6"),
            "img/Pack6unidadescafe.jpg",
        )
        self.assertEqual(
            resolver_imagen_producto(tipo="PACK", nombre="Pack Jamaica 6"),
            "img/Pack6unidadesJamaica.jpg",
        )

    def test_pack_desconocido_usa_pack_mixto(self):
        self.assertEqual(
            resolver_imagen_producto(tipo="PACK", nombre="Pack Sorpresa"),
            "img/Packmixto.jpg",
        )

    def test_sabor_sin_foto_devuelve_none(self):
        for sabor in ("Piña", "Frutos Rojos", "Menta", "Maracuyá"):
            with self.subTest(sabor=sabor):
                self.assertIsNone(
                    resolver_imagen_producto(
                        sabor=sabor, presentacion="Botella 330 ml"
                    )
                )

    def test_presentacion_750ml_sin_foto_devuelve_none(self):
        self.assertIsNone(
            resolver_imagen_producto(sabor="Piña", presentacion="Botella 750 ml")
        )


class PlantillasUsanLaFuenteDeVerdadTest(unittest.TestCase):
    """Ninguna plantilla debe fijar la imagen de un sabor a mano."""

    def test_favoritos_no_fija_la_botella_de_cafe(self):
        html = _leer(FAVORITOS)
        self.assertNotIn("img/BotellaCafe.png", html)
        self.assertIn("foto_producto", html)

    def test_ficha_no_fija_imagenes_por_sabor(self):
        html = _leer(FICHA)
        self.assertNotIn("img/BotellaCafe.png", html)
        self.assertNotIn("imagenes_sabor", html)
        self.assertIn("foto_producto", html)

    def test_tarjeta_de_producto_usa_el_componente(self):
        html = _leer(PRODUCT_CARD)
        self.assertNotIn("filename=producto.imagen", html)
        self.assertIn("foto_producto", html)

    def test_existe_el_componente_de_foto(self):
        self.assertTrue(FOTO_COMPONENTE.exists())
        html = _leer(FOTO_COMPONENTE)
        self.assertIn("imagen_producto", html)
        self.assertIn("producto-sin-foto", html)


if __name__ == "__main__":
    unittest.main()
