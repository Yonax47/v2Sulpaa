"""Acceso a datos de la Configuración de Delivery.

Capa Repository: solo lee y escribe las tablas REALES del delivery
(``tarifas_delivery``) y expone la configuración de transportistas
(``transportistas``, ``tarifarios_transportista``,
``reglas_tarifa_transportista``, ``rangos_tarifa_transportista``,
``coberturas_transportista``) para consulta. No recalcula la fórmula:
eso vive en ``app.operaciones.services``.
"""
from app.config.database import conexion_operaciones


def obtener_tarifa_delivery_activa():
    """Tarifa de delivery local vigente y ACTIVA (o None)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM tarifas_delivery
                WHERE estado = 'ACTIVA'
                  AND (vigente_hasta IS NULL OR vigente_hasta >= NOW())
                ORDER BY vigente_desde DESC, creado_en DESC
                LIMIT 1
                """
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def listar_tarifas_delivery():
    """Historial de tarifas de delivery (lectura)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, nombre, tarifa_base, km_incluidos,
                       precio_km_adicional, peso_incluido_kg,
                       precio_kg_adicional, distancia_maxima_km,
                       peso_maximo_kg, monto_envio_gratis, estado,
                       vigente_desde, vigente_hasta, creado_en
                FROM tarifas_delivery
                ORDER BY vigente_desde DESC, creado_en DESC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def actualizar_tarifa_delivery(tarifa_id, datos):
    """Actualiza los campos editables de una tarifa de delivery."""
    columnas = (
        "nombre",
        "tarifa_base",
        "km_incluidos",
        "precio_km_adicional",
        "peso_incluido_kg",
        "precio_kg_adicional",
        "distancia_maxima_km",
        "peso_maximo_kg",
        "monto_envio_gratis",
    )
    asignaciones = ", ".join("%s = %%s" % columna for columna in columnas)
    valores = [datos.get(columna) for columna in columnas]
    valores.append(tarifa_id)

    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE tarifas_delivery SET %s WHERE id = %%s" % asignaciones,
                valores,
            )
        conexion.commit()
    except Exception:
        # Si el cambio no se confirma, se descarta por completo: la
        # conexión puede reutilizarse después dentro de la misma
        # solicitud y no debe arrastrar escrituras a medias.
        conexion.rollback()
        raise
    finally:
        conexion.close()


def listar_transportistas():
    """Transportistas registrados (lectura)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, codigo, nombre, telefono, estado
                FROM transportistas
                ORDER BY nombre ASC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def listar_tarifarios_transportista():
    """Tarifarios de transportista con su transportista (lectura)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT t.id, t.nombre, t.version, t.estado,
                       t.vigente_desde,
                       tr.nombre AS transportista
                FROM tarifarios_transportista t
                LEFT JOIN transportistas tr ON tr.id = t.transportista_id
                ORDER BY tr.nombre ASC, t.vigente_desde DESC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def listar_reglas_tarifa(tarifario_id):
    """Reglas de un tarifario con la cantidad de rangos (lectura)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.metodo_calculo, r.tarifa_base,
                       r.precio_kg_adicional, r.recargo_fijo,
                       r.peso_maximo_gramos, r.estado,
                       r.distrito_destino_id,
                       COUNT(rg.id) AS rangos
                FROM reglas_tarifa_transportista r
                LEFT JOIN rangos_tarifa_transportista rg
                       ON rg.regla_tarifa_id = r.id
                WHERE r.tarifario_id = %s
                GROUP BY r.id, r.metodo_calculo, r.tarifa_base,
                         r.precio_kg_adicional, r.recargo_fijo,
                         r.peso_maximo_gramos, r.estado,
                         r.distrito_destino_id
                ORDER BY r.tarifa_base ASC
                """,
                (tarifario_id,),
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def listar_coberturas_activas():
    """Coberturas ACTIVAS por servicio y distrito (lectura)."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.id, c.tipo_cobertura, c.estado,
                       c.distrito_id,
                       s.nombre AS servicio,
                       tr.nombre AS transportista
                FROM coberturas_transportista c
                LEFT JOIN servicios_transportista s
                       ON s.id = c.servicio_transportista_id
                LEFT JOIN transportistas tr
                       ON tr.id = s.transportista_id
                WHERE c.estado = 'ACTIVA'
                ORDER BY tr.nombre ASC, s.nombre ASC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()
