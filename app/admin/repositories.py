"""
Repositorio del m\u00f3dulo Administrativo de SULPAA V2.

FUNCI\u00d3N DE ESTA CAPA
======================

Este archivo es la \u00fanica capa que ejecuta SQL.
Concretamente, ejecuta \u00fanicamente consultas SELECT
de SOLO LECTURA contra las bases de datos reales del
sistema (identidad, comercio, operaciones).

NO hace nada de esto:
- no escribe ni modifica datos;
- no contiene l\u00f3gica de negocio (eso vive en services.py);
- no contiene rutas HTTP (eso vive en routes.py).

C\u00d3MO SE CONECTA (patr\u00f3n de la casa)
===================================

Se reutilizan los 4 conectores que el m\u00f3dulo de
configuraci\u00f3n ya define en `app/config/database.py`:

    from app.config.database import (
        conexion_comercio,
        conexion_operaciones,
    )

Metodolog\u00eda:
- Cada funci\u00f3n ABRE su propia conexi\u00f3n con el conector
  del dominio correcto.
- Usa `with ... cursor()` para gestionar el cursor.
- Cierra la conexi\u00f3n SIEMPRE en un bloque `finally`
  (no se dejan conexiones colgadas en el pool de MySQL).
- Devuelve UNA sola m\u00e9trica (un `dict` con conteos);
  el c\u00e1lculo del porcentaje y la meta lo hace
  services.py.

KPI INSTRUMENTADOS (Etapa 1)
============================

- KPI-01 (RF-01): Pedidos procesados correctamente.
  F\u00f3rmula: (entregas ENTREGADO / total entregas) * 100
  Tabla: `entregas` (dominio operaciones). Columna: `estado`
  (ENUM real del dump operaciones).

- KPI-04 (RF-04): Disponibilidad del historial de pedidos.
  F\u00f3rmula: (pedidos con historial / total pedidos) * 100
  Tablas: `pedidos` y `pedido_historial` (dominio comercio).

Los dem\u00e1s 16 KPI (Etapas posteriores) NO se instrumentan
aqu\u00ed: se muestran como "Pendiente de instrumentaci\u00f3n"
en el dashboard porque su tabla base a\u00fan no permite
calcularlos sin inventar columnas.
"""


from app.config.database import (
    conexion_comercio,
    conexion_operaciones,
)


# ============================================================
# KPI-01 (BASE) — PEDIDOS PROCESADOS CORRECTAMENTE
# ============================================================
#
# F\u00f3rmula:
#
#     KPI-01 = ( entregas con estado = 'ENTREGADO' / total de entregas ) * 100
#
# Tabla y columnas utilizadas (dump REAL de operaciones):
#
#     operaciones.entregas.estado
#
#     Definici\u00f3n real de la columna `estado` en el esquema
#     (ENUM del dump operaciones):
#
#         'PENDIENTE'
#         'EN_PREPARACION'
#         'LISTO'
#         'PROGRAMADO'
#         'EN_TRANSITO'
#         'LISTO_PARA_RECOJO'
#         'ENTREGADO'
#         'CANCELADO'
#         'INCIDENCIA'
#
# NOTA DE DISE\u00d1O:
# Usa el estado literal EXACTO `ENTREGADO` (el \u00fanico que el
# esquema define para "entrega completada"). El sistema NO
# inventa un estado "COMPLETADO" que el dump no posea.
# ============================================================


def obtener_metrica_entregas():
    """
    M\u00e9trica base del KPI-01: conteos de entregas.

    Devuelve \u00fanicamente los DOS conteos que la tabla
    real `entregas` permite consultar:

    - entregas_entregadas: filas con estado = ENTREGADO.
    - total_entregas:      todas las filas de la tabla.

    El porcentaje se calcula en services.py (esta capa
    s\u00f3lo LEE los conteos; no decide si se cumple la meta).
    """

    conexion = conexion_operaciones()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total
                FROM entregas
                """
            )

            total_entregas = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total
                FROM entregas
                WHERE estado = 'ENTREGADO'
                """
            )

            entregas_entregadas = cursor.fetchone()["total"]

        return {
            "total_entregas": total_entregas,
            "entregas_entregadas": entregas_entregadas,
        }

    finally:

        conexion.close()


