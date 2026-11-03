"""Persistencia del perfil, siempre acotada al usuario autenticado."""

from app.config.database import conexion_identidad


def obtener_perfil(usuario_id):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id AS usuario_id, u.correo, u.correo_verificado,
                       u.estado, p.nombres, p.apellido_paterno,
                       p.apellido_materno, p.dni, p.telefono
                FROM usuarios AS u
                INNER JOIN perfiles AS p ON p.usuario_id = u.id
                WHERE u.id = %s AND u.estado = 'ACTIVO'
                LIMIT 1
                """,
                (usuario_id,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def actualizar_telefono(usuario_id, telefono):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE perfiles SET telefono = %s WHERE usuario_id = %s",
                (telefono, usuario_id),
            )
        conexion.commit()
        # El servicio comprobó antes que el perfil existe y está activo.
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def marcar_direccion_principal(usuario_id, direccion_id):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM direcciones
                WHERE id = %s AND usuario_id = %s AND estado = 'ACTIVA'
                LIMIT 1 FOR UPDATE
                """,
                (direccion_id, usuario_id),
            )
            if not cursor.fetchone():
                conexion.rollback()
                return False
            cursor.execute(
                "UPDATE direcciones SET es_principal = 0 WHERE usuario_id = %s",
                (usuario_id,),
            )
            cursor.execute(
                """
                UPDATE direcciones SET es_principal = 1
                WHERE id = %s AND usuario_id = %s AND estado = 'ACTIVA'
                """,
                (direccion_id, usuario_id),
            )
        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def desactivar_direccion(usuario_id, direccion_id):
    """Desactiva sin borrar y reasigna principal si corresponde."""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, es_principal FROM direcciones
                WHERE id = %s AND usuario_id = %s AND estado = 'ACTIVA'
                LIMIT 1 FOR UPDATE
                """,
                (direccion_id, usuario_id),
            )
            direccion = cursor.fetchone()
            if not direccion:
                conexion.rollback()
                return False
            cursor.execute(
                """
                UPDATE direcciones SET estado = 'INACTIVA', es_principal = 0
                WHERE id = %s AND usuario_id = %s
                """,
                (direccion_id, usuario_id),
            )
            if direccion.get("es_principal"):
                cursor.execute(
                    """
                    SELECT id FROM direcciones
                    WHERE usuario_id = %s AND estado = 'ACTIVA'
                    ORDER BY creado_en DESC, id DESC LIMIT 1
                    """,
                    (usuario_id,),
                )
                siguiente = cursor.fetchone()
                if siguiente:
                    cursor.execute(
                        """
                        UPDATE direcciones SET es_principal = 1
                        WHERE id = %s AND usuario_id = %s
                        """,
                        (siguiente["id"], usuario_id),
                    )
        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def listar_facturacion(usuario_id):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, tipo, dni, ruc, nombre_facturacion, razon_social,
                       distrito_id, direccion_fiscal, es_predeterminado,
                       creado_en
                FROM datos_facturacion
                WHERE usuario_id = %s AND estado = 'ACTIVO'
                ORDER BY es_predeterminado DESC, creado_en DESC, id DESC
                """,
                (usuario_id,),
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def marcar_facturacion_predeterminada(usuario_id, facturacion_id):
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM datos_facturacion
                WHERE id = %s AND usuario_id = %s AND estado = 'ACTIVO'
                LIMIT 1 FOR UPDATE
                """,
                (facturacion_id, usuario_id),
            )
            if not cursor.fetchone():
                conexion.rollback()
                return False
            cursor.execute(
                """
                UPDATE datos_facturacion SET es_predeterminado = 0
                WHERE usuario_id = %s AND estado = 'ACTIVO'
                """,
                (usuario_id,),
            )
            cursor.execute(
                """
                UPDATE datos_facturacion SET es_predeterminado = 1
                WHERE id = %s AND usuario_id = %s AND estado = 'ACTIVO'
                """,
                (facturacion_id, usuario_id),
            )
        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def desactivar_facturacion(usuario_id, facturacion_id):
    """Desactiva sin borrar y conserva una opción predeterminada activa."""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, es_predeterminado FROM datos_facturacion
                WHERE id = %s AND usuario_id = %s AND estado = 'ACTIVO'
                LIMIT 1 FOR UPDATE
                """,
                (facturacion_id, usuario_id),
            )
            registro = cursor.fetchone()
            if not registro:
                conexion.rollback()
                return False

            cursor.execute(
                """
                UPDATE datos_facturacion
                SET estado = 'INACTIVO', es_predeterminado = 0
                WHERE id = %s AND usuario_id = %s
                """,
                (facturacion_id, usuario_id),
            )

            if registro.get("es_predeterminado"):
                cursor.execute(
                    """
                    SELECT id FROM datos_facturacion
                    WHERE usuario_id = %s AND estado = 'ACTIVO'
                    ORDER BY creado_en DESC, id DESC LIMIT 1
                    """,
                    (usuario_id,),
                )
                siguiente = cursor.fetchone()
                if siguiente:
                    cursor.execute(
                        """
                        UPDATE datos_facturacion
                        SET es_predeterminado = 1
                        WHERE id = %s AND usuario_id = %s
                        """,
                        (siguiente["id"], usuario_id),
                    )
        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
