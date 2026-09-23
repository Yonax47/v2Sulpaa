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


import os
import re

from app.config.database import (
    conexion_comercio,
    conexion_inventario,
    conexion_operaciones,
)

_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")


def _esquema(nombre_variable):
    """Devuelve un nombre de esquema MySQL validado desde entorno."""
    valor = str(os.getenv(nombre_variable) or "").strip()
    if not valor or not _IDENTIFICADOR_SQL.fullmatch(valor):
        raise RuntimeError(
            f"La variable {nombre_variable} no contiene un esquema MySQL válido."
        )
    return valor


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


def obtener_metrica_kpi09():
    """
    Fórmula OFICIAL del KPI-09 (invariable, canal PORTAL):

        KPI-09 = ( pedidos entregados con invitación válida /
                   pedidos entregados elegibles ) * 100

    - Numerador:  COUNT DISTINCT de pedidos (encuestas) que tienen al
      menos un evento ``INVITACION_OK`` (la invitación PORTAL quedó
      efectivamente disponible para el cliente) y cuya entrega está
      realmente ``ENTREGADO``.
    - Denominador: COUNT DISTINCT de pedidos elegibles: los que entraron
      al circuito de encuestas (1 fila en ``encuestas``) y cuya entrega
      está ``ENTREGADO``.

    INVARIANTES:
    - Varios ``INVITACION_OK`` para el mismo pedido NO duplican el
      numerador (COUNT DISTINCT por pedido).
    - Una encuesta RESPONDIDA NO altera el numerador: el KPI mide solo
      la invitación entregada, no la respuesta.
    - Si el denominador es 0, el KPI queda PENDIENTE (disponible True,
      pero el cálculo en Services devuelve None).

    La satisfacción (promedios, tasa de respuesta) es una métrica
    GERENCIAL complementaria: vive en ``obtener_metrica_satisfaccion``
    y NUNCA alimenta este KPI.
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
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_NAME IN ('encuestas', 'encuesta_eventos')
                """,
                (operaciones,),
            )
            tablas_encontradas = cursor.fetchone()["total"]
            if tablas_encontradas < 2:
                return {
                    "disponible": False,
                    "invitaciones_ok": None,
                    "pedidos_entregados": None,
                }

            cursor.execute(
                f"""
                SELECT
                    (SELECT COUNT(DISTINCT e.pedido_id)
                     FROM {operaciones}.encuestas AS e
                     INNER JOIN {operaciones}.encuesta_eventos AS ev
                         ON ev.encuesta_id = e.id
                     INNER JOIN {operaciones}.entregas AS g_ped
                         ON g_ped.pedido_id = e.pedido_id
                     WHERE ev.tipo = 'INVITACION_OK'
                       AND g_ped.estado = 'ENTREGADO')
                        AS invitaciones_ok,
                    (SELECT COUNT(DISTINCT e.pedido_id)
                     FROM {operaciones}.encuestas AS e
                     INNER JOIN {operaciones}.entregas AS g
                         ON g.pedido_id = e.pedido_id
                     WHERE g.estado = 'ENTREGADO')
                        AS pedidos_entregados
                """
            )

            conteos = cursor.fetchone()

        return {
            "disponible": True,
            "invitaciones_ok": int(conteos["invitaciones_ok"]),
            "pedidos_entregados": int(conteos["pedidos_entregados"]),
        }

    finally:

        conexion.close()


