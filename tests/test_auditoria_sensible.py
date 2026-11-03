# -*- coding: utf-8 -*-
"""Pruebas del filtro de auditoría sin abrir conexiones a MySQL."""

import json
import unittest

from app.admin.auditoria.repositories import _serializar


class FiltroAuditoriaSensibleTest(unittest.TestCase):
    """Comprueba que una auditoría nunca conserve secretos recibidos."""

    def test_elimina_credenciales_en_datos_anidados(self):
        datos = {
            "csrf_token": "csrf-no-debe-aparecer",
            "_csrf_token": "csrf-interno-no-debe-aparecer",
            "password": "password-no-debe-aparecer",
            "usuario_password": "password-alterno-no-debe-aparecer",
            "contrasena_actual": "contrasena-no-debe-aparecer",
            "access_token": "acceso-no-debe-aparecer",
            "proveedor_api_key": "api-no-debe-aparecer",
            "private_key": "privada-no-debe-aparecer",
            "private_key_pem": "pem-no-debe-aparecer",
            "config_secret": "secreto-no-debe-aparecer",
            "authorization": "cabecera-no-debe-aparecer",
            "detalle": {
                "refresh-token": "refresh-no-debe-aparecer",
                "cookie": "cookie-no-debe-aparecer",
            },
        }

        serializado = _serializar(datos)
        for secreto in (
            "csrf-no-debe-aparecer",
            "csrf-interno-no-debe-aparecer",
            "password-no-debe-aparecer",
            "password-alterno-no-debe-aparecer",
            "contrasena-no-debe-aparecer",
            "acceso-no-debe-aparecer",
            "api-no-debe-aparecer",
            "privada-no-debe-aparecer",
            "pem-no-debe-aparecer",
            "secreto-no-debe-aparecer",
            "cabecera-no-debe-aparecer",
            "refresh-no-debe-aparecer",
            "cookie-no-debe-aparecer",
        ):
            self.assertNotIn(secreto, serializado)

    def test_conserva_datos_operativos_que_no_son_secretos(self):
        datos = {
            "pedido_id": "PED-100",
            "estado": "CONFIRMADO",
            "codigo_seguimiento": "TRACK-20",
            "metodo_pago": "YAPE",
            "monto": "25.00",
        }

        limpio = json.loads(_serializar(datos))
        self.assertEqual(limpio, datos)


if __name__ == "__main__":
    unittest.main()
