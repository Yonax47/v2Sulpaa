import unittest
from unittest.mock import patch

import app.operaciones.services as servicios


def _base_patches():
    """
    Devuelve los parches comunes que simulan una cotización
    válida. Cada prueba ajusta lo que necesite.
    """
    return {
        "_obtener_datos_carrito_entrega": {"ok": True, "peso_gramos": 2000},
        "obtener_transportista_activo": {
            "id": "t1",
            "codigo": "SHALOM",
            "nombre": "Shalom",
            "url_seguimiento": "https://shalom.com.pe/",
        },
        "obtener_servicio_transportista_activo": {
            "id": "s1",
            "codigo": "AGENCIA_AGENCIA",
            "nombre": "Agencia a agencia",
            "modalidad": "AGENCIA_AGENCIA",
        },
        "obtener_tarifario_activo_transportista": {"id": "tar1"},
        "obtener_regla_tarifa_transportista": {
            "id": "reg1",
            "metodo_calculo": "HIBRIDO",
            "peso_maximo_gramos": 20000,
            "recargo_fijo": 0,
        },
        "obtener_rango_tarifa_por_peso": {"id": "ran1", "precio": 15.0},
    }


class CotizacionCoberturaTest(unittest.TestCase):
    """
    Verifica que el distrito de destino del cliente se
    valide contra la cobertura del servicio, sin confundirlo
    con el distrito físico de la agencia.
    """

    def test_agencia_cercana_permite_distrito_distinto_al_de_la_agencia(self):
        """Cobertura de agencia cercana acepta distritos sin agencia física."""
        base = _base_patches()
        with patch.object(servicios, "_obtener_datos_carrito_entrega", return_value=base["_obtener_datos_carrito_entrega"]):
            with patch.object(servicios, "obtener_transportista_activo", return_value=base["obtener_transportista_activo"]):
                with patch.object(servicios, "obtener_servicio_transportista_activo", return_value=base["obtener_servicio_transportista_activo"]):
                    with patch.object(servicios, "obtener_cobertura_servicio_distrito", return_value={"tipo_cobertura": "AGENCIA_CERCANA"}):
                        with patch.object(servicios, "obtener_sucursal_destino_activa", return_value={"id": "ag1", "nombre": "Agencia Central", "direccion": "Av. Mexico 1187", "distrito_id": "150115"}):
                            with patch.object(servicios, "obtener_tarifario_activo_transportista", return_value=base["obtener_tarifario_activo_transportista"]):
                                with patch.object(servicios, "obtener_regla_tarifa_transportista", return_value=base["obtener_regla_tarifa_transportista"]):
                                    with patch.object(servicios, "obtener_rango_tarifa_por_peso", return_value=base["obtener_rango_tarifa_por_peso"]):
                                        resultado = servicios.cotizar_envio_transportista(
                                            "usuario-1", "t1", "s1", "150101", "ag1"
                                        )
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["costo_entrega"], 15.0)
        self.assertEqual(resultado["distrito_destino_id"], "150101")
        self.assertEqual(resultado["tipo_cobertura"], "AGENCIA_CERCANA")

    def test_sin_cobertura_rechaza_la_cotizacion(self):
        """Un distrito sin cobertura rechaza la cotización."""
        base = _base_patches()
        with patch.object(servicios, "_obtener_datos_carrito_entrega", return_value=base["_obtener_datos_carrito_entrega"]):
            with patch.object(servicios, "obtener_transportista_activo", return_value=base["obtener_transportista_activo"]):
                with patch.object(servicios, "obtener_servicio_transportista_activo", return_value=base["obtener_servicio_transportista_activo"]):
                    with patch.object(servicios, "obtener_cobertura_servicio_distrito", return_value=None):
                        resultado = servicios.cotizar_envio_transportista(
                            "usuario-1", "t1", "s1", "150999", "ag1"
                        )
        self.assertFalse(resultado["ok"])
        self.assertIn("cobertura", resultado["mensaje"])

    def test_cobertura_directa_rechaza_agencia_de_otro_distrito(self):
        """Cobertura directa exige que la agencia sea del distrito de destino."""
        base = _base_patches()
        with patch.object(servicios, "_obtener_datos_carrito_entrega", return_value=base["_obtener_datos_carrito_entrega"]):
            with patch.object(servicios, "obtener_transportista_activo", return_value=base["obtener_transportista_activo"]):
                with patch.object(servicios, "obtener_servicio_transportista_activo", return_value=base["obtener_servicio_transportista_activo"]):
                    with patch.object(servicios, "obtener_cobertura_servicio_distrito", return_value={"tipo_cobertura": "DIRECTA"}):
                        with patch.object(servicios, "obtener_sucursal_destino_activa", return_value={"id": "ag1", "nombre": "Agencia", "direccion": "x", "distrito_id": "150115"}):
                            resultado = servicios.cotizar_envio_transportista(
                                "usuario-1", "t1", "s1", "150101", "ag1"
                            )
        self.assertFalse(resultado["ok"])
        self.assertIn("no corresponde", resultado["mensaje"])

    def test_cobertura_directa_acepta_agencia_del_mismo_distrito(self):
        """Cobertura directa acepta una agencia del mismo distrito."""
        base = _base_patches()
        with patch.object(servicios, "_obtener_datos_carrito_entrega", return_value=base["_obtener_datos_carrito_entrega"]):
            with patch.object(servicios, "obtener_transportista_activo", return_value=base["obtener_transportista_activo"]):
                with patch.object(servicios, "obtener_servicio_transportista_activo", return_value=base["obtener_servicio_transportista_activo"]):
                    with patch.object(servicios, "obtener_cobertura_servicio_distrito", return_value={"tipo_cobertura": "DIRECTA"}):
                        with patch.object(servicios, "obtener_sucursal_destino_activa", return_value={"id": "ag1", "nombre": "Agencia", "direccion": "x", "distrito_id": "150101"}):
                            with patch.object(servicios, "obtener_tarifario_activo_transportista", return_value=base["obtener_tarifario_activo_transportista"]):
                                with patch.object(servicios, "obtener_regla_tarifa_transportista", return_value=base["obtener_regla_tarifa_transportista"]):
                                    with patch.object(servicios, "obtener_rango_tarifa_por_peso", return_value=base["obtener_rango_tarifa_por_peso"]):
                                        resultado = servicios.cotizar_envio_transportista(
                                            "usuario-1", "t1", "s1", "150101", "ag1"
                                        )
        self.assertTrue(resultado["ok"])

    def test_peso_excedido_rechaza_la_cotizacion(self):
        """Un peso por encima del máximo rechaza la cotización."""
        base = _base_patches()
        base["_obtener_datos_carrito_entrega"] = {"ok": True, "peso_gramos": 25000}
        with patch.object(servicios, "_obtener_datos_carrito_entrega", return_value=base["_obtener_datos_carrito_entrega"]):
            with patch.object(servicios, "obtener_transportista_activo", return_value=base["obtener_transportista_activo"]):
                with patch.object(servicios, "obtener_servicio_transportista_activo", return_value=base["obtener_servicio_transportista_activo"]):
                    with patch.object(servicios, "obtener_cobertura_servicio_distrito", return_value={"tipo_cobertura": "AGENCIA_CERCANA"}):
                        with patch.object(servicios, "obtener_sucursal_destino_activa", return_value={"id": "ag1", "nombre": "Agencia", "direccion": "x", "distrito_id": "150115"}):
                            with patch.object(servicios, "obtener_tarifario_activo_transportista", return_value=base["obtener_tarifario_activo_transportista"]):
                                with patch.object(servicios, "obtener_regla_tarifa_transportista", return_value=base["obtener_regla_tarifa_transportista"]):
                                    resultado = servicios.cotizar_envio_transportista(
                                        "usuario-1", "t1", "s1", "150101", "ag1"
                                    )
        self.assertFalse(resultado["ok"])
        self.assertIn("peso", resultado["mensaje"])


