# -*- coding: utf-8 -*-
"""Pruebas de las gráficas administrativas (dashboard y encuestas).

Verifican que los canvas del dashboard vivan dentro del contenido
(no incrustados en el bloque de scripts — eso causaba el desborde
inferior) y que la agregación de encuestas use datos reales.
"""
from __future__ import unicode_literals

import unittest
from pathlib import Path

from app.admin.encuestas.services import estadisticas_encuestas
from app.admin.caja import repositories as caja_repos


class DashboardLayoutTest(unittest.TestCase):
    def test_canvas_gerenciales_dentro_del_contenido(self):
        origen = Path("templates/admin/dashboard.html").read_text(encoding="utf-8")
        fin_contenido = origen.index("{% block page_js %}")
        bloque_contenido = origen[:fin_contenido]
        for marcador in (
            "chart-top-cobrados",
            "chart-ingresos-producto",
            "chart-evol-ventas",
            "chart-flujo-caja-2",
            "chart-estados-pedidos",
        ):
            self.assertIn(marcador, bloque_contenido)


class EstadisticasEncuestasTest(unittest.TestCase):
    def test_agrega_por_estado_y_satisfaccion(self):
        encuestas = [
            {"estado": "RESPONDIDA", "calificacion_general": 5, "recomendaria": 1},
            {"estado": "RESPONDIDA", "calificacion_general": 3, "recomendaria": 0},
            {"estado": "ENVIADA", "calificacion_general": None, "recomendaria": None},
            {"estado": "PENDIENTE", "calificacion_general": None, "recomendaria": None},
        ]
        estadisticas = estadisticas_encuestas(encuestas)

        conteos = {fila["estado"]: fila["cantidad"] for fila in estadisticas["por_estado"]}
        self.assertEqual(conteos["RESPONDIDA"], 2)
        self.assertEqual(conteos["ENVIADA"], 1)
        self.assertEqual(conteos["PENDIENTE"], 1)
        self.assertEqual(estadisticas["respuestas"], 2)
        self.assertEqual(estadisticas["promedio"], 4.0)
        self.assertEqual(estadisticas["recomendarian"], 1)

    def test_lista_vacia_no_rompe(self):
        estadisticas = estadisticas_encuestas([])
        self.assertEqual(estadisticas["por_estado"], [])
        self.assertIsNone(estadisticas["promedio"])
        self.assertEqual(estadisticas["respuestas"], 0)


class CajaFlujoSerieTest(unittest.TestCase):
    def test_serie_flujo_mensual_no_lanza_y_devuelve_filas(self):
        # Regresión: el SQL usaba '%Y-%m' sin escapar con parámetros
        # ligados; PyMySQL lanzaba ValueError y el servicio lo
        # silenciaba devolviendo []. Debe devolver una lista real.
        filas = caja_repos.serie_flujo_mensual()
        self.assertIsInstance(filas, list)
        for fila in filas:
            self.assertIn("periodo", fila)
            self.assertIn("ingresos", fila)
            self.assertIn("egresos", fila)


if __name__ == "__main__":
    unittest.main()
