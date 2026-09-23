"""
Acceso a datos del módulo administrativo de Reportes Gerenciales (Bloque 4).

La auditoría KPI-05 vive en ``reportes_solicitudes``: solo cuentan las
GENERACIONES reales de reportes (no visitar la página). Cada intento de
generación registra EXITO o FALLO después de resolver el archivo.

Los datos de cada reporte se toman de las fuentes únicas ya existentes
(dashboard de KPI, caja, encuestas, pedidos); este repositorio solo
persiste la auditoría.
"""

import os
import re

from app.config.database import conexion_operaciones

_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")


def registrar_solicitud_reporte(*, tipo_reporte, formato, parametros,
                                usuario_solicitante_id, resultado,
                                error_tecnico=None):
    """Registra una solicitud REAL de generación de reporte (KPI-05).

    Nunca genera otro reporte ni consulta reportes: solo audita. Evita
    la recursión que afectaría al propio KPI-05.
    """
    operaciones = str(os.getenv("DB_OPERACIONES") or "").strip()
    if not operaciones or not _IDENTIFICADOR_SQL.fullmatch(operaciones):
        raise RuntimeError(
            "DB_OPERACIONES no contiene un esquema MySQL válido."
        )

    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {operaciones}.reportes_solicitudes
                    (tipo_reporte, formato, parametros,
                     usuario_solicitante_id, resultado, error_tecnico)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tipo_reporte, formato,
                 (parametros or "")[:500], usuario_solicitante_id,
                 resultado, (error_tecnico or "")[:300]),
            )
        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()