class AgenciasPorCoberturaTest(unittest.TestCase):
    """
    Verifica el filtrado de agencias compatibles según la
    cobertura del servicio.
    """

    def test_agencia_cercana_lista_todas_las_agencias(self):
        """Con agencia cercana se listan todas las agencias activas."""
        with patch.object(servicios, "obtener_transportista_activo", return_value={"id": "t1", "nombre": "Shalom"}):
            with patch.object(servicios, "obtener_servicio_transportista_activo", return_value={"id": "s1"}):
                with patch.object(servicios, "obtener_cobertura_servicio_distrito", return_value={"tipo_cobertura": "AGENCIA_CERCANA"}):
                    with patch.object(servicios, "listar_sucursales_destino_activas", return_value=[{"id": "ag1"}, {"id": "ag2"}]) as listar:
                        resultado = servicios.obtener_agencias_destino_checkout("t1", "150101", "s1")
        self.assertTrue(resultado["ok"])
        self.assertEqual(len(resultado["sucursales"]), 2)
        listar.assert_called_once_with("t1", None)

    def test_directa_filtra_agencias_por_distrito(self):
        """Con cobertura directa solo se listan agencias del distrito."""
        with patch.object(servicios, "obtener_transportista_activo", return_value={"id": "t1", "nombre": "Shalom"}):
            with patch.object(servicios, "obtener_servicio_transportista_activo", return_value={"id": "s1"}):
                with patch.object(servicios, "obtener_cobertura_servicio_distrito", return_value={"tipo_cobertura": "DIRECTA"}):
                    with patch.object(servicios, "listar_sucursales_destino_activas", return_value=[{"id": "ag1"}]) as listar:
                        resultado = servicios.obtener_agencias_destino_checkout(
                            "t1", "150101", "s1"
                        )
        self.assertTrue(resultado["ok"])
        listar.assert_called_once_with("t1", "150101")

    def test_sin_cobertura_devuelve_error(self):
        """Un distrito sin cobertura devuelve error."""
        with patch.object(servicios, "obtener_transportista_activo", return_value={"id": "t1"}):
            with patch.object(servicios, "obtener_servicio_transportista_activo", return_value={"id": "s1"}):
                with patch.object(servicios, "obtener_cobertura_servicio_distrito", return_value=None):
                    resultado = servicios.obtener_agencias_destino_checkout(
                        "t1", "150999", "s1"
                    )
        self.assertFalse(resultado["ok"])