def obtener_metrica_satisfaccion():
    """
    Métricas GERENCIALES complementarias de satisfacción (Bloque 4).

    Estas métricas NO son el KPI-09. Describen la calidad percibida de
    las encuestas ya completadas y se muestran aparte:

    - satisfaccion_promedio / promedio_producto / promedio_entrega /
      promedio_atencion:  promedio 1-5 de las encuestas RESPONDIDA.
    - recomendacion_porcentaje: % de respuestas con recomendaria = SI.
    - tasa_respuesta_porcentaje: % de encuestas respondidas sobre las
      que recibieron invitación efectiva (INVITACION_OK).
    - respuestas_satisfactorias: respuestas con promedio general >= 4
      (umbral complementario de esta implementación, auditable aquí).

    Si las tablas no existieran, devuelve "disponible": False.
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
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_NAME IN ('encuestas', 'encuesta_respuestas',
                                     'encuesta_eventos')
                """,
                (operaciones,),
            )
            tablas_encontradas = cursor.fetchone()["total"]
            if tablas_encontradas < 3:
                return {
                    "disponible": False,
                    "total_encuestas": None,
                    "encuestas_completadas": None,
                    "encuestas_enviadas": None,
                    "satisfaccion_promedio": None,
                    "promedio_producto": None,
                    "promedio_entrega": None,
                    "promedio_atencion": None,
                    "recomendacion_porcentaje": None,
                    "tasa_respuesta_porcentaje": None,
                    "respuestas_satisfactorias": None,
                }

            cursor.execute(
                f"""
                SELECT
                    (SELECT COUNT(*) FROM {operaciones}.encuestas)
                        AS total_encuestas,
                    (SELECT COUNT(*)
                     FROM {operaciones}.encuesta_respuestas)
                        AS encuestas_completadas,
                    (SELECT COUNT(DISTINCT e.pedido_id)
                     FROM {operaciones}.encuestas AS e
                     INNER JOIN {operaciones}.encuesta_eventos AS ev
                         ON ev.encuesta_id = e.id
                     INNER JOIN {operaciones}.entregas AS g
                         ON g.pedido_id = e.pedido_id
                     WHERE ev.tipo = 'INVITACION_OK'
                       AND g.estado = 'ENTREGADO')
                        AS encuestas_enviadas,
                    COALESCE(AVG(r.calificacion_general), 0)
                        AS satisfaccion_promedio,
                    COALESCE(AVG(r.calificacion_producto), 0)
                        AS promedio_producto,
                    COALESCE(AVG(r.calificacion_entrega), 0)
                        AS promedio_entrega,
                    COALESCE(AVG(r.calificacion_atencion), 0)
                        AS promedio_atencion,
                    COALESCE(SUM(CASE WHEN r.recomendaria = 'SI'
                                      THEN 1 ELSE 0 END), 0)
                        AS recomendaciones_ok,
                    COALESCE(SUM(CASE WHEN
                        (r.calificacion_general
                         + r.calificacion_producto
                         + r.calificacion_entrega
                         + r.calificacion_atencion) / 4 >= 4
                        THEN 1 ELSE 0 END), 0)
                        AS respuestas_satisfactorias
                FROM {operaciones}.encuestas AS e
                LEFT JOIN {operaciones}.encuesta_respuestas AS r
                    ON r.encuesta_id = e.id
                """
            )

            conteos = cursor.fetchone()

        completadas = int(conteos["encuestas_completadas"])
        enviadas = int(conteos["encuestas_enviadas"])

        return {
            "disponible": True,
            "total_encuestas": int(conteos["total_encuestas"]),
            "encuestas_completadas": completadas,
            "encuestas_enviadas": enviadas,
            "satisfaccion_promedio": round(
                float(conteos["satisfaccion_promedio"]), 2),
            "promedio_producto": round(
                float(conteos["promedio_producto"]), 2),
            "promedio_entrega": round(
                float(conteos["promedio_entrega"]), 2),
            "promedio_atencion": round(
                float(conteos["promedio_atencion"]), 2),
            "recomendacion_porcentaje": round(
                (float(conteos["recomendaciones_ok"]) / completadas * 100)
                if completadas > 0 else 0.0, 2),
            "tasa_respuesta_porcentaje": round(
                (completadas / enviadas * 100) if enviadas > 0 else 0.0, 2),
            "respuestas_satisfactorias": int(
                conteos["respuestas_satisfactorias"]),
        }

    finally:

        conexion.close()


