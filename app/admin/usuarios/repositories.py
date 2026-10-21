"""Acceso a datos del módulo administrativo de Usuarios y Roles.

Tablas reales (identidad):
- ``usuarios``       (cuenta: correo, password_hash, estado).
- ``perfiles``       (datos personales del titular).
- ``roles``          (catálogo: GERENTE, ADMINISTRADOR, ...).
- ``usuario_roles``  (vínculo N:M usuario<->rol con estado).

Todas las escrituras se hacen dentro de una única transacción
que confirma solo si TODO quedó grabado. Nunca se guarda un
usuario sin perfil, ni un rol sin su vínculo.
"""

import uuid

from app.config.database import conexion_identidad


def _nuevo_uuid():
    return str(uuid.uuid4())


def listar_roles():
    """Devuelve todos los roles ACTIVOS reales del catálogo."""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, codigo, nombre, descripcion
                FROM roles
                WHERE estado = 'ACTIVO'
                ORDER BY id ASC
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def _condiciones(filtros):
    """Construye el WHERE parametrizado (nunca concatena valores)."""
    clausulas = []
    params = []

    texto = (filtros.get("texto") or "").strip()
    if texto:
        clausulas.append(
            "(u.correo LIKE %s OR p.nombres LIKE %s "
            "OR p.apellido_paterno LIKE %s OR p.dni LIKE %s)"
        )
        patron = "%" + texto + "%"
        params.extend([patron, patron, patron, patron])

    estado = (filtros.get("estado") or "").strip()
    if estado:
        clausulas.append("u.estado = %s")
        params.append(estado)

    rol = (filtros.get("rol") or "").strip()
    if rol:
        clausulas.append(
            "EXISTS ("
            "  SELECT 1 FROM usuario_roles ur"
            "  JOIN roles r ON r.id = ur.rol_id"
            "  WHERE ur.usuario_id = u.id AND ur.estado = 'ACTIVO'"
            "    AND r.codigo = %s AND r.estado = 'ACTIVO'"
            ")"
        )
        params.append(rol)

    return clausulas, params


def listar_usuarios(filtros=None, limite=25, offset=0):
    """Lista usuarios con su perfil y sus roles ACTIVOS agregados."""
    filtros = dict(filtros or {})
    clausulas, params = _condiciones(filtros)
    where = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""

    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    u.id,
                    u.correo,
                    u.estado,
                    u.correo_verificado,
                    u.ultimo_acceso_en,
                    u.creado_en,
                    p.nombres,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.dni,
                    p.telefono,
                    (
                        SELECT GROUP_CONCAT(r.codigo ORDER BY r.id)
                        FROM usuario_roles ur
                        JOIN roles r ON r.id = ur.rol_id
                        WHERE ur.usuario_id = u.id
                          AND ur.estado = 'ACTIVO'
                          AND r.estado = 'ACTIVO'
                    ) AS roles_csv
                FROM usuarios AS u
                LEFT JOIN perfiles AS p ON p.usuario_id = u.id
                {where}
                ORDER BY u.creado_en DESC
                LIMIT %s OFFSET %s
                """.format(where=where),
                params + [int(limite), int(offset)],
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def contar_usuarios(filtros=None):
    """Cuenta usuarios que cumplen el filtro (para paginar)."""
    clausulas, params = _condiciones(filtros or {})
    where = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM usuarios AS u
                LEFT JOIN perfiles AS p ON p.usuario_id = u.id
                {where}
                """.format(where=where),
                params,
            )
            return cursor.fetchone()["total"]
    finally:
        conexion.close()


