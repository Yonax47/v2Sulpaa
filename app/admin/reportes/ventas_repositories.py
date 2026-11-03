"""
Acceso a datos del reporte de Ventas (Bloque 4).

Complementa la auditoría de reportes con la materia prima del reporte
comercial. El resto de tipos (KPI, Caja, Encuestas) reutiliza sus
fuentes únicas ya existentes.
"""

import os
import re

from app.config.database import conexion_comercio, nombre_esquema

_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")


def obtener_datos_ventas(desde=None, hasta=None):
    """Lista pedidos del período (número, estado, total) para el reporte."""
    comercio = nombre_esquema("DB_COMERCIO")

    where = []
    parametros = []
    if desde:
        where.append("p.creado_en >= %s")
        parametros.append(desde)
    if hasta:
        where.append("p.creado_en < DATE_ADD(%s, INTERVAL 1 DAY)")
        parametros.append(hasta)
    condicion = ((" WHERE " + " AND ".join(where)) if where else "")

    conexion = conexion_comercio()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT p.id, p.numero_pedido, p.estado, p.origen,
                       p.total, p.moneda, p.creado_en
                FROM {comercio}.pedidos AS p
                {condicion}
                ORDER BY p.creado_en DESC
                """,
                parametros,
            )
            return cursor.fetchall()
    finally:
        conexion.close()
