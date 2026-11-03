"""
Acceso a datos del reporte de Entregas (Ronda Final, Bloque 4).

Fuente única real: ``entregas`` de Operaciones enlazada con su pedido
(Comercio) y, cuando existe, el repartidor asignado (asignaciones_reparto
con perfiles de Identidad).

El reporte es SOLO lectura: no crea entregas, estados ni programaciones.
El rango de fechas filtra por ``e.creado_en`` (fecha de registro real).
"""

import os
import re

from app.config.database import conexion_operaciones, nombre_esquema

_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")


def _esquemas_validos():
    """Devuelve los tres esquemas del reporte desde una fuente segura."""
    return (
        nombre_esquema("DB_OPERACIONES"),
        nombre_esquema("DB_COMERCIO"),
        nombre_esquema("DB_IDENTIDAD"),
    )


def listar_entregas_reporte(desde=None, hasta=None):
    """Lista entregas reales del período con pedido y repartidor.

    Devuelve por cada entrega:
    - id, numero_pedido, tipo_entrega, estado;
    - fecha_programada, completado_en, creado_en;
    - repartidor_nombre (o None si aún no hay asignación);
    - costo_cobrado_cliente, moneda del pedido.
    """
    operaciones, comercio, identidad = _esquemas_validos()

    condiciones = []
    parametros = []
    if desde:
        condiciones.append("e.creado_en >= %s")
        parametros.append(desde)
    if hasta:
        condiciones.append("e.creado_en < DATE_ADD(%s, INTERVAL 1 DAY)")
        parametros.append(hasta)
    where_sql = (
        ("WHERE " + " AND ".join(condiciones))
        if condiciones
        else ""
    )

    consulta = f"""
        SELECT
            e.id,
            p.numero_pedido,
            p.moneda,
            e.tipo_entrega,
            e.estado,
            e.fecha_programada,
            e.completado_en,
            e.costo_cobrado_cliente,
            e.creado_en,
            rep.detalle AS repartidor_detalle
        FROM {operaciones}.entregas AS e
        INNER JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
        LEFT JOIN (
            SELECT a.entrega_id,
                   CONCAT_WS(' ',
                             pf.nombres,
                             pf.apellido_paterno,
                             pf.apellido_materno) AS detalle
            FROM {operaciones}.asignaciones_reparto AS a
            INNER JOIN {operaciones}.repartidores AS r
                ON r.id = a.repartidor_id
            LEFT JOIN {identidad}.usuarios AS u ON u.id = r.usuario_id
            LEFT JOIN {identidad}.perfiles AS pf
                ON pf.usuario_id = r.usuario_id
            ORDER BY a.asignado_en ASC,
                     a.id ASC
        ) AS rep ON rep.entrega_id = e.id
        {where_sql}
        ORDER BY e.creado_en DESC, p.numero_pedido DESC
    """

    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(parametros))
            return cursor.fetchall()
    finally:
        conexion.close()
