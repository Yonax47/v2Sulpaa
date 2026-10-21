# -*- coding: utf-8 -*-
"""Pruebas de integración del módulo administrativo de Auditoría.

Comprueban:
- Que la auditoría solo es accesible al rol GERENTE.
- Que ``registrar_evento`` deja un rastro real y legible.
- Que el listado y el detalle renderizan.
"""
from __future__ import unicode_literals

import uuid
import unittest

from app import create_app
from app.admin.auditoria import services as auditoria
from app.config.database import conexion_operaciones


class AuditoriaAdminTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.marca = "prueba.auditoria.%s" % uuid.uuid4().hex[:10]

    def tearDown(self):
        conexion = conexion_operaciones()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM auditoria_operaciones WHERE datos_nuevos LIKE %s",
                    ("%" + self.marca + "%",),
                )
            conexion.commit()
        finally:
            conexion.close()

    def _sesion(self, roles):
        with self.client.session_transaction() as sesion:
            sesion["autenticado"] = True
            sesion["usuario_id"] = "e5b16653-a98d-4838-9e33-074b6423be75"
            sesion["correo"] = "e5b16653-a98d-4838-9e33-074b6423be75@continental.edu.pe"
            sesion["roles"] = list(roles)

    def test_solo_gerente_ve_auditoria(self):
        self._sesion(["GERENTE"])
        self.assertEqual(self.client.get("/admin/auditoria/").status_code, 200)

        self._sesion(["ADMINISTRADOR"])
        self.assertEqual(self.client.get("/admin/auditoria/").status_code, 403)

        self._sesion(["REPARTIDOR"])
        self.assertEqual(self.client.get("/admin/auditoria/").status_code, 403)

    def test_servicio_rechaza_no_gerente(self):
        with self.assertRaises(PermissionError):
            auditoria.listar_eventos_admin(["ADMINISTRADOR"])

    def test_registrar_evento_crea_fila(self):
        ok = auditoria.registrar_evento(
            usuario_id="e5b16653-a98d-4838-9e33-074b6423be75",
            modulo="PRUEBA",
            entidad="evento",
            accion="CREAR",
            rol_actual=["GERENTE"],
            entidad_id=None,
            tipo_operacion="CREAR",
            resultado="EXITO",
            detalle="Evento %s creado." % self.marca,
        )
        self.assertTrue(ok)

        conexion = conexion_operaciones()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM auditoria_operaciones
                    WHERE modulo = 'PRUEBA' AND datos_nuevos LIKE %s
                    """,
                    ("%" + self.marca + "%",),
                )
                self.assertEqual(cursor.fetchone()["total"], 1)
        finally:
            conexion.close()

    def test_listar_eventos_devuelve_el_evento(self):
        auditoria.registrar_evento(
            usuario_id="e5b16653-a98d-4838-9e33-074b6423be75",
            modulo="PRUEBA",
            entidad="evento",
            accion="CREAR",
            rol_actual=["GERENTE"],
            entidad_id=None,
            tipo_operacion="CREAR",
            resultado="EXITO",
            detalle="Evento %s listado." % self.marca,
        )
        resultado = auditoria.listar_eventos_admin(
            ["GERENTE"],
            filtros={"modulo": "PRUEBA"},
        )
        self.assertTrue(resultado["ok"])
        detalles = [evento["detalle"] for evento in resultado["eventos"]]
        self.assertTrue(any(self.marca in detalle for detalle in detalles))
