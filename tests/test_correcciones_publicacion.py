"""Regresiones aisladas: sin conexiones ni escrituras productivas."""

import hashlib
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from flask import render_template, session, url_for

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


class AnaliticaEncuestasTest(unittest.TestCase):
    """La analítica debe cubrir todo el filtro, no solo la página."""

    def test_agregado_usa_todas_las_filas_filtradas(self):
        from decimal import Decimal
        from app.admin.encuestas import services as encuestas_admin

        filas = [
            {'estado': 'RESPONDIDA', 'cantidad': 30, 'respuestas': 30,
             'suma': Decimal('120'), 'recomendarian': 24},
            {'estado': 'ENVIADA', 'cantidad': 15, 'respuestas': 0,
             'suma': Decimal('0'), 'recomendarian': 0},
        ]
        with patch.object(encuestas_admin, 'agregar_del_dominio',
                          return_value=filas) as agregado:
            estadisticas = encuestas_admin.estadisticas_encuestas_filtradas(
                {'estado': '', 'desde': '2026-10-01', 'hasta': '2026-10-31'}
            )
        agregado.assert_called_once_with(
            {'estado': '', 'desde': '2026-10-01', 'hasta': '2026-10-31'}
        )
        self.assertEqual(estadisticas['respuestas'], 30)
        self.assertEqual(estadisticas['promedio'], 4.0)
        self.assertEqual(estadisticas['recomendarian'], 24)
        self.assertEqual(
            {f['estado']: f['cantidad'] for f in estadisticas['por_estado']},
            {'RESPONDIDA': 30, 'ENVIADA': 15},
        )

    def test_repositorio_agrega_sin_limite_de_pagina(self):
        from app.encuestas import repositories as encuestas_repo
        conexion = MagicMock()
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        with patch('app.config.database.conexion_operaciones',
                   return_value=conexion):
            encuestas_repo.agregar_encuestas(
                estado='RESPONDIDA', desde='2026-10-01', hasta='2026-10-31'
            )
        sql, params = cursor.execute.call_args.args
        self.assertIn('GROUP BY e.estado', sql)
        self.assertNotIn('LIMIT', sql)
        self.assertEqual(tuple(params), ('RESPONDIDA', '2026-10-01', '2026-10-31'))


class SidebarPermisosTest(unittest.TestCase):
    """El menú no debe ofrecer enlaces que terminen en 403."""

    def _sidebar(self, roles):
        app = create_app()
        with app.test_request_context('/admin/'):
            session.update({'autenticado': True, 'usuario_id': 'u-1',
                            'roles': roles})
            return render_template(
                'admin/components/sidebar.html', admin_activo=''
            )

    def test_inventario_no_ve_enlace_pedidos(self):
        html = self._sidebar(['INVENTARIO'])
        self.assertNotIn('href="/admin/pedidos/"', html)
        self.assertIn('Pedidos', html)

    def test_logistica_ve_enlace_pedidos(self):
        html = self._sidebar(['PEDIDOS_LOGISTICA'])
        self.assertIn('href="/admin/pedidos/"', html)


