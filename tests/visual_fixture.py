"""Servidor visual local, solo datos sintéticos y conexiones DB prohibidas.

Ejecutar: python -m tests.visual_fixture (127.0.0.1:5067).
No permite login ni operaciones: únicamente HTML de plantillas y assets.
"""

from datetime import datetime
from unittest.mock import patch

from flask import Flask, flash, render_template, session

from app import create_app
from app.shared.pagination import crear_paginacion


def generar():
    app = create_app()
    app.config.update(TESTING=True)
    resumen = dict(total=0, instrumentados=0, con_evidencia=0, pendientes_de_datos=0, cumplen=0, no_cumplen=0)
    operativo = dict(pedidos_iniciados=0, pedidos_completados=0, entregas=0, productos_con_stock_bajo=0,
                     ingresos=40, egresos=10, flujo_neto=30, encuestas_completadas=0, satisfaccion_promedio=None)
    gerencial = dict(ventas_cobradas={'pedidos_cobrados': 2, 'ingresos_cobrados': 40}, top_productos_cobrados=[],
                     ingresos_por_producto=[], ventas_cobradas_serie=[], pedidos_por_estado=[], estados_financieros={},
                     periodo='dia', caja_resumen={'ingresos': 40, 'egresos': 10})
    perfil = dict(nombres='Cliente de prueba', apellido_paterno='Sintético', apellido_materno='',
                  correo='cliente.visual@example.invalid', telefono='900000000', dni='00000000', correo_verificado=False)
    p = crear_paginacion(80, 2, 25, endpoint='admin_caja.listado', filtros={'tipo': 'EGRESO'})
    mov = dict(id=1, tipo='EGRESO', origen='MANUAL', concepto='Concepto sintético de prueba visual con contenido extenso',
               monto=10, moneda='PEN', estado='ACTIVO', categoria_nombre='Pruebas', fecha_movimiento=datetime(2026, 11, 3),
               creado_en=datetime(2026, 11, 3), usuario_registra_id='fixture')
    paginas = {
        'login': ('auth/login.html', {}),
        'registro': ('auth/registro.html', {'datos_formulario': {}}),
        'inicio': ('cliente/inicio.html', {}),
        'tienda': ('cliente/tienda.html', dict(catalogo=[], variantes_330=[], packs_fijos=[], packs_personalizados=[], carrito={'items': [], 'subtotal': 0})),
        'checkout': ('cliente/checkout.html', dict(carrito_vacio=False, checkout=dict(ok=True, cliente=perfil, direccion=None, direcciones=[]),
                         carrito={'items': [{'nombre': 'Kombucha sintética de prueba visual', 'cantidad': 2, 'subtotal': 40}], 'subtotal': 40}, departamentos=[])),
        'perfil': ('perfil/inicio.html', dict(perfil=perfil, direcciones=[], facturacion=[], departamentos=[])),
        'pedidos': ('cliente/pedidos.html', dict(pedidos=[])),
        'dashboard': ('admin/dashboard.html', dict(kpis=[], resumen=resumen, operativo=operativo, gerencial=gerencial,
                          graficos={'flujo_caja': [{'periodo': '2026-10', 'ingresos': 40, 'egresos': 10}], 'kpi09': None, 'satisfaccion': None})),
        'caja': ('admin/caja/lista.html', dict(movimientos=[mov] * 5, categorias=[], resumen=dict(total_movimientos=80, ingresos=40, egresos=10, flujo_neto=30),
                       filtros=dict(desde='', hasta='', tipo='', origen='', categoria_id=''), serie_flujo=[{'periodo': '2026-10', 'ingresos': 40, 'egresos': 10}], paginacion=p)),
        'inventario': ('admin/inventario/lista.html', dict(existencias=[], filtros={'q': '', 'bajo_minimo': False}, paginacion=None)),
        'historial': ('admin/inventario/detalle.html', dict(existencia=dict(
            existencia_id='fixture', almacen_codigo='PRUEBA', almacen_nombre='Almacén sintético',
            nombre_comercial='Kombucha de prueba visual', sabor='Café', presentacion='Botella 1 L',
            stock_fisico=100, stock_reservado=10, stock_disponible=90, stock_minimo=5,
            actualizado_en=datetime(2026, 11, 3), motivos_entrada=[],
            movimientos=[dict(movimiento_id='fixture', tipo_movimiento='ENTRADA', cantidad=10,
                              stock_anterior=90, stock_posterior=100, origen='MANUAL', motivo_nombre='Prueba',
                              creado_en=datetime(2026, 11, 3), responsable_correo='inventario@example.invalid')],
            verificaciones=[dict(verificacion_id='fixture', codigo_verificacion='VER-PRUEBA',
                                 stock_sistema=100, stock_fisico=100, diferencia=0, coincide=True,
                                 verificada_en=datetime(2026, 11, 3), responsable_correo='inventario@example.invalid')],
            paginacion_movimientos={**p, 'endpoint': 'admin_inventario.detalle', 'parametro': 'mov_page', 'filtros': {'existencia_id': 'fixture', 'ver_page': 2}},
            paginacion_verificaciones={**p, 'endpoint': 'admin_inventario.detalle', 'parametro': 'ver_page', 'filtros': {'existencia_id': 'fixture', 'mov_page': 2}},
        ))),
        'entregas': ('admin/entregas/repartidores.html', dict(repartidores=[dict(id='fixture', nombre='Repartidor sintético', correo='repartidor@example.invalid', telefono='900000000', estado='ACTIVO', estado_label='Activo', disponible=True, disponible_label='Disponible', carga_activa=5)], paginacion=None)),
        'encuestas': ('admin/encuestas/lista.html', dict(
            encuestas=[dict(id=1, numero_pedido='P-PRUEBA', usuario_id='fixture', estado='RESPONDIDA',
                            canal='PORTAL', calificacion_general=5, recomendaria='SI',
                            creado_en=datetime(2026, 11, 3, 9, 0))],
            paginacion={**p, 'endpoint': 'admin_encuestas.listado', 'filtros': {'estado': 'RESPONDIDA'}},
            filtros=dict(estado='RESPONDIDA', desde='', hasta=''),
            estadisticas=dict(por_estado=[{'estado': 'RESPONDIDA', 'cantidad': 1}],
                              respuestas=1, promedio=5, recomendarian=1),
        )),
    }
    htmls = {}
    for nombre, (plantilla, contexto) in paginas.items():
        with app.test_request_context('/'):
            if nombre not in ('login', 'registro'):
                session.update(usuario_id='fixture-visual', nombres='Prueba visual', roles=['GERENTE', 'ADMINISTRADOR'])
            flash('Tu sesión se cerró correctamente' if nombre == 'login' else 'Bienvenido a SULPAA', 'success')
            htmls[nombre] = render_template(plantilla, **contexto)
    return app.static_folder, htmls


if __name__ == '__main__':
    with patch('pymysql.connect', side_effect=AssertionError('DB prohibida en fixtures visuales')):
        static, htmls = generar()
        server = Flask('visual_sin_bd', static_folder=static)

        @server.get('/<nombre>')
        def pagina(nombre):
            return htmls.get(nombre, 'Fixture no encontrado'), 200 if nombre in htmls else 404

        server.run(host='127.0.0.1', port=5067, debug=False, use_reloader=False)