class ListadoCoberturasTest(unittest.TestCase):
    """
    Verifica que el listado de coberturas agregue el nombre
    del distrito para mostrarlo al cliente.
    """

    def test_agrega_nombre_de_distrito(self):
        """Agrega el nombre legible del distrito a cada cobertura."""
        with patch.object(servicios, "obtener_servicio_transportista_activo", return_value={"id": "s1", "codigo": "AGENCIA_AGENCIA", "nombre": "Agencia a agencia", "modalidad": "AGENCIA_AGENCIA"}):
            with patch.object(servicios, "listar_coberturas_servicio", return_value=[{"distrito_id": "150101", "tipo_cobertura": "AGENCIA_CERCANA"}]):
                with patch("app.identidad.repositories.buscar_distritos_activos", return_value=[{"id": "150101", "nombre": "Lima", "provincia_nombre": "Lima", "departamento_nombre": "Lima"}]):
                    resultado = servicios.obtener_coberturas_checkout("t1", "s1")
        self.assertTrue(resultado["ok"])
        self.assertEqual(len(resultado["coberturas"]), 1)
        cobertura = resultado["coberturas"][0]
        self.assertEqual(cobertura["distrito_id"], "150101")
        self.assertEqual(cobertura["distrito_nombre"], "Lima")


class RutasCoberturasTest(unittest.TestCase):
    """
    Verifica el enrutado HTTP de las APIs de coberturas y
    agencias compatibles.
    """

    def setUp(self):
        from app import create_app

        self.app = create_app()
        self.app.config.update(TESTING=True)

    def _cliente(self):
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update(
                {
                    "autenticado": True,
                    "usuario_id": "actor-prueba",
                    "correo": "actor@example.test",
                    "roles": ["CLIENTE"],
                }
            )
        return cliente

    def test_coberturas_responde_ok(self):
        """GET de coberturas responde 200 con ok verdadero."""
        with patch("app.operaciones.routes.obtener_coberturas_checkout", return_value={"ok": True, "coberturas": [{"distrito_id": "150101", "distrito_nombre": "Lima"}]}):
            respuesta = self._cliente().get(
                "/operaciones/api/transportistas/t1/servicios/s1/coberturas"
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.get_json()["ok"])

    def test_agencias_recibe_servicio_y_distrito(self):
        """GET de agencias propaga servicio y distrito al servicio."""
        capturado = {}

        def falso(**kwargs):
            capturado.update(kwargs)
            return {"ok": True, "sucursales": []}

        with patch("app.operaciones.routes.obtener_agencias_destino_checkout", side_effect=falso):
            respuesta = self._cliente().get(
                "/operaciones/api/transportistas/t1/agencias?servicio_id=s1&distrito_id=150101"
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(capturado.get("servicio_transportista_id"), "s1")
        self.assertEqual(capturado.get("distrito_id"), "150101")


class ContratoFrontendCoberturasTest(unittest.TestCase):
    """
    Verifica que el frontend del checkout use el distrito de
    cobertura (distrito del cliente) y no el distrito físico
    de la agencia.
    """

    def _leer(self, ruta):
        import os

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base, ruta), encoding="utf-8") as archivo:
            return archivo.read()

    def test_checkout_tiene_selector_de_distrito_de_destino(self):
        """El checkout incluye el selector de distrito de destino."""
        html = self._leer("templates/cliente/checkout.html")
        self.assertIn('id="checkout-carrier-district"', html)
        self.assertIn('id="checkout-carrier-district-group"', html)

    def test_js_consulta_coberturas_del_servicio(self):
        """El JS del checkout consulta el endpoint de coberturas."""
        js = self._leer("static/js/modules/checkout.js")
        self.assertIn("/coberturas", js)

    def test_js_usa_distrito_de_cobertura_para_cotizar(self):
        """El JS usa el distrito de cobertura al cotizar el envío."""
        js = self._leer("static/js/modules/checkout.js")
        self.assertIn("carrierDistrictSelect", js)


if __name__ == "__main__":
    unittest.main()
