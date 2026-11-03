# -*- coding: utf-8 -*-
"""Regresiones de interfaz incorporadas en la Fase 4.1.

Estas pruebas no abren conexiones ni escriben en las bases de datos. Validan
plantillas, rutas y contratos estáticos con datos sintéticos.
"""

import json
import re
import unittest
from datetime import datetime
from pathlib import Path

from flask import flash, render_template

from app import create_app


RAIZ = Path(__file__).resolve().parents[1]
PLANTILLAS_GRAFICOS = (
    RAIZ / "templates/admin/dashboard.html",
    RAIZ / "templates/admin/caja/lista.html",
    RAIZ / "templates/admin/encuestas/lista.html",
)


class GraficosFase41Test(unittest.TestCase):
    """Evita que reaparezca la doble conversión de datos Jinja a JSON."""

    def test_no_existe_json_parse_aplicado_a_tojson(self):
        patron = re.compile(r"JSON\.parse\s*\(\s*\{\{[^}]*\|\s*tojson")
        for ruta in PLANTILLAS_GRAFICOS:
            contenido = ruta.read_text(encoding="utf-8")
            self.assertIsNone(patron.search(contenido), str(ruta))

    def test_las_cinco_series_utilizan_asignacion_directa(self):
        dashboard = PLANTILLAS_GRAFICOS[0].read_text(encoding="utf-8")
        caja = PLANTILLAS_GRAFICOS[1].read_text(encoding="utf-8")
        encuestas = PLANTILLAS_GRAFICOS[2].read_text(encoding="utf-8")

        self.assertIn("var flujo = {{ graficos.flujo_caja | tojson }}", dashboard)
        self.assertIn("var kpi09 = {{ graficos.kpi09 | tojson }}", dashboard)
        self.assertIn("var gerencial = {{ gerencial | tojson }}", dashboard)
        self.assertIn("var serie = {{ serie_flujo | tojson }}", caja)
        self.assertIn(
            "var porEstado = {{ estadisticas.por_estado | tojson }}",
            encuestas,
        )

    def test_tojson_renderiza_datos_sinteticos_validos(self):
        app = create_app()
        plantilla = app.jinja_env.from_string("{{ datos | tojson }}")
        datos = [{"periodo": "2026-10", "total": 1006.12}]
        renderizado = plantilla.render(datos=datos)
        self.assertEqual(json.loads(renderizado), datos)

    def test_chartjs_es_local_y_existen_estados_vacios(self):
        for ruta in PLANTILLAS_GRAFICOS:
            contenido = ruta.read_text(encoding="utf-8")
            self.assertIn("vendor/chart.umd.min.js", contenido)
        self.assertIn("Sin movimientos de caja", PLANTILLAS_GRAFICOS[0].read_text(encoding="utf-8"))
        self.assertIn("Sin datos para graficar", PLANTILLAS_GRAFICOS[1].read_text(encoding="utf-8"))

    def test_dashboard_renderiza_datos_sinteticos_y_estado_vacio(self):
        app = create_app()
        resumen = {
            "total": 0, "instrumentados": 0, "con_evidencia": 0,
            "pendientes_de_datos": 0, "cumplen": 0, "no_cumplen": 0,
        }
        operativo = {
            "pedidos_iniciados": 0, "pedidos_completados": 0,
            "entregas": 0, "productos_con_stock_bajo": 0,
            "ingresos": 0, "egresos": 0, "flujo_neto": 0,
            "encuestas_completadas": 0, "satisfaccion_promedio": None,
        }
        gerencial = {
            "ventas_cobradas": {"pedidos_cobrados": 1, "ingresos_cobrados": 25},
            "top_productos_cobrados": [], "ingresos_por_producto": [],
            "ventas_cobradas_por_dia": [], "pedidos_por_estado": [],
            "caja_resumen": {"ingresos": 25, "egresos": 0},
        }
        with app.test_request_context("/"):
            html = render_template(
                "admin/dashboard.html",
                kpis=[], resumen=resumen, operativo=operativo,
                graficos={"flujo_caja": [{"periodo": "2026-10", "ingresos": 25, "egresos": 0}], "kpi09": None, "satisfaccion": None},
                gerencial=gerencial,
            )
            vacio = render_template(
                "admin/dashboard.html",
                kpis=[], resumen=resumen, operativo=operativo,
                graficos={"flujo_caja": [], "kpi09": None, "satisfaccion": None},
                gerencial=gerencial,
            )
        self.assertIn('"periodo": "2026-10"', html)
        self.assertNotIn("JSON.parse", html)
        self.assertIn("Sin movimientos de caja registrados", vacio)

    def test_caja_y_encuestas_renderizan_series_sinteticas(self):
        app = create_app()
        with app.test_request_context("/"):
            caja = render_template(
                "admin/caja/lista.html",
                serie_flujo=[{"periodo": "2026-10", "ingresos": 40, "egresos": 10}],
                movimientos=[], categorias=[],
                resumen={"total_movimientos": 0, "ingresos": 40, "egresos": 10, "flujo_neto": 30},
                filtros={"desde": "", "hasta": "", "tipo": "", "origen": "", "categoria_id": ""},
            )
            encuestas = render_template(
                "admin/encuestas/lista.html",
                encuestas=[{
                    "id": 1, "numero_pedido": "PED-TEST", "usuario_id": "usuario-test",
                    "estado": "RESPONDIDA", "canal": "PORTAL",
                    "calificacion_general": 5, "recomendaria": "SI",
                    "creado_en": datetime(2026, 10, 1, 12, 0),
                }],
                filtros={"estado": "", "desde": "", "hasta": ""},
                estadisticas={
                    "por_estado": [{"estado": "RESPONDIDA", "cantidad": 1}],
                    "promedio": 5, "respuestas": 1, "recomendarian": 1,
                },
            )
        self.assertIn('"periodo": "2026-10"', caja)
        self.assertIn('"estado": "RESPONDIDA"', encuestas)
        self.assertNotIn("JSON.parse", caja + encuestas)


