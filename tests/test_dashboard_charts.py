# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re
import unittest
from pathlib import Path

from app import create_app


class DashboardChartsTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_chart_canvases_present_in_html(self):
        # Access dashboard as anonymous client - we expect redirect; but
        # render logic happens in view; here we just ensure template has ids
        from pathlib import Path
        html = Path('templates/admin/dashboard.html').read_text(encoding='utf-8', errors='ignore')
        for cid in [
            'chart-top-cobrados',
            'chart-ingresos-producto',
            'chart-evol-ventas',
            'chart-flujo-caja-2',
            'chart-estados-pedidos',
        ]:
            self.assertIn(cid, html)

    def test_gerencial_has_required_keys(self):
        from app.admin import services
        g = services.obtener_resumen_gerencial()
        for k in ['top_productos_cobrados', 'ingresos_por_producto', 'ventas_cobradas_por_dia', 'pedidos_por_estado', 'caja_resumen']:
            self.assertIn(k, g)


# Plantillas que contienen código Chart.js de los gráficos administrativos.
_RUTAS_CON_GRAFICOS = (
    "templates/admin/dashboard.html",
    "templates/admin/caja/lista.html",
    "templates/admin/encuestas/lista.html",
)

# Detecta cada `map(function (param) { return ... var.` para comprobar
# que la variable usada dentro del cuerpo sea la declarada como parámetro.
_PATRON_MAP = re.compile(
    r"\.map\(\s*function\s*\(\s*(\w+)\s*\)\s*\{\s*return\s+[^;{}]*?(\w+)\.",
    re.DOTALL,
)

_PATRON_CANVAS = re.compile(r'getElementById\("(chart-[\w-]+)"\)')


class GraficosVariableRegressionTest(unittest.TestCase):
    """Regresión: los callbacks de los gráficos no deben usar variables
    distintas a las declaradas (p. ej. ``function (d) { ... p.fecha ... }``)."""

    def test_map_no_referencia_variable_inexistente(self):
        for ruta in (
            "templates/admin/dashboard.html",
            "templates/admin/caja/lista.html",
            "templates/admin/encuestas/lista.html",
        ):
            contenido = Path(ruta).read_text(encoding="utf-8", errors="ignore")
            coincidencias = _PATRON_MAP.findall(contenido)
            self.assertTrue(coincidencias, "No se encontraron map() en %s" % ruta)
            for declarada, usada in coincidencias:
                self.assertEqual(
                    declarada,
                    usada,
                    "%s: el callback declara '%s' pero usa '%s'."
                    % (ruta, declarada, usada),
                )

    def test_canvas_referenciados_existen_en_la_plantilla(self):
        for ruta in (
            "templates/admin/dashboard.html",
            "templates/admin/caja/lista.html",
            "templates/admin/encuestas/lista.html",
        ):
            contenido = Path(ruta).read_text(encoding="utf-8", errors="ignore")
            for cid in _PATRON_CANVAS.findall(contenido):
                self.assertIn(
                    'id="%s"' % cid,
                    contenido,
                    "%s: el grafico referencia #%s pero no existe el canvas."
                    % (ruta, cid),
                )


class DashboardRenderAisladoTest(unittest.TestCase):
    """Renderiza el dashboard con datos gerenciales de prueba (sin tocar
    la base de datos) y comprueba que el JS recibe esos datos con la
    variable correcta."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sesion:
            sesion["autenticado"] = True
            sesion["usuario_id"] = "e5b16653-a98d-4838-9e33-074b6423be75"
            sesion["correo"] = "i2512609@continental.edu.pe"
            sesion["roles"] = ["GERENTE"]

    def test_dashboard_recibe_datos_gerenciales_de_prueba(self):
        from unittest.mock import patch

        gerencial_falso = {
            "ventas_cobradas": {"pedidos_cobrados": 1, "ingresos_cobrados": 10.0},
            "top_productos_cobrados": [],
            "ingresos_por_producto": [],
            "ventas_cobradas_por_dia": [{"fecha": "2026-10-16", "total": 10.0}],
            "pedidos_por_estado": [],
            "caja_resumen": {"ingresos": 10.0, "egresos": 0.0},
        }
        with patch(
            "app.admin.routes.obtener_resumen_gerencial",
            return_value=gerencial_falso,
        ):
            respuesta = self.client.get("/admin/dashboard")

        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.get_data(as_text=True)
        self.assertIn("2026-10-16", html)
        self.assertIn("return String(d.fecha)", html)
        self.assertNotIn("return String(p.fecha)", html)


if __name__ == '__main__':
    unittest.main()
