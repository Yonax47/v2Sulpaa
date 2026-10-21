# -*- coding: utf-8 -*-
"""Contrato del checkout entre la interfaz y Operaciones."""
from __future__ import unicode_literals

import unittest
from pathlib import Path
from unittest.mock import patch

from app.operaciones import services


CHECKOUT_JS = Path(__file__).resolve().parents[1] / "static" / "js" / "modules" / "checkout.js"
CHECKOUT_HTML = Path(__file__).resolve().parents[1] / "templates" / "cliente" / "checkout.html"


def _function_source(source, name):
    """Extrae una funcion JS para comprobar su contrato sin ejecutar un navegador."""
    start = source.index("function " + name + "(")
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
            continue
        if source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError("No se pudo extraer la funcion %s." % name)


class MatrizMetodosPagoCheckoutTest(unittest.TestCase):
    def setUp(self):
        self.metodos = [
            {"id": 1, "codigo": "EFECTIVO", "nombre": "Efectivo", "tipo_confirmacion": "MANUAL"},
            {"id": 2, "codigo": "YAPE", "nombre": "Yape", "tipo_confirmacion": "MANUAL"},
            {"id": 3, "codigo": "PLIN", "nombre": "Plin", "tipo_confirmacion": "MANUAL"},
            {"id": 4, "codigo": "TRANSFERENCIA", "nombre": "Transferencia", "tipo_confirmacion": "MANUAL"},
        ]

    def _matriz(self, tipo_entrega):
        with patch.object(
            services, "listar_metodos_pago_activos", return_value=self.metodos
        ):
            resultado = services.obtener_metodos_pago_checkout(tipo_entrega)
        self.assertTrue(resultado["ok"])
        return {
            metodo["codigo"]: metodo["modalidad"]
            for metodo in resultado["metodos_pago"]
        }

    def test_recojo_local_admite_pago_local_y_anticipados(self):
        self.assertEqual(
            self._matriz("RECOJO_LOCAL"),
            {
                "EFECTIVO": "PAGO_EN_LOCAL",
                "YAPE": "ANTICIPADO",
                "PLIN": "ANTICIPADO",
                "TRANSFERENCIA": "ANTICIPADO",
            },
        )

    def test_delivery_local_admite_contra_entrega_y_anticipados(self):
        self.assertEqual(
            self._matriz("DELIVERY_LOCAL"),
            {
                "EFECTIVO": "CONTRA_ENTREGA",
                "YAPE": "ANTICIPADO",
                "PLIN": "ANTICIPADO",
                "TRANSFERENCIA": "ANTICIPADO",
            },
        )

    def test_transportista_solo_admite_pagos_anticipados(self):
        self.assertEqual(
            self._matriz("TRANSPORTISTA"),
            {
                "YAPE": "ANTICIPADO",
                "PLIN": "ANTICIPADO",
                "TRANSFERENCIA": "ANTICIPADO",
            },
        )


class ContratoEntregaBackendTest(unittest.TestCase):
    def test_recojo_local_exige_y_conserva_el_punto(self):
        punto = {"id": "punto-1", "direccion": "Local SULPAA"}
        with patch.object(
            services, "listar_puntos_recojo_activos", return_value=[punto]
        ):
            entrega = services._preparar_entrega_checkout(
                "usuario-1",
                {"tipo_entrega": "RECOJO_LOCAL", "punto_recojo_id": "punto-1"},
            )
        self.assertEqual(entrega["punto_recojo"], punto)

    def test_delivery_local_conserva_destino_y_cotizacion(self):
        destino = {
            "distrito_id": "120114",
            "direccion": "Av. Prueba 123",
            "referencia": None,
            "latitud": "-12.0",
            "longitud": "-75.0",
        }
        cotizacion = {"ok": True, "tipo": "DELIVERY_LOCAL", "costo_entrega": 5}
        cliente = {
            "cliente": {
                "nombres": "Ana",
                "apellido_paterno": "Perez",
                "apellido_materno": "",
                "telefono": "999999999",
            }
        }
        with patch(
            "app.identidad.repositories.obtener_datos_checkout_usuario",
            return_value=cliente,
        ):
            with patch.object(
                services, "cotizar_delivery_local", return_value=cotizacion
            ):
                with patch.object(
                    services, "_destino_checkout_opcional", return_value=destino
                ):
                    entrega = services._preparar_entrega_checkout(
                        "usuario-1",
                        {"tipo_entrega": "DELIVERY_LOCAL", "distancia_km": "2.5"},
                    )
        self.assertEqual(entrega["destino"], destino)
        self.assertEqual(entrega["direccion_entrega"], destino["direccion"])

    def test_transportista_agencia_exige_sucursal(self):
        servicio = {"id": "servicio-1", "modalidad": "AGENCIA_AGENCIA"}
        cotizacion = {"ok": True, "sucursal_destino": {"direccion": "Agencia Uno"}}
        with patch(
            "app.identidad.repositories.obtener_datos_checkout_usuario",
            return_value={},
        ):
            with patch.object(
                services, "obtener_servicio_transportista_activo", return_value=servicio
            ):
                with patch.object(
                    services, "cotizar_envio_transportista", return_value=cotizacion
                ) as cotizar:
                    entrega = services._preparar_entrega_checkout(
                        "usuario-1",
                        {
                            "tipo_entrega": "TRANSPORTISTA",
                            "transportista_id": "transportista-1",
                            "servicio_transportista_id": "servicio-1",
                            "sucursal_destino_id": "agencia-1",
                            "distrito_destino_id": "120114",
                        },
                    )
        cotizar.assert_called_once_with(
            "usuario-1", "transportista-1", "servicio-1", "120114", "agencia-1"
        )
        self.assertEqual(entrega["direccion_entrega"], "Agencia Uno")

    def test_transportista_domicilio_usa_direccion_sin_agencia(self):
        servicio = {"id": "servicio-1", "modalidad": "AGENCIA_DOMICILIO"}
        destino = {
            "distrito_id": "120114",
            "direccion": "Av. Prueba 123",
            "referencia": "Puerta azul",
            "latitud": None,
            "longitud": None,
        }
        cotizacion = {"ok": True, "sucursal_destino": None}
        with patch(
            "app.identidad.repositories.obtener_datos_checkout_usuario",
            return_value={},
        ):
            with patch.object(
                services, "obtener_servicio_transportista_activo", return_value=servicio
            ):
                with patch.object(
                    services, "_destino_checkout", return_value=destino
                ):
                    with patch.object(
                        services, "cotizar_envio_transportista", return_value=cotizacion
                    ) as cotizar:
                        entrega = services._preparar_entrega_checkout(
                            "usuario-1",
                            {
                                "tipo_entrega": "TRANSPORTISTA",
                                "transportista_id": "transportista-1",
                                "servicio_transportista_id": "servicio-1",
                            },
                        )
        cotizar.assert_called_once_with(
            "usuario-1", "transportista-1", "servicio-1", "120114", None
        )
        self.assertEqual(
            entrega["direccion_entrega"], "Av. Prueba 123 | Ref: Puerta azul"
        )


class ContratoFrontendCheckoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CHECKOUT_JS.read_text(encoding="utf-8")

    def test_payload_recojo_envia_punto_seleccionado(self):
        payload = _function_source(self.source, "buildCheckoutPayload")
        self.assertIn("punto_recojo_id: selectedPickupId", payload)

    def test_transportista_distingue_agencia_y_domicilio(self):
        payload = _function_source(self.source, "buildCheckoutPayload")
        self.assertIn("carrierServiceRequiresAgency()", payload)
        self.assertIn("carrierDestinationIsReady()", payload)

    def test_direccion_guardada_esta_conectada_al_selector(self):
        self.assertRegex(
            self.source,
            r"savedSelector\.addEventListener\(\s*[\"']change[\"']",
        )

    def test_boton_cotizar_transportista_tiene_evento(self):
        self.assertIn("checkout-quote-carrier", self.source)
        self.assertRegex(
            self.source,
            r"carrierQuoteButton\.addEventListener\(\s*[\"']click[\"']",
        )

    def test_boton_confirmar_valida_recojo_y_modalidad_transportista(self):
        ready = _function_source(self.source, "updateConfirmOrderButton")
        self.assertIn("selectedPickupId", ready)
        self.assertIn("carrierServiceRequiresAgency()", ready)
        self.assertIn("carrierDestinationIsReady()", ready)

    def test_delivery_local_envia_destino_y_cotizacion(self):
        payload = _function_source(self.source, "buildCheckoutPayload")
        self.assertIn("...destinationPayload()", payload)
        self.assertIn("distancia_km: deliveryQuote.distancia_km", payload)
        self.assertIn("cotizacion_token: deliveryQuote.cotizacion_token", payload)

    def test_punto_de_recojo_muestra_referencia(self):
        render = _function_source(self.source, "renderPickupLocations")
        self.assertIn("location.referencia", render)
        self.assertIn("Referencia:", render)

    def test_agencia_seleccionada_actualiza_el_resumen(self):
        self.assertIn("function updateCarrierAgencySummary(", self.source)
        self.assertIn("option.dataset.name = agency.nombre", self.source)
        refresh = _function_source(self.source, "refreshAddressMode")
        self.assertIn("updateCarrierAgencySummary()", refresh)


class ContratoOrdenCheckoutTest(unittest.TestCase):
    """Comprueba que el checkout pide primero la modalidad y luego el destino."""

    @classmethod
    def setUpClass(cls):
        cls.html = CHECKOUT_HTML.read_text(encoding="utf-8")

    def _posicion(self, fragmento):
        indice = self.html.find(fragmento)
        self.assertNotEqual(indice, -1, "No se encontró en el checkout: " + fragmento)
        return indice

    def test_modalidad_va_antes_que_el_destino(self):
        modalidad = self._posicion('id="checkout-delivery-section"')
        destino = self._posicion('id="checkout-destination-section"')
        self.assertLess(modalidad, destino)

    def test_opciones_de_modalidad_antes_del_formulario_de_direccion(self):
        opciones = self._posicion('id="checkout-delivery-options"')
        destino = self._posicion('id="checkout-destination-summary"')
        formulario = self._posicion('id="checkout-address-form"')
        self.assertLess(opciones, destino)
        self.assertLess(destino, formulario)

    def test_paneles_de_entrega_dentro_del_paso_destino(self):
        inicio = self._posicion('id="checkout-destination-section"')
        comprobante = self._posicion("04. COMPROBANTE")
        for panel in (
            'id="checkout-pickup-panel"',
            'id="checkout-local-delivery-panel"',
            'id="checkout-carrier-panel"',
        ):
            posicion = self._posicion(panel)
            self.assertGreater(posicion, inicio)
            self.assertLess(posicion, comprobante)

    def test_resumen_de_destino_visible(self):
        self._posicion('id="checkout-destination-summary"')
        self.assertIn("checkout-destination", self.html)

    def test_resumen_de_agencia_presente_en_panel_transportista(self):
        inicio = self._posicion('id="checkout-carrier-panel"')
        resumen = self._posicion('id="checkout-carrier-agency-summary"')
        detalle = self._posicion('id="checkout-carrier-agency-detail"')
        self.assertGreater(resumen, inicio)
        self.assertGreater(detalle, inicio)


if __name__ == "__main__":
    unittest.main()