class NotificacionesFase41Test(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)

    def test_solo_el_componente_global_consume_los_flash(self):
        coincidencias = []
        for ruta in (RAIZ / "templates").rglob("*.html"):
            if "get_flashed_messages" in ruta.read_text(encoding="utf-8"):
                coincidencias.append(ruta.relative_to(RAIZ).as_posix())
        self.assertEqual(
            coincidencias,
            ["templates/components/flash_messages.html"],
        )

    def test_error_se_presenta_como_danger_y_escapa_html(self):
        with self.app.test_request_context("/"):
            flash("<script>dato sensible</script>", "error")
            html = render_template("components/flash_messages.html")
        self.assertIn("sulpaa-toast is-danger", html)
        self.assertNotIn("is-error", html)
        self.assertNotIn("<script>dato sensible</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_categorias_profesionales_disponibles(self):
        with self.app.test_request_context("/"):
            for categoria in ("success", "danger", "warning", "info"):
                flash(categoria, categoria)
            html = render_template("components/flash_messages.html")
        for categoria in ("success", "danger", "warning", "info"):
            self.assertIn("is-" + categoria, html)
        self.assertIn('aria-live="polite"', html)

    def test_base_incluye_el_componente_una_sola_vez(self):
        base = (RAIZ / "templates/base.html").read_text(encoding="utf-8")
        self.assertEqual(base.count('components/flash_messages.html'), 1)


class LogoutFase41Test(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def test_logout_solo_admite_post(self):
        regla = next(
            regla
            for regla in self.app.url_map.iter_rules()
            if regla.endpoint == "identidad.logout"
        )
        self.assertIn("POST", regla.methods)
        self.assertNotIn("GET", regla.methods)
        self.assertEqual(self.client.get(str(regla)).status_code, 405)

    def test_post_sin_csrf_es_rechazado(self):
        regla = next(
            regla
            for regla in self.app.url_map.iter_rules()
            if regla.endpoint == "identidad.logout"
        )
        self.assertEqual(self.client.post(str(regla)).status_code, 400)

    def test_sidebar_conserva_logout_y_agrega_acceso_movil(self):
        contenido = (
            RAIZ / "templates/admin/components/sidebar.html"
        ).read_text(encoding="utf-8")
        self.assertEqual(contenido.count("url_for('identidad.logout')"), 2)
        self.assertEqual(contenido.count('method="POST"'), 2)
        self.assertEqual(contenido.count('name="csrf_token"'), 2)
        self.assertIn("admin-mobile-logout-form", contenido)
        self.assertIn("Cerrar sesión", contenido)

        estilos = (RAIZ / "static/css/pages/admin.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 900px)", estilos)
        self.assertIn(".admin-mobile-logout-form", estilos)
        self.assertIn("display: block", estilos)

    def test_cliente_y_repartidor_conservan_logout_seguro(self):
        navbar = (RAIZ / "templates/components/navbar.html").read_text(encoding="utf-8")
        repartidor = (
            RAIZ / "templates/repartidor/components/cabecera.html"
        ).read_text(encoding="utf-8")
        self.assertEqual(navbar.count("url_for('identidad.logout')"), 2)
        self.assertEqual(navbar.count('method="POST"'), 2)
        self.assertGreaterEqual(navbar.count('name="csrf_token"'), 2)
        self.assertIn("url_for('identidad.logout')", repartidor)
        self.assertIn('method="POST"', repartidor)
        self.assertIn('name="csrf_token"', repartidor)


class PlantillasFase41Test(unittest.TestCase):
    def test_todas_las_plantillas_compilan(self):
        app = create_app()
        for nombre in app.jinja_env.list_templates():
            app.jinja_env.get_template(nombre)


if __name__ == "__main__":
    unittest.main()