class RepartidorHistorialRegresionTest(unittest.TestCase):
    """El historial debe ser consultable, paginado y sin enlaces 404."""

    def test_detalle_acepta_asignaciones_cerradas(self):
        from app.operaciones import repositories as ops_repo
        conexion = MagicMock()
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        with patch.object(
            ops_repo, 'nombre_esquema', return_value='identidad'
        ):
            ops_repo.obtener_detalle_asignacion(
                conexion,
                {'operaciones': 'operaciones', 'comercio': 'comercio',
                 'identidad': 'identidad'},
                'repartidor-1', 'entrega-1',
            )
        sql, params = cursor.execute.call_args.args
        self.assertIn("'FINALIZADA'", sql)
        self.assertIn("'CANCELADA'", sql)
        self.assertEqual(tuple(params), ('repartidor-1', 'entrega-1'))

    def test_historial_pagina_y_entrega_limite_offset(self):
        from app.operaciones import repositories as repos_ops
        from app.operaciones import services as servicios_operaciones

        class UoW:
            conexion = object()
            esquemas = {'comercio': 'c', 'operaciones': 'o', 'identidad': 'i'}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def confirmar(self): pass

        with patch.object(servicios_operaciones, 'UnidadTrabajo', UoW), \
             patch.object(repos_ops, 'obtener_repartidor_por_usuario',
                          return_value={'id': 'r-1'}), \
             patch.object(repos_ops, 'listar_asignaciones_repartidor',
                          return_value=[]), \
             patch.object(repos_ops, 'contar_asignaciones_repartidor_historial',
                          return_value=41), \
             patch.object(repos_ops, 'listar_asignaciones_repartidor_historial',
                          return_value=[]) as historial:
            resultado = servicios_operaciones.listar_repartos_repartidor(
                'usuario-1', pagina=2, por_pagina=20
            )
        self.assertEqual(resultado['paginacion']['pagina'], 2)
        self.assertEqual(resultado['paginacion']['offset'], 20)
        self.assertEqual(resultado['paginacion']['total'], 41)
        historial.assert_called_once_with(
            UoW.conexion, UoW.esquemas, 'r-1', limite=20, offset=20
        )

    def test_listado_repartos_pagina_y_conserva_enlaces(self):
        app = create_app()
        app.config.update(TESTING=True, OMITIR_SEGURIDAD_EN_PRUEBAS=True)
        cliente = app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({'autenticado': True, 'usuario_id': 'u-1',
                           'correo': 'r@example.test', 'roles': ['REPARTIDOR']})
        datos = {
            'activas': [],
            'historial': [{
                'numero_pedido': 'PED-2', 'entrega_id': 'e-2',
                'entrega_estado': 'ENTREGADO',
                'entrega_estado_label': 'Entregado',
                'asignacion_estado': 'FINALIZADA',
                'asignacion_estado_label': 'Finalizada',
                'asignado_en': None, 'finalizado_en': None,
            }],
            'paginacion': crear_paginacion(41, 2, 20),
        }
        with patch(
            'app.repartidor.routes.listar_repartos_repartidor',
            return_value=datos,
        ) as listado:
            respuesta = cliente.get('/repartidor/?page=2')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(listado.call_args.kwargs.get('pagina'), '2')
        html = respuesta.data.decode('utf-8')
        self.assertIn('Página 2 de 3', html)
        self.assertIn('/repartidor/?page=1', html)
        self.assertIn('/repartidor/?page=3', html)
        self.assertIn('Finalizada', html)

    def test_detalle_historico_renderiza_sin_acciones(self):
        app = create_app()
        app.config.update(TESTING=True, OMITIR_SEGURIDAD_EN_PRUEBAS=True)
        cliente = app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({'autenticado': True, 'usuario_id': 'u-1',
                           'correo': 'r@example.test', 'roles': ['REPARTIDOR']})
        detalle = {
            'numero_pedido': 'PED-1', 'entrega_id': 'e-1',
            'cliente_nombre': 'Cliente', 'cliente_correo': '',
            'cliente_telefono': '999999999', 'pedido_total': 20,
            'entrega_estado': 'ENTREGADO',
            'entrega_estado_label': 'Entregado',
            'asignacion_estado': 'FINALIZADA',
            'asignacion_estado_label': 'Finalizada',
            'fecha_programada': None, 'asignado_en': None,
            'aceptado_en': None, 'finalizado_en': None,
            'costo_cobrado_cliente': 5, 'tipo_entrega': 'DELIVERY_LOCAL',
            'delivery': None,
        }
        with patch(
            'app.repartidor.routes.obtener_detalle_reparto_repartidor',
            return_value=detalle,
        ):
            respuesta = cliente.get('/repartidor/e-1')
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.data.decode('utf-8')
        self.assertIn('ya fue cerrado', html)
        self.assertNotIn('/repartidor/e-1/confirmar', html)
        self.assertNotIn('/repartidor/e-1/aceptar', html)