# ============================================================
# KPI-04 (BASE) — DISPONIBILIDAD DEL HISTORIAL DE PEDIDOS
# ============================================================
#
# F\u00f3rmula:
#
#     KPI-04 = ( pedidos con historial / total de pedidos ) * 100
#
# Tablas y columnas utilizadas (dump REAL de comercio):
#
#     comercio.pedidos
#         - id
#
#     comercio.pedido_historial
#         - pedido_id
#         - estado_anterior
#         - estado_nuevo
#         - creado_en
#
# De esta manera respondemos la pregunta de sustentaci\u00f3n:
# "\u00bfCu\u00e1nta informaci\u00f3n del historial de cada pedido
# queda registrada y puede consultarse?". El numerador cuenta
# los pedidos que tienen al menos un registro en el historial.
# ============================================================


def obtener_metrica_historial_pedidos():
    """
    Métrica base del KPI-04: conteos de pedidos vs historial.

    Devuelve únicamente los DOS conteos reales:

    - total_pedidos:          filas en `pedidos` (comercio).
    - pedidos_con_historial:  pedidos distintos que aparecen
                              en `pedido_historial`.

    El porcentaje (y la meta ≥ 98 %) se calculan en
    services.py; esta capa sólo LEE los conteos.
    """

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total
                FROM pedidos
                """
            )

            total_pedidos = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT pedido_id) AS total
                FROM pedido_historial
                """
            )

            pedidos_con_historial = cursor.fetchone()["total"]

        return {
            "total_pedidos": total_pedidos,
            "pedidos_con_historial": pedidos_con_historial,
        }

    finally:

        conexion.close()


def obtener_metrica_pedidos_procesados():
    """
    Métrica base del KPI-01: pedidos iniciados vs completados.

    Devuelve únicamente los DOS conteos reales:

    - pedidos_iniciados:   pedidos cuyo estado alcanzó la zona
                           operativa real (EN_PREPARACION o
                           COMPLETADO).
    - pedidos_completados: pedidos en estado COMPLETADO que
                           además tienen una entrega ENTREGADO
                           y un pago PAGADO (finalización
                           legítima de extremo a extremo).

    El porcentaje se calcula en services.py; esta capa sólo
    LEE los conteos.
    """
    import os
    import re

    comercio = str(os.getenv("DB_COMERCIO") or "").strip()
    operaciones = str(os.getenv("DB_OPERACIONES") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", comercio):
        raise RuntimeError("DB_COMERCIO no contiene un esquema válido.")
    if not re.fullmatch(r"[A-Za-z0-9_]+", operaciones):
        raise RuntimeError("DB_OPERACIONES no contiene un esquema válido.")

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                f"""
                SELECT
                    COUNT(DISTINCT p.id) AS pedidos_iniciados,
                    COUNT(DISTINCT CASE
                        WHEN p.estado = 'COMPLETADO'
                         AND e.estado = 'ENTREGADO'
                         AND pg.estado = 'PAGADO'
                        THEN p.id
                    END) AS pedidos_completados
                FROM {comercio}.pedidos AS p
                LEFT JOIN {operaciones}.entregas AS e
                    ON e.pedido_id = p.id
                LEFT JOIN {operaciones}.pagos AS pg
                    ON pg.pedido_id = p.id
                WHERE p.estado IN ('EN_PREPARACION', 'COMPLETADO')
                """
            )

            conteos = cursor.fetchone()

        return {
            "pedidos_iniciados": conteos["pedidos_iniciados"],
            "pedidos_completados": conteos["pedidos_completados"],
        }

    finally:

        conexion.close()


