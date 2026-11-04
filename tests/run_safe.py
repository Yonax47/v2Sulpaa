"""Suite sin BD real. Las pruebas históricas de integración se ejecutan aparte.

python -m tests.run_safe
"""
import unittest
from unittest.mock import patch

from pymysql.err import OperationalError


MODULES = '''admin_pedidos auditoria_sensible bloque2_entregas bloque2_operaciones
bloque3 bloque4 carrito_favoritos_contract checkout_atomico checkout_contract
configuracion_pruebas confirmacion_pedido etapa3_coberturas fase0_seguridad
fase1_seguridad fase21_entorno fase2_catalogo fase41_ui fase42_ventas_paginacion
fase43_registro_perfil fase44_correo fase45_constancia_pdf imagenes_producto
modo_sin_correo predeploy_checkout_red preflight_apisperu sql_alwaysdata
correcciones_publicacion'''.split()

# Estas pruebas antiguas consultan datos reales sin mocks; no son unitarias.
REQUIRES_DATABASE = {
    'tests.test_checkout_atomico.CheckoutAtomicoIntegracionTest.test_rollback_cruza_esquemas_sin_residuos',
    'tests.test_bloque2_entregas.PermisosHTTPEntregasTest.test_get_entregas_permitido_para_roles_operativos',
    'tests.test_bloque2_entregas.PermisosHTTPEntregasTest.test_detalle_inexistente_responde_404',
    'tests.test_bloque2_entregas.PermisosHTTPEntregasTest.test_planilla_repartidores_carga_para_operativo',
    'tests.test_bloque2_entregas.PermisosHTTPRepartidorTest.test_lista_solo_para_repartidor',
    'tests.test_bloque2_entregas.RedireccionesLoginYConfirmacionTest.test_confirmar_entrega_ok_conserva_flash',
}


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromNames(['tests.test_' + m for m in MODULES])
    tests = [test for test in flatten(suite) if test.id() not in REQUIRES_DATABASE]
    print(f'Suite segura: {len(tests)} pruebas; 6 casos históricos requieren BD aislada.')
    # OperationalError conserva los fallbacks existentes de "BD no disponible".
    with patch('pymysql.connect', side_effect=OperationalError(2003, 'BD real denegada por run_safe')):
        result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(tests))
    raise SystemExit(not result.wasSuccessful())