class CorreccionesP1Test(unittest.TestCase):
    """Regresiones de los defectos P1 confirmados en la auditoría."""

    def test_encuesta_bloquea_token_antes_de_insertar(self):
        conexion = MagicMock()
        fila = {'id': 'e-1', 'estado': 'PENDIENTE',
                'numero_pedido': 'PED-1'}
        respuestas = {
            'calificacion_general': 5, 'calificacion_producto': 5,
            'calificacion_entrega': 5, 'calificacion_atencion': 5,
            'recomendaria': 'SI', 'comentario': None,
        }
        with patch.object(encuestas, 'conexion_operaciones',
                          return_value=conexion), \
             patch.object(encuestas, 'esquemas_sulpaa',
                          return_value={'operaciones': 'o',
                                        'comercio': 'c'}), \
             patch.object(encuestas, 'validar_respuestas',
                          return_value=respuestas), \
             patch.object(encuestas_repo, 'buscar_por_hash_bloqueado',
                          return_value=fila) as bloqueo, \
             patch.object(encuestas_repo, 'existe_respuesta',
                          return_value=False), \
             patch.object(encuestas_repo, 'insertar_respuesta'), \
             patch.object(encuestas_repo, 'marcar_estado'), \
             patch.object(encuestas_repo, 'registrar_evento'):
            resultado = encuestas.responder_encuesta('token-valido-1', {})
        self.assertEqual(resultado, {'ok': True, 'estado': 'RESPONDIDA'})
        bloqueo.assert_called_once()
        conexion.commit.assert_called_once()

    def test_busqueda_por_hash_usa_for_update(self):
        conexion = MagicMock()
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        encuestas_repo.buscar_por_hash_bloqueado(
            conexion, {'operaciones': 'o', 'comercio': 'c'}, 'hash'
        )
        sql, params = cursor.execute.call_args.args
        self.assertIn('FOR UPDATE', sql)
        self.assertEqual(tuple(params), ('hash',))

    def test_repartidor_rechaza_dni_invalido(self):
        from app.operaciones import services as operaciones
        for dni in ('123', '1234567A', '123456789'):
            with self.subTest(dni=dni):
                with self.assertRaises(operaciones.ReglaOperativaError):
                    operaciones.registrar_repartidor(
                        'actor', ['GERENTE'], 'r@example.test',
                        'Clave1234', 'Ana', 'Pérez', None, '987654321',
                        dni=dni,
                    )

    def test_contenido_rechaza_url_peligrosa(self):
        for url in ('javascript:alert(1)', 'data:text/html,x',
                    'ftp://example.test/a', '//example.test/a'):
            with self.subTest(url=url):
                with self.assertRaises(contenido.ErrorContenido):
                    contenido.agregar_fuente_para_admin(
                        ['GERENTE'], 'c-1', 'Fuente', url=url
                    )

    def test_contenido_acepta_url_http_y_limita_referencia(self):
        with patch.object(contenido, 'agregar_fuente',
                          return_value={'ok': True}) as alta:
            contenido.agregar_fuente_para_admin(
                ['GERENTE'], 'c-1', 'Fuente',
                url='https://example.test/fuente',
                referencia='Ref', nota='Nota',
            )
        self.assertEqual(alta.call_args.kwargs['url'],
                         'https://example.test/fuente')
        with self.assertRaises(contenido.ErrorContenido):
            contenido.agregar_fuente_para_admin(
                ['GERENTE'], 'c-1', 'Fuente', referencia='x' * 256
            )

    def test_administrador_conserva_rol_gerente_no_enviado(self):
        from app.admin.usuarios import repositories as usuarios_repo
        from app.admin.usuarios import services as usuarios

        with patch.object(
            usuarios_repo, 'obtener_usuario',
            return_value={'roles': [{'codigo': 'GERENTE'}],
                          'correo': 'g@example.test'},
        ), patch.object(
            usuarios_repo, 'listar_roles',
            return_value=[{'codigo': 'GERENTE', 'id': 'rol-g'}],
        ), patch.object(
            usuarios_repo, 'reemplazar_roles'
        ) as reemplazar:
            resultado = usuarios.asignar_roles_usuario_admin(
                ['ADMINISTRADOR'], 'actor', ['ADMINISTRADOR'],
                'usuario-1', [],
            )
        self.assertTrue(resultado)
        reemplazar.assert_not_called()


    def test_facturacion_inserta_columna_tipo(self):
        from app.identidad import repositories as identidad_repo
        conexion = MagicMock()
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        identidad_repo.guardar_datos_facturacion(
            'fact-1', 'usuario-1', 'PERSONA', dni='12345678',
            nombre_facturacion='Ana', conexion=conexion,
        )
        insert = [
            llamada.args for llamada in cursor.execute.call_args_list
            if 'INSERT INTO datos_facturacion' in llamada.args[0]
        ]
        self.assertEqual(len(insert), 1)
        sql, params = insert[0]
        self.assertRegex(sql, r'\btipo\b')
        self.assertNotIn('tipo_contribuyente', sql)
        self.assertEqual(params[2], 'PERSONA')

    def test_caja_rechaza_montos_no_finitos(self):
        from app.admin.caja import services as caja_servicios
        for monto in ('nan', 'inf', '-inf', '0', '-5'):
            with self.subTest(monto=monto):
                with self.assertRaises(caja_servicios.ReglaCajaError):
                    caja_servicios.registrar_egreso_manual(
                        'actor', ['GERENTE'],
                        {'monto': monto, 'categoria_id': '1',
                         'concepto': 'Gasto operativo'},
                    )

    def test_caja_rechaza_rango_de_fechas_invalido(self):
        from app.admin.caja import services as caja_servicios
        for desde, hasta in (('2026-13-01', ''), ('2026-02-01', '2026-01-01')):
            with self.subTest(desde=desde, hasta=hasta):
                with self.assertRaises(caja_servicios.ReglaCajaError):
                    caja_servicios.listar_movimientos(
                        {'desde': desde, 'hasta': hasta}, pagina=1
                    )

    def test_reportes_rechaza_rango_invertido(self):
        from app.admin.reportes import services as reportes
        with self.assertRaises(reportes.ReglaReporteError):
            reportes.generar_reporte(
                'VENTAS', 'CSV', 'actor',
                {'desde': '2026-02-01', 'hasta': '2026-01-01'},
            )

    def test_entrega_no_se_programa_en_el_pasado(self):
        from app.operaciones import services as operaciones
        with self.assertRaises(operaciones.ReglaOperativaError):
            operaciones.programar_entrega(
                'actor', ['GERENTE'], 'entrega-1', '2020-01-01T10:00'
            )


    def test_administrador_no_cambia_estado_de_gerente(self):
        from app.admin.usuarios import repositories as usuarios_repo
        from app.admin.usuarios import services as usuarios

        with patch.object(
            usuarios_repo, 'obtener_usuario',
            return_value={'estado': 'ACTIVO',
                          'roles': [{'codigo': 'GERENTE'}],
                          'correo': 'g@example.test'},
        ), patch.object(
            usuarios_repo, 'actualizar_estado_usuario'
        ) as actualizar:
            with self.assertRaises(usuarios.ErrorUsuarios):
                usuarios.cambiar_estado_usuario_admin(
                    ['ADMINISTRADOR'], 'actor', ['ADMINISTRADOR'],
                    'gerente-1', 'INACTIVO',
                )
        actualizar.assert_not_called()


    def test_ajuste_rechaza_verificacion_de_otra_existencia(self):
        with patch.object(
            inventario, 'listar_motivos_activos',
            return_value=[{'codigo': 'AJUSTE_CONTEO',
                           'categoria': 'AJUSTE'}],
        ), patch.object(
            inventario, 'verificacion_pertenece_existencia',
            return_value=False,
        ), patch.object(
            inventario, 'registrar_movimiento_stock'
        ) as registrar:
            with self.assertRaises(inventario.ErrorInventario):
                inventario.registrar_ajuste(
                    'actor', ['GERENTE'], 'existencia-1',
                    'AJUSTE_CONTEO', 'AJUSTE_POSITIVO', 1,
                    verificacion_id='verificacion-otra',
                )
        registrar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
