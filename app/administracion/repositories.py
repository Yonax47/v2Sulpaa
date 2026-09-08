"""
Repositorio del módulo Administración de SULPAA V2.
Acceso a datos del perfil de administradores.
"""

from app.config.database import conexion_identidad


def obtener_perfil_administrador(usuario_id):
    """
    Obtiene los datos de perfil de un administrador.
    """
    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    u.id AS usuario_id,
                    u.correo,
                    u.rol,
                    u.ultimo_acceso_en,
                    u.creado_en,

                    p.nombres,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.telefono

                FROM usuarios AS u
                LEFT JOIN perfiles AS p
                    ON p.usuario_id = u.id

                WHERE
                    u.id = %s
                    AND u.rol = 'ADMIN'
                    AND u.estado = 'ACTIVO'

                LIMIT 1
                """,
                (usuario_id,),
            )
            return cursor.fetchone()

    finally:
        conexion.close()


def actualizar_perfil_administrador(
    usuario_id,
    nombres,
    apellido_paterno,
    apellido_materno,
    telefono,
):
    """
    Actualiza los datos editables del perfil de administrador.
    """
    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE perfiles
                SET
                    nombres = %s,
                    apellido_paterno = %s,
                    apellido_materno = %s,
                    telefono = %s
                WHERE usuario_id = %s
                """,
                (
                    nombres,
                    apellido_paterno,
                    apellido_materno,
                    telefono,
                    usuario_id,
                ),
            )

        conexion.commit()
        return True

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()