def obtener_usuario(usuario_id):
    """Devuelve un usuario con su perfil y la lista de roles."""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    u.id,
                    u.correo,
                    u.estado,
                    u.correo_verificado,
                    u.ultimo_acceso_en,
                    u.creado_en,
                    p.nombres,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.dni,
                    p.telefono
                FROM usuarios AS u
                LEFT JOIN perfiles AS p ON p.usuario_id = u.id
                WHERE u.id = %s
                LIMIT 1
                """,
                (usuario_id,),
            )
            usuario = cursor.fetchone()
            if not usuario:
                return None

            cursor.execute(
                """
                SELECT ur.id, ur.rol_id, r.codigo, r.nombre
                FROM usuario_roles AS ur
                JOIN roles AS r ON r.id = ur.rol_id
                WHERE ur.usuario_id = %s AND ur.estado = 'ACTIVO'
                ORDER BY r.id ASC
                """,
                (usuario_id,),
            )
            usuario["roles"] = cursor.fetchall()
            return usuario
    finally:
        conexion.close()


def correo_existe(correo, excepto_id=None):
    """True si el correo ya está tomado por otra cuenta."""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            if excepto_id:
                cursor.execute(
                    "SELECT id FROM usuarios WHERE correo = %s AND id <> %s LIMIT 1",
                    (correo, excepto_id),
                )
            else:
                cursor.execute(
                    "SELECT id FROM usuarios WHERE correo = %s LIMIT 1",
                    (correo,),
                )
            return cursor.fetchone() is not None
    finally:
        conexion.close()


def dni_existe(dni, excepto_usuario_id=None):
    """True si el DNI ya está tomado por otro perfil."""
    if not dni:
        return False
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            if excepto_usuario_id:
                cursor.execute(
                    "SELECT id FROM perfiles WHERE dni = %s AND usuario_id <> %s LIMIT 1",
                    (dni, excepto_usuario_id),
                )
            else:
                cursor.execute(
                    "SELECT id FROM perfiles WHERE dni = %s LIMIT 1",
                    (dni,),
                )
            return cursor.fetchone() is not None
    finally:
        conexion.close()


def crear_usuario_con_roles(
    usuario_id,
    perfil_id,
    correo,
    password_hash,
    nombres,
    apellido_paterno,
    apellido_materno,
    dni,
    telefono,
    rol_ids,
    asignado_por=None,
):
    """Crea cuenta + perfil + vínculos de rol en una sola transacción.

    Si cualquiera de las inserciones falla, ninguna queda registrada.
    """
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO usuarios (
                    id, correo, password_hash, estado, correo_verificado
                )
                VALUES (%s, %s, %s, 'ACTIVO', FALSE)
                """,
                (usuario_id, correo, password_hash),
            )

            cursor.execute(
                """
                INSERT INTO perfiles (
                    id, usuario_id, nombres, apellido_paterno,
                    apellido_materno, dni, telefono
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    perfil_id,
                    usuario_id,
                    nombres,
                    apellido_paterno,
                    apellido_materno,
                    dni,
                    telefono,
                ),
            )

            for rol_id in rol_ids or []:
                cursor.execute(
                    """
                    INSERT INTO usuario_roles (
                        id, usuario_id, rol_id,
                        asignado_por_usuario_id, estado
                    )
                    VALUES (%s, %s, %s, %s, 'ACTIVO')
                    """,
                    (
                        _nuevo_uuid(),
                        usuario_id,
                        rol_id,
                        asignado_por,
                    ),
                )

        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def actualizar_estado_usuario(usuario_id, estado):
    """Activa o desactiva una cuenta. Devuelve filas afectadas."""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE usuarios SET estado = %s WHERE id = %s",
                (estado, usuario_id),
            )
            afectadas = cursor.rowcount
        conexion.commit()
        return afectadas
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def reemplazar_roles(usuario_id, rol_ids, asignado_por=None):
    """Deja al usuario EXACTAMENTE con los roles indicados.

    Los vínculos que ya no aplican pasan a estado INACTIVO (no se
    borran, para conservar el histórico). Los que ya existían se
    reactivan. Es una sola transacción.
    """
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            # 1. Desactivar todos los vínculos actuales.
            cursor.execute(
                "UPDATE usuario_roles SET estado = 'INACTIVO' "
                "WHERE usuario_id = %s AND estado = 'ACTIVO'",
                (usuario_id,),
            )

            # 2. Reactivar o crear los roles solicitados.
            for rol_id in rol_ids or []:
                cursor.execute(
                    "SELECT id FROM usuario_roles "
                    "WHERE usuario_id = %s AND rol_id = %s LIMIT 1",
                    (usuario_id, rol_id),
                )
                existente = cursor.fetchone()
                if existente:
                    cursor.execute(
                        "UPDATE usuario_roles SET estado = 'ACTIVO', "
                        "asignado_por_usuario_id = %s WHERE id = %s",
                        (asignado_por, existente["id"]),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO usuario_roles "
                        "(id, usuario_id, rol_id, asignado_por_usuario_id, estado) "
                        "VALUES (%s, %s, %s, %s, 'ACTIVO')",
                        (_nuevo_uuid(), usuario_id, rol_id, asignado_por),
                    )

        conexion.commit()
        return True
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
