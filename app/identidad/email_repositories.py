"""Persistencia atómica para verificación de correo."""

from app.config.database import conexion_identidad
from app.shared.email.repositories import insertar_outbox


def insertar_solicitud(cursor, solicitud):
    cursor.execute(
        """
        INSERT INTO tokens_verificacion (
            id, usuario_id, proposito, token_hash, expira_en
        ) VALUES (%s, %s, 'VERIFICAR_CORREO', %s, %s)
        """,
        (
            solicitud["token_id"],
            solicitud["usuario_id"],
            solicitud["token_hash"],
            solicitud["expira_en"],
        ),
    )
    insertar_outbox(
        cursor,
        evento_id=solicitud["evento_id"],
        clave_idempotencia=solicitud["clave_idempotencia"],
        tipo="VERIFICAR_CORREO",
        destinatario=solicitud["correo"],
        plantilla="verificacion_correo",
        datos=solicitud["datos"],
        secreto_cifrado=solicitud["secreto_cifrado"],
    )


def buscar_cuenta_para_verificacion(correo):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.correo, u.correo_verificado,
                       u.requiere_verificacion_correo, u.estado,
                       p.nombres
                FROM usuarios u
                JOIN perfiles p ON p.usuario_id = u.id
                WHERE u.correo = %s
                LIMIT 1
                """,
                (correo,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def reemplazar_solicitud(solicitud):
    """Invalida pendientes y crea token+evento bajo un único commit."""

    conexion = conexion_identidad()
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM usuarios
                WHERE id = %s AND correo = %s AND estado = 'ACTIVO'
                  AND correo_verificado = 0
                LIMIT 1 FOR UPDATE
                """,
                (solicitud["usuario_id"], solicitud["correo"]),
            )
            if not cursor.fetchone():
                conexion.rollback()
                return False
            cursor.execute(
                """
                UPDATE correos_outbox co
                JOIN tokens_verificacion tv
                  ON co.clave_idempotencia = CONCAT('VERIFICAR_CORREO:', tv.id)
                SET co.estado = 'FALLIDO', co.ultimo_error = 'REEMPLAZADO',
                    co.secreto_cifrado = NULL, co.lease_token = NULL,
                    co.bloqueado_hasta = NULL
                WHERE tv.usuario_id = %s
                  AND tv.proposito = 'VERIFICAR_CORREO'
                  AND tv.consumido_en IS NULL
                  AND tv.invalidado_en IS NULL
                  AND co.estado IN ('PENDIENTE','REINTENTO')
                """,
                (solicitud["usuario_id"],),
            )
            cursor.execute(
                """
                UPDATE tokens_verificacion
                SET invalidado_en = NOW(6)
                WHERE usuario_id = %s AND proposito = 'VERIFICAR_CORREO'
                  AND consumido_en IS NULL AND invalidado_en IS NULL
                """,
                (solicitud["usuario_id"],),
            )
            insertar_solicitud(cursor, solicitud)
        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def inspeccionar_token(token_hash):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT tv.id, tv.usuario_id, tv.expira_en, tv.consumido_en,
                       tv.invalidado_en, (tv.expira_en > NOW(6)) AS vigente,
                       u.correo_verificado, u.estado, u.correo
                FROM tokens_verificacion tv
                JOIN usuarios u ON u.id = tv.usuario_id
                WHERE tv.token_hash = %s
                  AND tv.proposito = 'VERIFICAR_CORREO'
                LIMIT 1
                """,
                (token_hash,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def consumir_token(token_hash):
    """Consume exactamente una vez y actualiza el usuario atómicamente."""

    conexion = conexion_identidad()
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT tv.id, tv.usuario_id, tv.expira_en, tv.consumido_en,
                       tv.invalidado_en, (tv.expira_en > NOW(6)) AS vigente,
                       u.correo_verificado, u.estado
                FROM tokens_verificacion tv
                JOIN usuarios u ON u.id = tv.usuario_id
                WHERE tv.token_hash = %s
                  AND tv.proposito = 'VERIFICAR_CORREO'
                LIMIT 1 FOR UPDATE
                """,
                (token_hash,),
            )
            token = cursor.fetchone()
            if not token:
                conexion.rollback()
                return {"estado": "INVALIDO"}
            if token["estado"] != "ACTIVO" or token["invalidado_en"]:
                conexion.rollback()
                return {"estado": "INVALIDO"}
            if token["consumido_en"]:
                conexion.rollback()
                return {"estado": "CONSUMIDO"}
            if not token["vigente"]:
                conexion.rollback()
                return {"estado": "EXPIRADO"}

            cursor.execute(
                """
                UPDATE usuarios SET correo_verificado = 1
                WHERE id = %s AND estado = 'ACTIVO'
                """,
                (token["usuario_id"],),
            )
            cursor.execute(
                """
                UPDATE tokens_verificacion SET consumido_en = NOW(6)
                WHERE id = %s AND consumido_en IS NULL
                """,
                (token["id"],),
            )
            cursor.execute(
                """
                UPDATE tokens_verificacion SET invalidado_en = NOW(6)
                WHERE usuario_id = %s AND proposito = 'VERIFICAR_CORREO'
                  AND id <> %s AND consumido_en IS NULL
                  AND invalidado_en IS NULL
                """,
                (token["usuario_id"], token["id"]),
            )
        conexion.commit()
        return {
            "estado": "VERIFICADO",
            "usuario_id": token["usuario_id"],
            "ya_verificado": bool(token["correo_verificado"]),
        }
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
