"""
Acceso a datos del módulo administrativo de Flujo de Caja (Bloque 4).

Tablas reales (operaciones):
- caja_categorias     (catálogo INGRESO/EGRESO; solo clasifica).
- caja_movimientos    (fuente única de ingresos y egresos).

Regla de caja autorizada: un pago PAGADO con ``pagado_en`` genera
EXACTAMENTE un ingreso (UNIQUE pago_id) con la categoría COBRO_PEDIDO,
el monto y el método de pago reales. La escritura idempotente de ese
ingreso vive en ``app/operaciones/repositories.py``
(``insertar_ingreso_caja_desde_pago``) porque participa en la misma
transacción que confirma el pago.

Los egresos manuales son ALWAYS EGRESO con origen MANUAL, actor
obligatorio, monto > 0 y categoría EGRESO activa (validado en Service).
"""

import os
import re

from app.config.database import conexion_operaciones

_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")


def _esquema():
    valor = str(os.getenv("DB_OPERACIONES") or "").strip()
    if not valor or not _IDENTIFICADOR_SQL.fullmatch(valor):
        raise RuntimeError(
            "DB_OPERACIONES no contiene un esquema MySQL válido."
        )
    return valor


def listar_categorias(tipo=None, solo_activas=True):
    """Lista categorías de caja (para filtros y formularios)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            where = []
            parametros = []
            if tipo:
                where.append("tipo = %s")
                parametros.append(tipo)
            if solo_activas:
                where.append("estado = 'ACTIVO'")
            condicion = ((" WHERE " + " AND ".join(where)) if where else "")
            cursor.execute(
                f"""
                SELECT id, codigo, nombre, tipo, estado
                FROM caja_categorias
                {condicion}
                ORDER BY tipo DESC, nombre ASC
                """,
                parametros,
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def listar_metodos_pago():
    """Lista métodos de pago activos (para el select de egresos)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, nombre
                FROM metodos_pago
                ORDER BY nombre ASC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def buscar_categoria_activa(categoria_id, tipo_esperado):
    """Devuelve una categoría ACTIVA que coincida con el tipo esperado."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, codigo, nombre, tipo, estado
                FROM caja_categorias
                WHERE id = %s AND estado = 'ACTIVO' LIMIT 1
                """,
                (categoria_id,),
            )
            categoria = cursor.fetchone()
            if categoria and tipo_esperado and categoria["tipo"] != tipo_esperado:
                return None
            return categoria
    finally:
        conexion.close()


