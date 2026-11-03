# -*- coding: utf-8 -*-
"""Fase 4.5: constancias PDF bajo demanda, sin bases ni archivos reales."""

import inspect
import unittest
from datetime import datetime
from unittest.mock import patch

from app import create_app
from app.comercio import constancias
from app.comercio.pdf import ADVERTENCIA, generar_pdf_constancia
from app.identidad import repositories as identidad_repositories


USUARIO_ID = "usuario-propio"
PEDIDO_ID = "pedido-propio"


def pedido_base():
    return {
        "id": PEDIDO_ID,
        "numero_pedido": "PED-20261103-ÁRBOL",
        "subtotal": 31.5,
        "descuento_total": 1.5,
        "costo_entrega": 5,
        "total": 35,
        "moneda": "PEN",
        "estado": "CONFIRMADO",
        "creado_en": datetime(2026, 11, 3, 14, 30),
    }


def detalles_varios():
    return [
        {
            "pedido_detalle_id": "d1",
            "nombre_articulo": "Kombucha de maracuyá",
            "cantidad": 2,
            "precio_unitario": 10.5,
            "descuento_unitario": 0,
            "subtotal_linea": 21,
        },
        {
            "pedido_detalle_id": "d2",
            "nombre_articulo": "Té de piña y kión",
            "cantidad": 1,
            "precio_unitario": 10.5,
            "descuento_unitario": 0,
            "subtotal_linea": 10.5,
        },
    ]


class DatosConstanciaTest(unittest.TestCase):
    def _obtener(self, *, pedido=None, detalles=None, pago=None, entrega=None):
        with patch.object(
            constancias, "obtener_pedido_usuario",
            return_value=pedido_base() if pedido is None else pedido,
        ) as propiedad, patch.object(
            constancias, "obtener_detalles_pedido",
            return_value=detalles_varios() if detalles is None else detalles,
        ), patch.object(
            constancias, "obtener_pago_pedido", return_value=pago,
        ), patch.object(
            constancias, "obtener_entrega_pedido", return_value=entrega,
        ), patch.object(
            constancias, "obtener_nombre_cliente_constancia",
            return_value="José Muñoz Peña",
        ):
            resultado = constancias.obtener_datos_constancia(
                USUARIO_ID, PEDIDO_ID
            )
        propiedad.assert_called_once_with(
            usuario_id=USUARIO_ID, pedido_id=PEDIDO_ID
        )
        return resultado

    def test_pedido_propio_con_varios_productos_y_totales_backend(self):
        resultado = self._obtener(pago={
            "metodo_nombre": "Yape", "modalidad": "PAGO_PREVIO"
        })
        self.assertEqual(len(resultado["productos"]), 2)
        self.assertEqual(resultado["productos"][0]["subtotal"], 21)
        self.assertEqual(resultado["subtotal"], 31.5)
        self.assertEqual(resultado["descuento"], 1.5)
        self.assertEqual(resultado["total"], 35)
        self.assertEqual(resultado["cliente"], "José Muñoz Peña")

    def test_pedido_ajeno_o_inexistente_no_filtra_datos(self):
        for pedido in (None, False):
            with self.subTest(pedido=pedido), patch.object(
                constancias, "obtener_pedido_usuario", return_value=pedido
            ), patch.object(
                constancias, "obtener_detalles_pedido"
            ) as detalles:
                resultado = constancias.obtener_datos_constancia(
                    USUARIO_ID, "pedido-no-propio"
                )
            self.assertIsNone(resultado)
            detalles.assert_not_called()

    def test_sin_datos_opcionales(self):
        resultado = self._obtener(pago=None, entrega=None)
        self.assertIsNone(resultado["metodo_pago"])
        self.assertIsNone(resultado["entrega"])

    def test_no_proyecta_datos_sensibles_de_pago_o_entrega(self):
        resultado = self._obtener(
            pago={
                "metodo_nombre": "Tarjeta",
                "modalidad": "INMEDIATO",
                "referencia_externa": "referencia-secreta-987",
            },
            entrega={
                "tipo_entrega": "DELIVERY_LOCAL",
                "estado": "PENDIENTE",
                "codigo_cliente_token": "token-entrega-secreto",
                "delivery": {
                    "direccion": "Av. Prueba 123",
                    "referencia": "Portón verde",
                    "telefono_receptor": "999999999",
                    "latitud": -12.1,
                    "longitud": -77.1,
                },
            },
        )
        serializado = repr(resultado)
        for prohibido in (
            "referencia-secreta-987", "token-entrega-secreto",
            "999999999", "-12.1", "-77.1",
        ):
            self.assertNotIn(prohibido, serializado)

    def test_nombre_archivo_es_seguro(self):
        nombre = constancias.nombre_archivo_constancia(
            "PED/../áé 123\r\nmalicioso"
        )
        self.assertEqual(nombre, "constancia-compra-PED-123-malicioso.pdf")
        self.assertNotIn("..", nombre)
        self.assertNotIn("/", nombre)

    def test_consulta_de_nombre_es_parametrizada_y_minima(self):
        fuente = inspect.getsource(
            identidad_repositories.obtener_nombre_cliente_constancia
        )
        self.assertIn("WHERE u.id = %s", fuente)
        self.assertNotIn("p.dni", fuente)
        self.assertNotIn("u.correo", fuente)