def obtener_metrica_consistencia_estados():
    """
    Métrica base del KPI-07: consistencia estado actual.

    Devuelve únicamente los DOS conteos reales:

    - total_pedidos_historial:   pedidos con al menos un evento
                                 en `pedido_historial`.
    - estados_consistentes:      pedidos cuyo estado ACTUAL
                                 coincide con el último evento
                                 (estado_nuevo) registrado.

    El porcentaje se calcula en services.py; esta capa sólo
    LEE los conteos.
    """

    conexion = conexion_comercio()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT h.pedido_id) AS total_pedidos_historial
                FROM pedido_historial AS h
                """
            )

            total_pedidos_historial = cursor.fetchone()[
                "total_pedidos_historial"
            ]

            cursor.execute(
                """
                SELECT COUNT(*) AS estados_consistentes
                FROM pedidos AS p
                WHERE EXISTS (
                    SELECT 1
                    FROM pedido_historial AS h1
                    WHERE h1.pedido_id = p.id
                      AND h1.id = (
                          SELECT MAX(h2.id)
                          FROM pedido_historial AS h2
                          WHERE h2.pedido_id = h1.pedido_id
                      )
                      AND h1.estado_nuevo = p.estado
                )
                """
            )

            estados_consistentes = cursor.fetchone()["estados_consistentes"]

        return {
            "total_pedidos_historial": total_pedidos_historial,
            "estados_consistentes": estados_consistentes,
        }

    finally:

        conexion.close()


def obtener_metrica_programacion_entregas():
    """
    Métrica base del KPI-08: entregas programadas.

    Devuelve únicamente los DOS conteos reales:

    - total_entregas:        filas en `entregas` (operaciones),
                             es decir, la totalidad de
                             solicitudes de entrega.
    - entregas_programadas:  entregas con `fecha_programada`
                             registrada (programadas de forma
                             correcta).

    El porcentaje se calcula en services.py; esta capa sólo
    LEE los conteos.
    """

    conexion = conexion_operaciones()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_entregas,
                    SUM(CASE WHEN fecha_programada IS NOT NULL
                             THEN 1 ELSE 0 END) AS entregas_programadas
                FROM entregas
                """
            )

            conteos = cursor.fetchone()

        return {
            "total_entregas": conteos["total_entregas"],
            "entregas_programadas": conteos["entregas_programadas"],
        }

    finally:

        conexion.close()


def obtener_metrica_satisfaccion():
    """
    Métrica base del KPI-09 (GANCHO): satisfacción del cliente.

    Devuelve únicamente los conteos reales disponibles:

    - encuestas_completadas:     encuestas con calificación.
    - encuestas_satisfactorias:  calificación >= 4.

    IMPORTANTE (GANCHO): el dominio Operaciones aún no
    define la tabla `encuestas` en el dump vigente, así que
    esta métrica consulta `information_schema` y, si el
    campo `estado`/`calificacion` no existe, devuelve
    "disponible": False. El dashboard conserva entonces el
    KPI como "Pendiente" sin inventar un valor.
    """

    import os
    import re

    operaciones = str(os.getenv("DB_OPERACIONES") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", operaciones):
        raise RuntimeError("DB_OPERACIONES no contiene un esquema válido.")

    conexion = conexion_operaciones()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'encuestas'
                """,
                (operaciones,),
            )

            if cursor.fetchone()["total"] == 0:
                return {
                    "disponible": False,
                    "encuestas_completadas": None,
                    "encuestas_satisfactorias": None,
                }

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS encuestas_completadas,
                    COALESCE(SUM(CASE WHEN calificacion >= 4
                                      THEN 1 ELSE 0 END), 0)
                        AS encuestas_satisfactorias
                FROM {operaciones}.encuestas
                WHERE calificacion IS NOT NULL
                """
            )

            conteos = cursor.fetchone()

        return {
            "disponible": True,
            "encuestas_completadas": conteos["encuestas_completadas"],
            "encuestas_satisfactorias": conteos["encuestas_satisfactorias"],
        }

    finally:

        conexion.close()
