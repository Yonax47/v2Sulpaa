"""Persistencia del outbox y límites compartidos en Identidad."""

import json
import uuid
from datetime import timedelta

from app.config.database import conexion_identidad


def insertar_outbox(
    cursor,
    *,
    evento_id,
    clave_idempotencia,
    tipo,
    destinatario,
    plantilla,
    datos,
    secreto_cifrado=None,
):
    """Inserta idempotentemente usando un cursor de la transacción dueña."""

    cursor.execute(
        """
        INSERT INTO correos_outbox (
            id, clave_idempotencia, tipo, destinatario, plantilla,
            datos_json, secreto_cifrado, estado, proximo_intento_en
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDIENTE', NOW(6))
        ON DUPLICATE KEY UPDATE id = id
        """,
        (
            evento_id,
            clave_idempotencia,
            tipo,
            destinatario,
            plantilla,
            json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
            secreto_cifrado,
        ),
    )
    return cursor.rowcount == 1


def insertar_confirmacion_pedido(
    cursor, *, pedido_id, numero_pedido, usuario_id, items, total, fecha
):
    """Crea el evento dentro de la misma transacción multiesquema."""

    cursor.execute(
        """
        SELECT u.correo, p.nombres
        FROM usuarios u
        JOIN perfiles p ON p.usuario_id = u.id
        WHERE u.id = %s AND u.estado = 'ACTIVO'
        LIMIT 1
        """,
        (usuario_id,),
    )
    usuario = cursor.fetchone()
    if not usuario:
        raise RuntimeError("No se encontró destinatario activo del pedido.")
    datos_items = [
        {
            "nombre": str(item.get("nombre") or "Artículo")[:180],
            "cantidad": int(item.get("cantidad") or 0),
            "precio": float(item.get("precio") or 0),
        }
        for item in items
    ]
    return insertar_outbox(
        cursor,
        evento_id=str(uuid.uuid4()),
        clave_idempotencia=f"PEDIDO_CONFIRMADO:{pedido_id}",
        tipo="PEDIDO_CONFIRMADO",
        destinatario=usuario["correo"],
        plantilla="pedido_confirmado",
        datos={
            "nombre": str(usuario.get("nombres") or "cliente")[:120],
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "fecha": fecha,
            "estado": "Confirmado",
            "items": datos_items,
            "total": float(total),
            "order_path": f"/pedidos/{pedido_id}",
        },
    )


