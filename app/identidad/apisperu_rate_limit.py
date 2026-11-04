"""Contador InnoDB compartido para consultas a APIsPERU."""

from dataclasses import dataclass
from datetime import timedelta

from app.config.database import crear_conexion, nombre_esquema


@dataclass(frozen=True)
class ResultadoLimite:
    permitido: bool
    reintentar_en: int = 0


def consumir_limite_apisperu(
    *, operacion, clave_hash, maximo, ventana_segundos
):
    """Consume un intento usando una fila serializada con ``FOR UPDATE``.

    La conexión se confirma y cierra antes de que el llamador contacte al
    proveedor. Un error se propaga para que la capa APIsPERU falle cerrada.
    """

    operacion = str(operacion or "").strip().upper()
    if operacion not in {"DNI", "RUC"}:
        raise ValueError("Operación APIsPERU no permitida.")
    if not isinstance(clave_hash, bytes) or len(clave_hash) != 32:
        raise ValueError("La clave HMAC debe contener 32 bytes.")

    maximo = max(1, int(maximo))
    ventana_segundos = max(1, int(ventana_segundos))
    conexion = crear_conexion(nombre_esquema("DB_IDENTIDAD"), reutilizar=False)
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute("SELECT NOW(6) AS ahora")
            ahora = cursor.fetchone()["ahora"]
            cursor.execute(
                """
                INSERT INTO limites_consulta_externa (
                    servicio, operacion, clave_hash, intentos,
                    ventana_inicia_en, ultimo_intento_en
                ) VALUES ('APISPERU', %s, %s, 0, %s, %s)
                ON DUPLICATE KEY UPDATE servicio = servicio
                """,
                (operacion, clave_hash, ahora, ahora),
            )
            cursor.execute(
                """
                SELECT intentos, ventana_inicia_en, ultimo_intento_en
                FROM limites_consulta_externa
                WHERE servicio = 'APISPERU'
                  AND operacion = %s AND clave_hash = %s
                FOR UPDATE
                """,
                (operacion, clave_hash),
            )
            fila = cursor.fetchone()
            if not fila:
                raise RuntimeError("No se pudo bloquear el contador APIsPERU.")

            # Tomar el reloj después de esperar el bloqueo, no antes: otra
            # transacción podría haber iniciado una ventana más reciente.
            cursor.execute("SELECT NOW(6) AS ahora")
            ahora = cursor.fetchone()["ahora"]

            inicio = fila["ventana_inicia_en"]
            fin = inicio + timedelta(seconds=ventana_segundos)
            if ahora >= fin:
                intentos = 0
                inicio = ahora
                fin = ahora + timedelta(seconds=ventana_segundos)
            else:
                intentos = int(fila["intentos"] or 0)

            if intentos >= maximo:
                conexion.rollback()
                espera = max(1, int((fin - ahora).total_seconds()))
                return ResultadoLimite(False, espera)

            cursor.execute(
                """
                UPDATE limites_consulta_externa
                SET intentos = %s,
                    ventana_inicia_en = %s,
                    ultimo_intento_en = %s
                WHERE servicio = 'APISPERU'
                  AND operacion = %s AND clave_hash = %s
                """,
                (intentos + 1, inicio, ahora, operacion, clave_hash),
            )
        conexion.commit()
        return ResultadoLimite(True)
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
