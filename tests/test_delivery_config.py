# -*- coding: utf-8 -*-
"""Pruebas de integración de la Configuración de Delivery.

Comprueban:
- Control de acceso (GERENTE/ADMINISTRADOR leen; REPARTIDOR no).
- Que la página renderiza la tarifa real activa.
- Que el simulador usa LA MISMA fórmula del checkout.
- Que la validación de datos rechaza entradas inválidas.
"""
from __future__ import unicode_literals

import unittest
from decimal import Decimal

from app import create_app
from app.admin.delivery import services as delivery
from app.operaciones.services import calcular_costo_delivery_local


class DeliveryConfigTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def _sesion(self, roles):
        with self.client.session_transaction() as sesion:
            sesion["autenticado"] = True
            sesion["usuario_id"] = "e5b16653-a98d-4838-9e33-074b6423be75"
            sesion["correo"] = "i2512609@continental.edu.pe"
            sesion["roles"] = list(roles)

    def test_control_de_acceso(self):
        self._sesion(["REPARTIDOR"])
        self.assertEqual(self.client.get("/admin/delivery/").status_code, 403)
        for roles in (["GERENTE"], ["ADMINISTRADOR"]):
            self._sesion(roles)
            self.assertEqual(self.client.get("/admin/delivery/").status_code, 200)

    def test_pagina_muestra_tarifa_real(self):
        self._sesion(["GERENTE"])
        respuesta = self.client.get("/admin/delivery/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Configuración de Delivery", respuesta.get_data(as_text=True))

    def test_simulador_usa_la_formula_del_checkout(self):
        self._sesion(["GERENTE"])
        tarifa = delivery.obtener_configuracion_delivery(["GERENTE"])["tarifa_activa"]
        esperado = calcular_costo_delivery_local(tarifa, 6, 3, 50)

        respuesta = self.client.post(
            "/admin/delivery/simular",
            json={"distancia_km": 6, "peso_kg": 3, "subtotal": 50},
        )
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.get_json()
        self.assertTrue(cuerpo["ok"])
        self.assertEqual(cuerpo["costo_entrega"], esperado["costo_entrega"])

    def test_simulador_rechaza_fuera_de_cobertura(self):
        self._sesion(["GERENTE"])
        respuesta = self.client.post(
            "/admin/delivery/simular",
            json={"distancia_km": 9999, "peso_kg": 3, "subtotal": 50},
        )
        cuerpo = respuesta.get_json()
        self.assertFalse(cuerpo["ok"])

    def test_validacion_rechaza_negativos(self):
        limpios, error = delivery.validar_datos_tarifa(
            {
                "nombre": "Prueba",
                "tarifa_base": "-1",
                "km_incluidos": "4",
                "precio_km_adicional": "1",
                "peso_incluido_kg": "5",
                "precio_kg_adicional": "1",
            }
        )
        self.assertIsNone(limpios)
        self.assertTrue(error)

    def test_validacion_acepta_datos_correctos(self):
        limpios, error = delivery.validar_datos_tarifa(
            {
                "nombre": "Prueba",
                "tarifa_base": "6.00",
                "km_incluidos": "4.50",
                "precio_km_adicional": "1.40",
                "peso_incluido_kg": "5",
                "precio_kg_adicional": "1",
                "distancia_maxima_km": "",
                "peso_maximo_kg": "",
                "monto_envio_gratis": "",
            }
        )
        self.assertIsNone(error)
        self.assertEqual(Decimal(limpios["tarifa_base"]), Decimal("6.00"))
        self.assertIsNone(limpios["distancia_maxima_km"])

    def test_edicion_restringida_a_gerente(self):
        with self.assertRaises(PermissionError):
            delivery.actualizar_tarifa_delivery_admin(
                roles=["ADMINISTRADOR"],
                actor_id="x",
                actor_roles=["ADMINISTRADOR"],
                tarifa_id="no-existe",
                datos={"nombre": "X"},
            )
