"""
Repositorio del módulo Identidad.

Este archivo contiene únicamente operaciones de acceso a datos
relacionadas con usuarios y perfiles.

No debe contener lógica de negocio ni código de rutas Flask.
"""

from app.config.database import conexion_identidad


def buscar_usuario_por_correo(correo: str):
    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    correo,
                    password_hash,
                    estado,
                    rol,
                    correo_verificado,
                    ultimo_acceso_en,
                    creado_en,
                    actualizado_en
                FROM usuarios
                WHERE correo = %s
                LIMIT 1
            """
            cursor.execute(sql, (correo,))
            return cursor.fetchone()

    finally:
        conexion.close()


def crear_usuario_y_perfil(
    usuario_id: str,
    perfil_id: str,
    correo: str,
    password_hash: str,
    nombres: str,
    apellido_paterno: str,
    apellido_materno: str | None,
    dni: str | None,
    telefono: str,
):
    """
    Crea usuario y perfil dentro de una única transacción.

    Si alguna inserción falla, ninguna de las dos queda registrada.
    """
    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            sql_usuario = """
                INSERT INTO usuarios (
                    id,
                    correo,
                    password_hash,
                    estado,
                    correo_verificado
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'ACTIVO',
                    FALSE
                )
            """

            cursor.execute(
                sql_usuario,
                (
                    usuario_id,
                    correo,
                    password_hash,
                ),
            )

            sql_perfil = """
                INSERT INTO perfiles (
                    id,
                    usuario_id,
                    nombres,
                    apellido_paterno,
                    apellido_materno,
                    dni,
                    telefono
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """

            cursor.execute(
                sql_perfil,
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

        conexion.commit()

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def actualizar_ultimo_acceso(usuario_id: str):
    """
    Actualiza la fecha y hora del último acceso del usuario.

    Esta información será útil posteriormente para:
    - auditoría,
    - seguridad,
    - panel administrativo.
    """

    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            sql = """
                UPDATE usuarios
                SET ultimo_acceso_en = NOW()
                WHERE id = %s
            """

            cursor.execute(
                sql,
                (usuario_id,),
            )

        conexion.commit()

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()

# ============================================================
# DATOS DEL CLIENTE PARA CHECKOUT
# ============================================================

def obtener_datos_checkout_usuario(usuario_id):
    """
    Obtiene los datos personales, dirección principal
    y facturación del usuario autenticado.
    """

    conexion = conexion_identidad()

    try:

        with conexion.cursor() as cursor:

            # ------------------------------------------------
            # 1. Usuario + perfil
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    u.id AS usuario_id,
                    u.correo,

                    p.nombres,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.dni,
                    p.telefono

                FROM usuarios AS u

                LEFT JOIN perfiles AS p
                    ON p.usuario_id = u.id

                WHERE
                    u.id = %s
                    AND u.estado = 'ACTIVO'

                LIMIT 1
                """,
                (
                    usuario_id,
                ),
            )

            cliente = cursor.fetchone()

            if not cliente:

                return None

            # ------------------------------------------------
            # 2. Dirección principal
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    distrito_id,
                    alias,
                    direccion,
                    referencia,
                    codigo_postal,
                    latitud,
                    longitud,
                    es_principal

                FROM direcciones

                WHERE
                    usuario_id = %s
                    AND estado = 'ACTIVA'

                ORDER BY
                    es_principal DESC,
                    creado_en ASC

                LIMIT 1
                """,
                (
                    usuario_id,
                ),
            )

            direccion = cursor.fetchone()

            # ------------------------------------------------
            # 3. Datos de facturación predeterminados
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    tipo,
                    dni,
                    ruc,
                    nombre_facturacion,
                    razon_social,
                    distrito_id,
                    direccion_fiscal,
                    es_predeterminado

                FROM datos_facturacion

                WHERE
                    usuario_id = %s
                    AND estado = 'ACTIVO'

                ORDER BY
                    es_predeterminado DESC,
                    creado_en ASC

                LIMIT 1
                """,
                (
                    usuario_id,
                ),
            )

            facturacion = cursor.fetchone()

            return {
                "cliente":
                    cliente,

                "direccion":
                    direccion,

                "facturacion":
                    facturacion,
            }

    finally:

        conexion.close()
# ============================================================
# UBICACIÓN GEOGRÁFICA
# ============================================================

def obtener_departamentos_activos():
    """
    Obtiene todos los departamentos activos.
    """

    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    nombre
                FROM departamentos
                WHERE estado = 'ACTIVO'
                ORDER BY nombre ASC
                """
            )

            return cursor.fetchall()

    finally:
        conexion.close()


def obtener_provincias_por_departamento(
    departamento_id,
):
    """
    Obtiene las provincias activas
    de un departamento.
    """

    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    nombre
                FROM provincias
                WHERE
                    departamento_id = %s
                    AND estado = 'ACTIVO'
                ORDER BY nombre ASC
                """,
                (
                    departamento_id,
                ),
            )

            return cursor.fetchall()

    finally:
        conexion.close()


def obtener_distritos_por_provincia(
    provincia_id,
):
    """
    Obtiene los distritos activos
    de una provincia.
    """

    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    nombre
                FROM distritos
                WHERE
                    provincia_id = %s
                    AND estado = 'ACTIVO'
                ORDER BY nombre ASC
                """,
                (
                    provincia_id,
                ),
            )

            return cursor.fetchall()

    finally:
        conexion.close()

# ============================================================
# GUARDAR DIRECCIÓN DEL USUARIO
# ============================================================

def crear_direccion_usuario(
    direccion_id,
    usuario_id,
    distrito_id,
    alias,
    direccion,
    referencia,
    es_principal=True,
):
    """
    Registra una nueva dirección para el usuario.

    Si se registra como principal, las demás direcciones
    del usuario dejan de ser principales.
    """

    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            # Si será la dirección principal,
            # quitamos esa condición a las anteriores.
            if es_principal:

                cursor.execute(
                    """
                    UPDATE direcciones
                    SET es_principal = 0
                    WHERE usuario_id = %s
                    """,
                    (
                        usuario_id,
                    ),
                )

            cursor.execute(
                """
                INSERT INTO direcciones (
                    id,
                    usuario_id,
                    distrito_id,
                    alias,
                    direccion,
                    referencia,
                    es_principal,
                    estado
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'ACTIVA'
                )
                """,
                (
                    direccion_id,
                    usuario_id,
                    distrito_id,
                    alias,
                    direccion,
                    referencia,
                    1 if es_principal else 0,
                ),
            )

        conexion.commit()

        return True

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def buscar_distrito_activo(
    distrito_id,
):
    """
    Comprueba que el distrito exista y esté activo.
    """

    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    provincia_id,
                    nombre
                FROM distritos
                WHERE
                    id = %s
                    AND estado = 'ACTIVO'
                LIMIT 1
                """,
                (
                    distrito_id,
                ),
            )

            return cursor.fetchone()

    finally:
        conexion.close()

def buscar_perfil_por_dni(dni: str):
    """
    Busca un perfil por DNI.

    Se utiliza para evitar registros duplicados.
    """
    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    usuario_id,
                    nombres,
                    apellido_paterno,
                    apellido_materno,
                    dni,
                    telefono
                FROM perfiles
                WHERE dni = %s
                LIMIT 1
            """

            cursor.execute(sql, (dni,))
            return cursor.fetchone()

    finally:
        conexion.close()