def consumir_limites_persistentes(
    claves, *, maximo, ventana_segundos, minimo_intervalo_segundos
):
    """Comprueba e incrementa varias claves bajo bloqueos ``FOR UPDATE``."""

    claves = sorted(set(claves), key=lambda item: (item[0], item[1]))
    conexion = conexion_identidad()
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute("SELECT NOW(6) AS ahora")
            ahora = cursor.fetchone()["ahora"]
            for alcance, clave_hash in claves:
                cursor.execute(
                    """
                    INSERT IGNORE INTO limites_correo (
                        alcance, clave_hash, intentos,
                        ventana_inicia_en, ultimo_intento_en
                    ) VALUES (%s, %s, 0, %s, %s)
                    """,
                    (alcance, clave_hash, ahora, ahora),
                )

            filas = []
            for alcance, clave_hash in claves:
                cursor.execute(
                    """
                    SELECT alcance, clave_hash, intentos,
                           ventana_inicia_en, ultimo_intento_en
                    FROM limites_correo
                    WHERE alcance = %s AND clave_hash = %s
                    FOR UPDATE
                    """,
                    (alcance, clave_hash),
                )
                filas.append(cursor.fetchone())

            for fila in filas:
                inicio = fila["ventana_inicia_en"]
                ultimo = fila["ultimo_intento_en"]
                en_ventana = inicio > ahora - timedelta(seconds=ventana_segundos)
                if en_ventana and fila["intentos"] >= maximo:
                    conexion.rollback()
                    return False
                if fila["intentos"] and ultimo > ahora - timedelta(
                    seconds=minimo_intervalo_segundos
                ):
                    conexion.rollback()
                    return False

            for fila in filas:
                reiniciar = fila["ventana_inicia_en"] <= ahora - timedelta(
                    seconds=ventana_segundos
                )
                cursor.execute(
                    """
                    UPDATE limites_correo
                    SET intentos = %s,
                        ventana_inicia_en = %s,
                        ultimo_intento_en = %s
                    WHERE alcance = %s AND clave_hash = %s
                    """,
                    (
                        1 if reiniciar else fila["intentos"] + 1,
                        ahora if reiniciar else fila["ventana_inicia_en"],
                        ahora,
                        fila["alcance"],
                        fila["clave_hash"],
                    ),
                )
        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def reclamar_lote(limite, lease_token, lease_seconds, max_intentos):
    """Reclama trabajos vencidos y devuelve la conexión antes del proveedor."""

    conexion = conexion_identidad()
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE correos_outbox
                SET estado = 'FALLIDO', ultimo_error = 'MAX_INTENTOS',
                    secreto_cifrado = NULL, lease_token = NULL,
                    bloqueado_hasta = NULL
                WHERE estado = 'PROCESANDO' AND bloqueado_hasta < NOW(6)
                  AND intentos >= %s
                """,
                (int(max_intentos),),
            )
            cursor.execute(
                """
                SELECT id
                FROM correos_outbox
                WHERE (
                    estado IN ('PENDIENTE','REINTENTO')
                    AND proximo_intento_en <= NOW(6)
                    AND intentos < %s
                ) OR (
                    estado = 'PROCESANDO'
                    AND bloqueado_hasta < NOW(6)
                    AND intentos < %s
                )
                ORDER BY creado_en ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (int(max_intentos), int(max_intentos), int(limite)),
            )
            ids = [fila["id"] for fila in cursor.fetchall()]
            if not ids:
                conexion.commit()
                return []
            marcadores = ",".join(["%s"] * len(ids))
            cursor.execute(
                f"""
                UPDATE correos_outbox
                SET estado = 'PROCESANDO', lease_token = %s,
                    bloqueado_hasta = DATE_ADD(NOW(6), INTERVAL %s SECOND),
                    intentos = intentos + 1
                WHERE id IN ({marcadores})
                """,
                (lease_token, int(lease_seconds), *ids),
            )
            cursor.execute(
                f"""
                SELECT id, clave_idempotencia, tipo, destinatario, plantilla,
                       datos_json, secreto_cifrado, intentos
                FROM correos_outbox
                WHERE id IN ({marcadores}) AND lease_token = %s
                ORDER BY creado_en ASC
                """,
                (*ids, lease_token),
            )
            filas = cursor.fetchall()
        conexion.commit()
        return filas
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def marcar_enviado(evento_id, lease_token, proveedor_id):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE correos_outbox
                SET estado = 'ENVIADO', enviado_en = NOW(6),
                    proveedor_id = %s, ultimo_error = NULL,
                    secreto_cifrado = NULL, lease_token = NULL,
                    bloqueado_hasta = NULL
                WHERE id = %s AND estado = 'PROCESANDO' AND lease_token = %s
                """,
                (proveedor_id, evento_id, lease_token),
            )
            actualizado = cursor.rowcount == 1
        conexion.commit()
        return actualizado
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def marcar_fallo(
    evento_id,
    lease_token,
    *,
    permanente,
    error_code,
    proximo_intento_segundos=None,
):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE correos_outbox
                SET estado = %s,
                    proximo_intento_en = DATE_ADD(NOW(6), INTERVAL %s SECOND),
                    ultimo_error = %s, lease_token = NULL,
                    bloqueado_hasta = NULL,
                    secreto_cifrado = CASE WHEN %s THEN NULL ELSE secreto_cifrado END
                WHERE id = %s AND estado = 'PROCESANDO' AND lease_token = %s
                """,
                (
                    "FALLIDO" if permanente else "REINTENTO",
                    int(proximo_intento_segundos or 0),
                    str(error_code or "UNKNOWN")[:80],
                    1 if permanente else 0,
                    evento_id,
                    lease_token,
                ),
            )
            actualizado = cursor.rowcount == 1
        conexion.commit()
        return actualizado
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
