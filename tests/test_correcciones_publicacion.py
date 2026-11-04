"""Regresiones aisladas: sin conexiones ni escrituras productivas."""

import hashlib
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from flask import render_template, url_for

from app import create_app
from app.admin.caja import repositories as caja_repo, services as caja
from app.admin.contenido import repositories as contenido_repo, services as contenido
from app.admin.inventario import repositories as inventario_repo, services as inventario
from app.comercio.visibilidad import (
    VARIANTES_PAUSADAS, VARIANTES_PAUSADAS_POR_SABOR, filtrar_presentacion_tienda,
)
from app.encuestas import repositories as encuestas_repo, services as encuestas
from app.shared.pagination import crear_paginacion


class PublicacionTest(unittest.TestCase):
    def test_hash_css_js_no_imagenes(self):
        app = create_app()
        with app.test_request_context('/'):
            for nombre in ('css/components.css', 'js/main.js'):
                version = hashlib.sha256((Path(app.static_folder) / nombre).read_bytes()).hexdigest()[:12]
                self.assertIn('v=' + version, url_for('static', filename=nombre))
            self.assertNotIn('?v=', url_for('static', filename='img/logo.png'))

    def test_filtro_exacto_sin_imagen_y_sin_mutar_datos(self):
        filas = [{'variante_id': id_, 'precio': 10, 'stock': 99} for id_ in VARIANTES_PAUSADAS]
        habituales = [{'variante_id': 'habitual-' + sabor, 'imagen': None} for sabor in ('Café', 'Kion', 'Flor de Jamaica', 'Limón')]
        datos = {'catalogo': filas + habituales, 'variantes_330': filas + habituales,
                 'packs_personalizados': [{'variantes_permitidas': filas + habituales}], 'packs_fijos': []}
        resultado = filtrar_presentacion_tienda(datos)
        self.assertEqual(len(VARIANTES_PAUSADAS), 40)
        self.assertEqual(len(VARIANTES_PAUSADAS_POR_SABOR), 8)
        self.assertEqual(resultado['catalogo'], habituales)
        self.assertEqual(resultado['variantes_330'], habituales)
        self.assertEqual(resultado['packs_personalizados'][0]['variantes_permitidas'], habituales)
        self.assertEqual(len(datos['catalogo']), 44)
        self.assertEqual(filas[0]['stock'], 99)

    def test_caja_normaliza_ultima_pagina_y_conserva_filtros(self):
        with patch.object(caja_repo, 'contar_movimientos', return_value=51) as count, \
             patch.object(caja_repo, 'listar_movimientos', return_value=[]) as listar:
            resultado = caja.listar_movimientos({'tipo': 'EGRESO', 'desde': '2026-01-01'}, 999, 25)
        self.assertEqual(resultado['paginacion']['pagina'], 3)
        self.assertEqual(listar.call_args.kwargs['offset'], 50)
        self.assertEqual(count.call_args.kwargs['tipo'], 'EGRESO')
        self.assertEqual(listar.call_args.kwargs['desde'], '2026-01-01')

    def test_contenido_permiso_antes_de_consultar(self):
        with patch.object(contenido_repo, 'contar_contenidos') as count:
            with self.assertRaises(contenido.ErrorContenido):
                contenido.listar_para_admin(['CLIENTE'], pagina=1)
        count.assert_not_called()

    def test_encuestas_normaliza_pagina_y_conserva_filtros(self):
        with patch.object(encuestas_repo, 'contar_encuestas', return_value=61) as count, \
             patch.object(encuestas_repo, 'listar_encuestas', return_value=[]) as listar:
            resultado = encuestas.listar_encuestas(
                {'estado': 'RESPONDIDA', 'desde': '2026-01-01'}, 999, 25
            )
        self.assertEqual(resultado['paginacion']['pagina'], 3)
        self.assertEqual(resultado['paginacion']['offset'], 50)
        self.assertEqual(resultado['paginacion']['filtros']['estado'], 'RESPONDIDA')
        self.assertEqual(count.call_args.kwargs['estado'], 'RESPONDIDA')
        self.assertEqual(listar.call_args.kwargs['limite'], 25)
        self.assertEqual(listar.call_args.kwargs['offset'], 50)

    def test_historiales_independientes(self):
        with patch.object(inventario, 'obtener_existencia_detalle', return_value={'id': 'fixture'}), \
             patch.object(inventario, 'listar_motivos_activos', return_value=[]), \
             patch.object(inventario, 'contar_historial_existencia', return_value=60), \
             patch.object(inventario, 'listar_movimientos', return_value=[]) as mov, \
             patch.object(inventario, 'listar_verificaciones', return_value=[]) as ver:
            resultado = inventario.obtener_detalle_existencia(['GERENTE'], 'fixture', 2, 3, 25)
        self.assertEqual(resultado['paginacion_movimientos']['pagina'], 2)
        mov.assert_called_once_with('fixture', limite=25, offset=25)
        self.assertEqual(ver.call_args_list, [call('fixture', limite=25, offset=50), call('fixture', limite=5)])

    def test_enlaces_historial_conservan_otro_historial(self):
        app = create_app()
        p = crear_paginacion(80, 2, 25, endpoint='admin_inventario.detalle',
                            filtros={'existencia_id': 'fixture', 'ver_page': 3})
        p['parametro'] = 'mov_page'
        with app.test_request_context('/'):
            html = render_template('admin/components/pagination.html', paginacion=p)
        self.assertIn('mov_page=1', html)
        self.assertIn('mov_page=3', html)
        self.assertIn('ver_page=3', html)
        self.assertNotIn('?page=', html)

    def test_sql_limite_offset_parametrizados(self):
        for modulo, funcion, args in (
            (caja_repo, 'listar_movimientos', {}),
            (contenido_repo, 'listar_contenidos', {'estado': 'PUBLICADO'}),
            (inventario_repo, 'listar_movimientos', {'existencia_id': 'fixture'}),
            (inventario_repo, 'listar_verificaciones', {'existencia_id': 'fixture'}),
        ):
            with self.subTest(funcion=modulo.__name__ + '.' + funcion):
                conexion = MagicMock()
                cursor = conexion.cursor.return_value.__enter__.return_value
                cursor.fetchall.return_value = []
                conector = 'conexion_operaciones' if modulo is caja_repo else ('conexion_comercio' if modulo is contenido_repo else 'conexion_inventario')
                with patch.object(modulo, conector, return_value=conexion):
                    getattr(modulo, funcion)(**args, limite=10, offset=20)
                sql, params = cursor.execute.call_args.args
                self.assertIn('LIMIT %s OFFSET %s', sql)
                self.assertEqual(tuple(params[-2:]), (10, 20))

    def test_listados_rechazan_cliente(self):
        app = create_app()
        app.config.update(TESTING=True, OMITIR_SEGURIDAD_EN_PRUEBAS=True)
        client = app.test_client()
        with client.session_transaction() as sesion:
            sesion['usuario_id'] = 'fixture'
            sesion['autenticado'] = True
            sesion['roles'] = ['CLIENTE']
        for ruta in ('/admin/caja/', '/admin/contenido/', '/admin/entregas/repartidores', '/admin/inventario/fixture'):
            self.assertEqual(client.get(ruta).status_code, 403)


if __name__ == '__main__':
    unittest.main()