def obtener_metrica_reportes():
    """
    Métrica base del KPI-05: reportes gerenciales (Bloque 4).

    Solo cuentan las SOLICITUDES REALES de generación registradas en
    ``reportes_solicitudes`` (visitar el panel no genera reportes). El
    registro del resultado sucede al terminar de construir el archivo,
    por lo que nunca genera otro reporte (sin recursión).
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
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'reportes_solicitudes'
                """,
                (operaciones,),
            )

            if cursor.fetchone()["total"] == 0:
                return {
                    "disponible": False,
                    "total_solicitudes": None,
                    "solicitudes_exitosas": None,
                }

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_solicitudes,
                    COALESCE(SUM(CASE WHEN resultado = 'EXITO'
                                      THEN 1 ELSE 0 END), 0)
                        AS solicitudes_exitosas
                FROM {operaciones}.reportes_solicitudes
                """
            )

            conteos = cursor.fetchone()

        return {
            "disponible": True,
            "total_solicitudes": conteos["total_solicitudes"],
            "solicitudes_exitosas": conteos["solicitudes_exitosas"],
        }

    finally:

        conexion.close()


# ============================================================
# KPI-02 — EXACTITUD DE INVENTARIO (Bloque 3)
# ============================================================
#
# Fórmula:
#
#     KPI-02 = ( verificaciones donde el conteo coincide /
#                total de verificaciones físicas ) * 100
#
# Tabla real (creada en el Bloque 3):
#     inventario.verificaciones_fisicas
#         - coincide  (indica si stock_fisico == stock_sistema)
#
# NOTA DE DISEÑO (condición de autorización Bloque 3):
# La verificación conserva la fotografía del stock en el
# momento del conteo (stock_sistema, stock_fisico, diferencia);
# el KPI se calcula con la columna booleana `coincide` real.
# ============================================================


def obtener_metrica_verificaciones_fisicas():
    """
    Métrica base del KPI-02: conteos de verificaciones físicas.

    Consulta la tabla `verificaciones_fisicas` del esquema de
    inventario y devuelve únicamente los DOS conteos reales:

    - total_verificaciones:  filas de verificación registradas.
    - verificaciones_ok:     filas donde coincide = 1.

    Si la tabla aún no existe (primer arranque), devuelve
    "disponible": False para que el dashboard conserve el KPI
    como "Pendiente" sin inventar valores.
    """

    inventario = _esquema("DB_INVENTARIO")

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s "
                "  AND TABLE_NAME = 'verificaciones_fisicas'",
                (inventario,),
            )
            if cursor.fetchone()["total"] == 0:
                return {
                    "disponible": False,
                    "total_verificaciones": 0,
                    "verificaciones_ok": 0,
                }

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_verificaciones,
                    COALESCE(SUM(CASE WHEN coincide = 1
                                      THEN 1 ELSE 0 END), 0)
                        AS verificaciones_ok
                FROM {inventario}.verificaciones_fisicas
                """
            )
            conteos = cursor.fetchone()

        return {
            "disponible": True,
            "total_verificaciones": conteos["total_verificaciones"],
            "verificaciones_ok": conteos["verificaciones_ok"],
        }
    finally:
        conexion.close()


# ============================================================
# KPI-03 — ACCESO A INFORMACIÓN DE PRODUCTO (Bloque 3)
# ============================================================
#
# Fórmula:
#
#     KPI-03 = ( consultas EXITO / total de consultas ) * 100
#
# Tabla real (creada en el Bloque 3):
#     comercio.consultas_producto
#         - resultado  (ENUM 'EXITO' / 'FALLO')
#         - sku        (recurso solicitado)
#
# NOTA DE DISEÑO (condición de autorización Bloque 3):
# La tabla acumula SOLO intentos funcionales de consulta del
# cliente sobre un SKU real; nunca se registran assets ni
# navegación genérica como consultas artificiales.
# ============================================================