def insertar_movimiento_manual(*, categoria_id, tipo, concepto, monto,
                               moneda, fecha_movimiento, metodo_pago_id,
                               usuario_registra_id):
    """Inserta un movimiento manual (egreso) con su actor responsable."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO caja_movimientos
                    (categoria_id, tipo, origen, concepto, monto, moneda,
                     metodo_pago_id, fecha_movimiento, estado,
                     usuario_registra_id)
                VALUES (%s, %s, 'MANUAL', %s, %s, %s, %s, %s, 'ACTIVO', %s)
                """,
                (categoria_id, tipo, concepto, monto, moneda,
                 metodo_pago_id, fecha_movimiento, usuario_registra_id),
            )
            nuevo_id = cursor.lastrowid
        conexion.commit()
        return nuevo_id
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def anular_movimiento(movimiento_id, actor_id, motivo):
    """Anula un movimiento ACTIVO (trazable: motivo y actor). Nunca DELETE."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE caja_movimientos
                SET estado = 'ANULADO', anulado_en = NOW(),
                    anulado_motivo = %s, anulado_por_usuario_id = %s
                WHERE id = %s AND estado = 'ACTIVO'
                """,
                (motivo, actor_id, movimiento_id),
            )
            modificado = cursor.rowcount == 1
        conexion.commit()
        return modificado
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def listar_movimientos(desde=None, hasta=None, tipo=None, origen=None,
                       categoria_id=None, limite=300):
    """Lista movimientos enriquecidos (categoría y método de pago)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            where = []
            parametros = []
            if desde:
                where.append("m.fecha_movimiento >= %s")
                parametros.append(desde)
            if hasta:
                where.append(
                    "m.fecha_movimiento < DATE_ADD(%s, INTERVAL 1 DAY)"
                )
                parametros.append(hasta)
            if tipo:
                where.append("m.tipo = %s")
                parametros.append(tipo)
            if origen:
                where.append("m.origen = %s")
                parametros.append(origen)
            if categoria_id:
                where.append("m.categoria_id = %s")
                parametros.append(categoria_id)
            condicion = ((" WHERE " + " AND ".join(where)) if where else "")
            cursor.execute(
                f"""
                SELECT m.id, m.categoria_id, m.tipo, m.origen, m.concepto,
                       m.monto, m.moneda, m.metodo_pago_id, m.pago_id,
                       m.pedido_id, m.fecha_movimiento, m.estado,
                       m.anulado_en, m.anulado_motivo, m.creado_en,
                       c.nombre AS categoria_nombre,
                       mp.nombre AS metodo_nombre
                FROM caja_movimientos AS m
                INNER JOIN caja_categorias AS c ON c.id = m.categoria_id
                LEFT JOIN metodos_pago AS mp ON mp.id = m.metodo_pago_id
                {condicion}
                ORDER BY m.fecha_movimiento DESC, m.id DESC
                LIMIT %s
                """,
                parametros + [limite],
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def resumen_movimientos(desde=None, hasta=None, tipo=None, origen=None,
                        categoria_id=None):
    """Totales de ingresos y egresos ACTIVOS en el período (flujo de caja).

    Respeta los MISMOS filtros que la tabla, para que las tarjetas del
    resumen siempre coincidan con la lista visible.
    """
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            where = ["m.estado = 'ACTIVO'"]
            parametros = []
            if desde:
                where.append("m.fecha_movimiento >= %s")
                parametros.append(desde)
            if hasta:
                where.append(
                    "m.fecha_movimiento < DATE_ADD(%s, INTERVAL 1 DAY)"
                )
                parametros.append(hasta)
            if tipo:
                where.append("m.tipo = %s")
                parametros.append(tipo)
            if origen:
                where.append("m.origen = %s")
                parametros.append(origen)
            if categoria_id:
                where.append("m.categoria_id = %s")
                parametros.append(categoria_id)
            condicion = " AND ".join(where)
            cursor.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN m.tipo = 'INGRESO'
                                     THEN m.monto ELSE 0 END), 0)
                        AS ingresos,
                    COALESCE(SUM(CASE WHEN m.tipo = 'EGRESO'
                                     THEN m.monto ELSE 0 END), 0)
                        AS egresos,
                    COUNT(*) AS total_movimientos
                FROM caja_movimientos AS m
                WHERE {condicion}
                """,
                parametros,
            )
            fila = cursor.fetchone()
        return {
            "ingresos": float(fila["ingresos"] or 0),
            "egresos": float(fila["egresos"] or 0),
            "flujo_neto": float(fila["ingresos"] or 0)
                          - float(fila["egresos"] or 0),
            "total_movimientos": fila["total_movimientos"],
        }
    finally:
        conexion.close()


def pagos_sin_movimiento_caja(conexion, esquemas):
    """Pagos PAGADO con pagado_en que aún no tienen ingreso de caja."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT p.id, p.pedido_id, p.estado, p.pagado_en
            FROM {operaciones}.pagos AS p
            LEFT JOIN {operaciones}.caja_movimientos AS m
                ON m.pago_id = p.id
            WHERE p.estado = 'PAGADO' AND p.pagado_en IS NOT NULL
              AND m.id IS NULL
            ORDER BY p.pagado_en ASC
            """
        )
        return cursor.fetchall()


def serie_flujo_mensual(meses=6):
    """Agrupación mensual de ingresos/egresos ACTIVOS (gráfico del panel)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DATE_FORMAT(m.fecha_movimiento, '%Y-%m') AS periodo,
                       COALESCE(SUM(CASE WHEN m.tipo = 'INGRESO'
                                        THEN m.monto ELSE 0 END), 0)
                           AS ingresos,
                       COALESCE(SUM(CASE WHEN m.tipo = 'EGRESO'
                                        THEN m.monto ELSE 0 END), 0)
                           AS egresos
                FROM caja_movimientos AS m
                WHERE m.estado = 'ACTIVO'
                  AND m.fecha_movimiento >= DATE_SUB(
                        DATE_FORMAT(CURDATE(), '%Y-%m-01'),
                        INTERVAL %s MONTH)
                GROUP BY DATE_FORMAT(m.fecha_movimiento, '%Y-%m')
                ORDER BY periodo ASC
                """,
                (meses - 1,),
            )
            return cursor.fetchall()
    finally:
        conexion.close()