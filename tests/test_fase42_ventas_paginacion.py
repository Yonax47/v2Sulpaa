import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from flask import render_template

from app import create_app
from app.admin import repositories, services
from app.admin.pedidos import repositories as pedidos_repositories
from app.shared.pagination import crear_paginacion, normalizar_paginacion


class VentasCobradasTest(unittest.TestCase):
    def test_series_dia_mes_anio(self):
        casos = (
            ("dia", "2026-11-03", "03/11/2026"),
            ("mes", "2026-11", "nov 2026"),
            ("anio", "2026", "2026"),
        )
        for periodo, clave, etiqueta in casos:
            with self.subTest(periodo=periodo):
                fila = {
                    "periodo": clave,
                    "ventas": 2,
                    "ingresos": Decimal("25.50"),
                }
                with patch.object(repositories, "obtener_resumen_pedidos_financiero", return_value={}), \
                     patch.object(repositories, "obtener_ventas_cobradas", return_value={}), \
                     patch.object(repositories, "obtener_serie_ventas_cobradas", return_value=[fila]) as consulta, \
                     patch.object(repositories, "obtener_top_productos_vendidos_cobrados", return_value=[]), \
                     patch.object(repositories, "obtener_ingresos_por_producto_cobrado", return_value=[]), \
                     patch.object(repositories, "obtener_pedidos_por_estado_agrupado", return_value=[]), \
                     patch.object(repositories, "obtener_caja_movimientos_resumen", return_value={}):
                    resultado = services.obtener_resumen_gerencial(
                        periodo=periodo,
                        desde="2026-01-01",
                        hasta="2026-12-31",
                    )

                consulta.assert_called_once_with(
                    periodo, date(2026, 1, 1), date(2026, 12, 31)
                )
                self.assertEqual(
                    resultado["ventas_cobradas_serie"],
                    [{
                        "periodo": clave,
                        "etiqueta": etiqueta,
                        "ventas": 2,
                        "ingresos": 25.5,
                    }],
                )

    def test_filtros_financieros_invalidos(self):
        for opciones in (
            {"periodo": "semana"},
            {"desde": "03/11/2026"},
            {"desde": "2026-12-01", "hasta": "2026-01-01"},
        ):
            with self.subTest(opciones=opciones):
                with self.assertRaises(ValueError):
                    services.obtener_resumen_gerencial(**opciones)

    def test_subconsulta_deduplica_por_pedido_y_fecha_primera(self):
        sql = repositories._subconsulta_primer_cobro("operaciones")
        self.assertIn("MIN(pagado_en)", sql)
        self.assertIn("GROUP BY pedido_id", sql)
        self.assertIn("estado = 'PAGADO'", sql)

    def test_serie_parametriza_fechas_y_no_duplica_pagos(self):
        cursor = _CursorFalso(filas=[])
        conexion = _ConexionFalsa(cursor)
        with patch.object(repositories, "conexion_comercio", return_value=conexion), \
             patch.object(repositories, "nombre_esquema", side_effect=lambda nombre: {
                 "DB_COMERCIO": "comercio_test",
                 "DB_OPERACIONES": "operaciones_test",
             }[nombre]):
            resultado = repositories.obtener_serie_ventas_cobradas(
                "mes", date(2026, 1, 1), date(2026, 12, 31)
            )

        self.assertEqual(resultado, [])
        consulta, parametros = cursor.ejecuciones[0]
        self.assertIn("MIN(pagado_en)", consulta)
        self.assertIn("GROUP BY pedido_id", consulta)
        self.assertIn("DATE_FORMAT(cobro.pagado_en, '%Y-%m')", consulta)
        self.assertIn("DATE_ADD(%s, INTERVAL 1 DAY)", consulta)
        self.assertEqual(
            parametros, [date(2026, 1, 1), date(2026, 12, 31)]
        )


class PaginacionTest(unittest.TestCase):
    def test_parametros_invalidos_usan_valores_seguros(self):
        self.assertEqual(normalizar_paginacion("x", "1000"), (1, 25))
        self.assertEqual(normalizar_paginacion("-3", "0"), (1, 25))

    def test_primera_y_ultima_pagina(self):
        primera = crear_paginacion(51, 1, 25)
        ultima = crear_paginacion(51, 99, 25)
        self.assertEqual(primera["offset"], 0)
        self.assertTrue(primera["tiene_siguiente"])
        self.assertEqual(ultima["pagina"], 3)
        self.assertEqual(ultima["offset"], 50)
        self.assertFalse(ultima["tiene_siguiente"])
        self.assertTrue(ultima["tiene_anterior"])

    def test_conserva_filtros_no_vacios(self):
        datos = crear_paginacion(
            30,
            1,
            25,
            endpoint="admin_pedidos.listado",
            filtros={"q": "Ana", "estado": "PAGADO", "fecha_desde": ""},
        )
        self.assertEqual(
            datos["filtros"], {"q": "Ana", "estado": "PAGADO"}
        )

    def test_repositorio_usa_limite_offset_y_orden_estable(self):
        cursor = _CursorFalso(filas=[])
        conexion = _ConexionFalsa(cursor)
        pedidos_repositories.listar_pedidos(
            conexion,
            {
                "comercio": "comercio_test",
                "operaciones": "operaciones_test",
                "identidad": "identidad_test",
            },
            busqueda="PED-1",
            limite=10,
            offset=20,
        )
        consulta, parametros = cursor.ejecuciones[0]
        self.assertIn("ORDER BY p.creado_en DESC, p.id DESC", consulta)
        self.assertIn("ORDER BY e2.creado_en DESC, e2.id DESC LIMIT 1", consulta)
        self.assertIn("LIMIT %s OFFSET %s", consulta)
        self.assertEqual(parametros[-2:], (10, 20))

    def test_componente_conserva_filtros_en_enlaces(self):
        app = create_app()
        paginacion = crear_paginacion(
            60,
            2,
            25,
            endpoint="admin_pedidos.listado",
            filtros={"q": "Ana", "estado": "CONFIRMADO"},
        )
        with app.test_request_context("/admin/pedidos/"):
            html = render_template(
                "admin/components/pagination.html",
                paginacion=paginacion,
            )
        self.assertIn("q=Ana", html)
        self.assertIn("estado=CONFIRMADO", html)
        self.assertIn("page=1", html)
        self.assertIn("page=3", html)


class _CursorFalso:
    def __init__(self, filas=None, fila=None):
        self.filas = filas or []
        self.fila = fila or {"total": 0}
        self.ejecuciones = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, consulta, parametros=None):
        self.ejecuciones.append((consulta, parametros))

    def fetchall(self):
        return self.filas

    def fetchone(self):
        return self.fila


class _ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor
        self.cerrada = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.cerrada = True


if __name__ == "__main__":
    unittest.main()