def obtener_metrica_consultas_producto():
    """
    Métrica base del KPI-03: conteos de consultas de producto.

    Devuelve únicamente los DOS conteos reales:

    - total_consultas:     filas en `consultas_producto`.
    - consultas_exitosas:  filas con resultado = 'EXITO'.

    El porcentaje (y la meta ≥ 95 %) se calcula en services.py.
    """

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s "
                "  AND TABLE_NAME = 'consultas_producto'",
                (comercio,),
            )
            if cursor.fetchone()["total"] == 0:
                return {
                    "disponible": False,
                    "total_consultas": 0,
                    "consultas_exitosas": 0,
                }

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_consultas,
                    COALESCE(SUM(CASE WHEN resultado = 'EXITO'
                                      THEN 1 ELSE 0 END), 0)
                        AS consultas_exitosas
                FROM {comercio}.consultas_producto
                """
            )
            conteos = cursor.fetchone()

        return {
            "disponible": True,
            "total_consultas": conteos["total_consultas"],
            "consultas_exitosas": conteos["consultas_exitosas"],
        }
    finally:
        conexion.close()


# ============================================================
# KPI-06 — ARTÍCULOS FAVORITOS DEL CLIENTE (Bloque 3)
# ============================================================
#
# Fórmula:
#
#     KPI-06 = ( operaciones de favoritos EXITOSAS /
#                total de operaciones de favoritos ) * 100
#
# Tabla real (creada en el Bloque 3):
#     comercio.favoritos_auditoria
#         - resultado  (ENUM 'EXITO' / 'FALLO')
#         - operacion  (ENUM 'AGREGAR' / 'QUITAR')
#
# NOTA DE DISEÑO (condición de autorización Bloque 3):
# `favoritos_auditoria` es append-only: registra cada intento
# real de agregar/quitar un favorito, sin modificar el
# historial existente. El KPI mide la eficacia real de estas
# operaciones.
# ============================================================


def obtener_metrica_favoritos():
    """
    Métrica base del KPI-06: conteos de operaciones de favoritos.

    Devuelve únicamente los DOS conteos reales:

    - total_favoritos_ops:  filas en `favoritos_auditoria`.
    - favoritos_exitosos:   filas con resultado = 'EXITO'.

    El porcentaje (y la meta ≥ 95 %) se calcula en services.py.
    """

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s "
                "  AND TABLE_NAME = 'favoritos_auditoria'",
                (comercio,),
            )
            if cursor.fetchone()["total"] == 0:
                return {
                    "disponible": False,
                    "total_favoritos_ops": 0,
                    "favoritos_exitosos": 0,
                }

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_favoritos_ops,
                    COALESCE(SUM(CASE WHEN resultado = 'EXITO'
                                      THEN 1 ELSE 0 END), 0)
                        AS favoritos_exitosos
                FROM {comercio}.favoritos_auditoria
                """
            )
            conteos = cursor.fetchone()

        return {
            "disponible": True,
            "total_favoritos_ops": conteos["total_favoritos_ops"],
            "favoritos_exitosos": conteos["favoritos_exitosos"],
        }
    finally:
        conexion.close()


# ============================================================
# KPI-10 — DISPONIBILIDAD DEL CONTENIDO EDUCATIVO (Bloque 3)
# ============================================================
#
# Fórmula:
#
#     KPI-10 = ( accesos EXITO / total de accesos ) * 100
#
# Tabla real (creada en el Bloque 3):
#     comercio.accesos_contenido
#         - resultado   (ENUM 'EXITO' / 'FALLO')
#         - slug_solicitado (recurso solicitado)
#
# NOTA DE DISEÑO (condición de autorización Bloque 3):
# `accesos_contenido` registra la evidencia real de cada
# consulta pública a la experiencia "Aprende"; el KPI mide la
# disponibilidad efectiva del contenido publicado.
# ============================================================


def obtener_metrica_accesos_contenido():
    """
    Métrica base del KPI-10: conteos de accesos a contenido.

    Devuelve únicamente los DOS conteos reales:

    - total_accesos:  filas en `accesos_contenido`.
    - accesos_exitosos:  filas con resultado = 'EXITO'.

    El porcentaje (y la meta ≥ 95 %) se calcula en services.py.
    """

    comercio = _esquema("DB_COMERCIO")

    conexion = conexion_comercio()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s "
                "  AND TABLE_NAME = 'accesos_contenido'",
                (comercio,),
            )
            if cursor.fetchone()["total"] == 0:
                return {
                    "disponible": False,
                    "total_accesos": 0,
                    "accesos_exitosos": 0,
                }

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_accesos,
                    COALESCE(SUM(CASE WHEN resultado = 'EXITO'
                                      THEN 1 ELSE 0 END), 0)
                        AS accesos_exitosos
                FROM {comercio}.accesos_contenido
                """
            )
            conteos = cursor.fetchone()

        return {
            "disponible": True,
            "total_accesos": conteos["total_accesos"],
            "accesos_exitosos": conteos["accesos_exitosos"],
        }
    finally:
        conexion.close()