class GeneracionPDFTest(unittest.TestCase):
    def _datos(self):
        return {
            "empresa": "Corporación Sulpaa S.A.C.",
            "numero_pedido": "PED-Ñ-001",
            "fecha": datetime(2026, 11, 3, 14, 30),
            "cliente": "José Muñoz Peña",
            "estado": "Confirmado",
            "moneda": "PEN",
            "productos": [
                {
                    "nombre": "Kombucha de maracuyá y piña",
                    "cantidad": 2,
                    "precio_unitario": 10.5,
                    "subtotal": 21,
                },
                {
                    "nombre": "Té de kión",
                    "cantidad": 1,
                    "precio_unitario": 9,
                    "subtotal": 9,
                },
            ],
            "subtotal": 30,
            "descuento": 0,
            "costo_entrega": 5,
            "total": 35,
            "metodo_pago": "Yape",
            "modalidad_pago": "Pago previo",
            "entrega": {
                "tipo": "Recojo local",
                "estado": "Pendiente",
                "destino": "Tienda SULPAA",
                "direccion": "Dirección disponible",
            },
        }

    def test_pdf_valido_unicode_y_varios_productos(self):
        contenido = generar_pdf_constancia(self._datos())
        self.assertTrue(contenido.startswith(b"%PDF-"))
        self.assertGreater(len(contenido), 5000)
        self.assertEqual(
            ADVERTENCIA,
            "Documento informativo. No constituye comprobante de pago "
            "electrónico válido ante SUNAT.",
        )
        self.assertIn("ADVERTENCIA", inspect.getsource(generar_pdf_constancia))

    def test_pdf_no_incluye_campos_sensibles_ajenos_al_contrato(self):
        datos = self._datos()
        datos.update({
            "password": "clave-prohibida",
            "dni": "12345678",
            "token": "token-prohibido",
        })
        contenido = generar_pdf_constancia(datos)
        for prohibido in (b"clave-prohibida", b"12345678", b"token-prohibido"):
            self.assertNotIn(prohibido, contenido)


class RutaConstanciaTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            OMITIR_SEGURIDAD_EN_PRUEBAS=True,
        )
        self.client = self.app.test_client()

    def _sesion(self):
        with self.client.session_transaction() as session:
            session.update({
                "autenticado": True,
                "usuario_id": USUARIO_ID,
                "correo": "cliente@sulpaa.test",
                "roles": ["CLIENTE"],
                "correo_verificado": True,
                "requiere_verificacion_correo": True,
            })

    def test_usuario_sin_sesion_es_redirigido(self):
        respuesta = self.client.get(
            f"/pedidos/{PEDIDO_ID}/constancia.pdf"
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/identidad/login", respuesta.headers["Location"])

    def test_pedido_propio_descarga_pdf_con_cabeceras_privadas(self):
        self._sesion()
        with patch(
            "app.comercio.routes.generar_constancia_compra",
            return_value={
                "contenido": b"%PDF-1.7\ncontenido",
                "nombre_archivo": "constancia-compra-PED-001.pdf",
            },
        ) as generar:
            respuesta = self.client.get(
                f"/pedidos/{PEDIDO_ID}/constancia.pdf"
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.mimetype, "application/pdf")
        self.assertIn("attachment", respuesta.headers["Content-Disposition"])
        self.assertIn(
            "constancia-compra-PED-001.pdf",
            respuesta.headers["Content-Disposition"],
        )
        self.assertEqual(
            respuesta.headers["Cache-Control"], "private, no-store, max-age=0"
        )
        self.assertEqual(respuesta.headers["X-Content-Type-Options"], "nosniff")
        generar.assert_called_once_with(
            usuario_id=USUARIO_ID, pedido_id=PEDIDO_ID
        )

    def test_pedido_ajeno_e_inexistente_responden_404(self):
        self._sesion()
        for pedido_id in ("pedido-ajeno", "pedido-inexistente"):
            with self.subTest(pedido_id=pedido_id), patch(
                "app.comercio.routes.generar_constancia_compra",
                return_value=None,
            ):
                respuesta = self.client.get(
                    f"/pedidos/{pedido_id}/constancia.pdf"
                )
            self.assertEqual(respuesta.status_code, 404)


class IntegracionPlantillasTest(unittest.TestCase):
    def test_botones_presentes_en_las_tres_pantallas(self):
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[1] / "templates" / "cliente"
        for nombre in (
            "confirmacion_pedido.html", "pedidos.html", "detalle_pedido.html"
        ):
            with self.subTest(nombre=nombre):
                texto = (raiz / nombre).read_text(encoding="utf-8")
                self.assertIn("descargar_constancia_pedido", texto)


if __name__ == "__main__":
    unittest.main()
