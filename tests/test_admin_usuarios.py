# -*- coding: utf-8 -*-
"""Pruebas de integración del módulo administrativo de Usuarios y Roles.

Comprueban:
- Control de acceso real (solo GERENTE/ADMINISTRADOR).
- Render de listado, formulario y detalle.
- Que crear un usuario GUARDA de verdad usuario + perfil + roles.
- Que nunca se guarda "a medias" (correo duplicado).
- Que cada cambio deja un evento en la auditoría.

Las pruebas crean cuentas de prueba con correo único y las eliminan
en `tearDown`; no tocan datos reales del sistema.
"""
from __future__ import unicode_literals

import uuid
import unittest

from app import create_app
from app.admin.usuarios import services as usuarios
from app.config.database import conexion_identidad, conexion_operaciones


class UsuariosAdminTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.correo_prueba = "prueba.admin.%s@sulpaa.test" % uuid.uuid4().hex[:10]
        self._ids_creados = []

    def tearDown(self):
        self._limpiar()

    def _limpiar(self):
        conexion = conexion_identidad()
        try:
            with conexion.cursor() as cursor:
                for usuario_id in self._ids_creados:
                    cursor.execute(
                        "DELETE FROM usuario_roles WHERE usuario_id = %s",
                        (usuario_id,),
                    )
                    cursor.execute(
                        "DELETE FROM perfiles WHERE usuario_id = %s",
                        (usuario_id,),
                    )
                    cursor.execute(
                        "DELETE FROM usuarios WHERE id = %s",
                        (usuario_id,),
                    )
            conexion.commit()
        finally:
            conexion.close()

        conexion_op = conexion_operaciones()
        try:
            with conexion_op.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM auditoria_operaciones WHERE datos_nuevos LIKE %s",
                    ("%" + self.correo_prueba + "%",),
                )
            conexion_op.commit()
        finally:
            conexion_op.close()

    def _sesion(self, roles):
        with self.client.session_transaction() as sesion:
            sesion["autenticado"] = True
            sesion["usuario_id"] = "e5b16653-a98d-4838-9e33-074b6423be75"
            sesion["correo"] = "e5b16653-a98d-4838-9e33-074b6423be75@continental.edu.pe"
            sesion["roles"] = list(roles)

    def test_anonimo_redirige_al_login(self):
        respuesta = self.client.get("/admin/usuarios/")
        self.assertIn(respuesta.status_code, (302, 401, 403))

    def test_repartidor_no_puede_entrar(self):
        self._sesion(["REPARTIDOR"])
        self.assertEqual(self.client.get("/admin/usuarios/").status_code, 403)

    def test_gerente_y_administrador_entran(self):
        for roles in (["GERENTE"], ["ADMINISTRADOR"]):
            self._sesion(roles)
            self.assertEqual(
                self.client.get("/admin/usuarios/").status_code, 200
            )
            self.assertEqual(
                self.client.get("/admin/usuarios/nuevo").status_code, 200
            )

    def test_crear_usuario_guarda_de_verdad(self):
        roles_actor = ["GERENTE"]
        datos = {
            "correo": self.correo_prueba,
            "password": "ClaveSegura123",
            "nombres": "Prueba",
            "apellido_paterno": "Admin",
            "apellido_materno": "Test",
            "dni": None,
            "telefono": "987654321",
            "roles": ["INVENTARIO"],
        }

        usuario_id = usuarios.crear_usuario_admin(
            roles=roles_actor,
            actor_id="e5b16653-a98d-4838-9e33-074b6423be75",
            actor_roles=roles_actor,
            datos=datos,
        )
        self._ids_creados.append(usuario_id)

        conexion = conexion_identidad()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT id, estado FROM usuarios WHERE correo = %s",
                    (self.correo_prueba,),
                )
                fila = cursor.fetchone()
                self.assertIsNotNone(fila)
                self.assertEqual(fila["estado"], "ACTIVO")

                cursor.execute(
                    "SELECT COUNT(*) AS total FROM perfiles WHERE usuario_id = %s",
                    (usuario_id,),
                )
                self.assertEqual(cursor.fetchone()["total"], 1)

                cursor.execute(
                    """
                    SELECT r.codigo
                    FROM usuario_roles ur
                    JOIN roles r ON r.id = ur.rol_id
                    WHERE ur.usuario_id = %s AND ur.estado = 'ACTIVO'
                    """,
                    (usuario_id,),
                )
                codigos = [f["codigo"] for f in cursor.fetchall()]
                self.assertEqual(codigos, ["INVENTARIO"])
        finally:
            conexion.close()

    def test_correo_duplicado_no_crea_nada(self):
        roles_actor = ["GERENTE"]
        datos = {
            "correo": self.correo_prueba,
            "password": "ClaveSegura123",
            "nombres": "Prueba",
            "apellido_paterno": "Admin",
            "telefono": "987654321",
            "roles": [],
        }
        usuario_id = usuarios.crear_usuario_admin(
            roles=roles_actor,
            actor_id="e5b16653-a98d-4838-9e33-074b6423be75",
            actor_roles=roles_actor,
            datos=datos,
        )
        self._ids_creados.append(usuario_id)

        with self.assertRaises(usuarios.ErrorUsuarios):
            usuarios.crear_usuario_admin(
                roles=roles_actor,
                actor_id="e5b16653-a98d-4838-9e33-074b6423be75",
                actor_roles=roles_actor,
                datos=dict(datos),
            )

        conexion = conexion_identidad()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM usuarios WHERE correo = %s",
                    (self.correo_prueba,),
                )
                self.assertEqual(cursor.fetchone()["total"], 1)
        finally:
            conexion.close()

    def test_creacion_deja_evento_de_auditoria(self):
        roles_actor = ["GERENTE"]
        usuario_id = usuarios.crear_usuario_admin(
            roles=roles_actor,
            actor_id="e5b16653-a98d-4838-9e33-074b6423be75",
            actor_roles=roles_actor,
            datos={
                "correo": self.correo_prueba,
                "password": "ClaveSegura123",
                "nombres": "Prueba",
                "apellido_paterno": "Admin",
                "telefono": "987654321",
                "roles": ["INVENTARIO"],
            },
        )
        self._ids_creados.append(usuario_id)

        conexion = conexion_operaciones()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM auditoria_operaciones
                    WHERE modulo = 'USUARIOS'
                      AND accion = 'CREAR_USUARIO'
                      AND datos_nuevos LIKE %s
                    """,
                    ("%" + self.correo_prueba + "%",),
                )
                self.assertGreaterEqual(cursor.fetchone()["total"], 1)
        finally:
            conexion.close()


if __name__ == "__main__":
    unittest.main()
