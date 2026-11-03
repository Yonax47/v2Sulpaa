"""
Repositorio del módulo Identidad.

Este archivo contiene únicamente operaciones de acceso a datos
relacionadas con usuarios y perfiles.

No debe contener lógica de negocio ni código de rutas Flask.
"""

import uuid

from app.config.database import conexion_identidad
from app.identidad.access_control import evaluar_fallo_contador
from app.identidad.email_repositories import insertar_solicitud


def _auditar_acceso(
    cursor,
    *,
    usuario_id,
    correo,
    evento,
    resultado,
    direccion_ip,
    user_agent,
    detalle,
):
    """Inserta un evento sin incluir contraseñas, tokens ni cookies."""

    cursor.execute(
        """
        INSERT INTO auditoria_accesos (
            usuario_id, correo_intentado, evento, resultado,
            direccion_ip, user_agent, detalle
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            usuario_id,
            correo or None,
            evento,
            resultado,
            direccion_ip,
            user_agent,
            detalle,
        ),
    )


def obtener_bloqueo_vigente(correo, direccion_ip):
    """Busca un bloqueo activo por cuenta+IP o por IP completa."""

    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, tipo, usuario_id, correo_objetivo, direccion_ip,
                       intentos_al_bloquear, bloqueado_en, expira_en
                FROM bloqueos_acceso
                WHERE direccion_ip = %s
                  AND desbloqueado_en IS NULL
                  AND expira_en > NOW(6)
                  AND (
                      tipo = 'IP'
                      OR (tipo = 'CUENTA_IP' AND correo_objetivo = %s)
                  )
                ORDER BY CASE WHEN tipo = 'IP' THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (direccion_ip, correo),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def registrar_intento_bloqueado(
    *, correo, usuario_id, direccion_ip, user_agent
):
    """Audita una petición rechazada sin volver a aumentar contadores."""

    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            _auditar_acceso(
                cursor,
                usuario_id=usuario_id,
                correo=correo,
                evento="LOGIN_BLOQUEADO",
                resultado="BLOQUEADO",
                direccion_ip=direccion_ip,
                user_agent=user_agent,
                detalle="Acceso rechazado por un bloqueo temporal vigente.",
            )
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def registrar_fallo_login(
    *,
    correo,
    usuario_id,
    direccion_ip,
    user_agent,
    max_cuenta_ip,
    max_ip,
    ventana_minutos,
    bloqueo_minutos,
):
    """Suma un fallo y crea bloqueos sin perder incrementos concurrentes.

    Las dos filas de contador se crean con una clave única y luego se bloquean
    con ``FOR UPDATE``. Así dos instancias de Railway serializan los cambios y
    ningún fallo se pierde. La fila de cuenta+IP nunca bloquea otras IP.
    """

    conexion = conexion_identidad()
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute("SELECT NOW(6) AS ahora")
            ahora = cursor.fetchone()["ahora"]
            claves = (("CUENTA_IP", correo), ("IP", ""))

            for tipo, correo_clave in claves:
                cursor.execute(
                    """
                    INSERT IGNORE INTO contadores_acceso (
                        tipo, correo_clave, direccion_ip, usuario_id,
                        intentos, ventana_inicia_en, ultimo_intento_en
                    ) VALUES (%s, %s, %s, %s, 0, %s, %s)
                    """,
                    (
                        tipo,
                        correo_clave,
                        direccion_ip,
                        usuario_id,
                        ahora,
                        ahora,
                    ),
                )

            cursor.execute(
                """
                SELECT tipo, correo_clave, intentos, ventana_inicia_en,
                       bloqueado_hasta
                FROM contadores_acceso
                WHERE direccion_ip = %s
                  AND ((tipo = 'CUENTA_IP' AND correo_clave = %s)
                       OR (tipo = 'IP' AND correo_clave = ''))
                ORDER BY tipo
                FOR UPDATE
                """,
                (direccion_ip, correo),
            )
            contadores = cursor.fetchall()
            bloqueos_creados = []
            bloqueo_ya_vigente = False

            for contador in contadores:
                tipo = contador["tipo"]
                limite = max_cuenta_ip if tipo == "CUENTA_IP" else max_ip
                estado = evaluar_fallo_contador(
                    intentos=contador["intentos"],
                    ventana_inicia_en=contador["ventana_inicia_en"],
                    bloqueado_hasta=contador["bloqueado_hasta"],
                    ahora=ahora,
                    limite=limite,
                    ventana_minutos=ventana_minutos,
                    bloqueo_minutos=bloqueo_minutos,
                )
                intentos = estado["intentos"]
                inicio = estado["ventana_inicia_en"]
                bloqueado_hasta = estado["bloqueado_hasta"]

                # Una petición que pasó la comprobación antes que otra puede
                # llegar aquí cuando el bloqueo ya nació. No crea otro episodio.
                if estado["bloqueo_vigente"]:
                    bloqueo_ya_vigente = True
                    continue

                if estado["bloqueo_nuevo"]:
                    cursor.execute(
                        """
                        INSERT INTO bloqueos_acceso (
                            tipo, usuario_id, correo_objetivo, direccion_ip,
                            intentos_al_bloquear, primer_intento_en,
                            ultimo_intento_en, bloqueado_en, expira_en
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            tipo,
                            usuario_id,
                            correo if tipo == "CUENTA_IP" else None,
                            direccion_ip,
                            intentos,
                            inicio,
                            ahora,
                            ahora,
                            bloqueado_hasta,
                        ),
                    )
                    bloqueos_creados.append(tipo)

                cursor.execute(
                    """
                    UPDATE contadores_acceso
                    SET usuario_id = COALESCE(usuario_id, %s),
                        intentos = %s,
                        ventana_inicia_en = %s,
                        ultimo_intento_en = %s,
                        bloqueado_hasta = %s
                    WHERE tipo = %s AND correo_clave = %s
                      AND direccion_ip = %s
                    """,
                    (
                        usuario_id,
                        intentos,
                        inicio,
                        ahora,
                        bloqueado_hasta,
                        tipo,
                        contador["correo_clave"],
                        direccion_ip,
                    ),
                )

            _auditar_acceso(
                cursor,
                usuario_id=usuario_id,
                correo=correo,
                evento="LOGIN_FALLIDO",
                resultado=(
                    "BLOQUEADO"
                    if bloqueos_creados or bloqueo_ya_vigente
                    else "FALLO"
                ),
                direccion_ip=direccion_ip,
                user_agent=user_agent,
                detalle=(
                    "Se activó un bloqueo temporal."
                    if bloqueos_creados or bloqueo_ya_vigente
                    else "Credenciales rechazadas."
                ),
            )
        conexion.commit()
        return {
            "bloqueado": bool(bloqueos_creados or bloqueo_ya_vigente),
            "tipos": bloqueos_creados,
        }
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def registrar_login_exitoso(
    *, usuario_id, correo, direccion_ip, user_agent
):
    """Actualiza el acceso, audita el éxito y reinicia solo cuenta+IP.

    El contador general de IP no se limpia: una cuenta válida no debe permitir
    que un atacante borre los fallos acumulados contra otras cuentas.
    """

    conexion = conexion_identidad()
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE usuarios SET ultimo_acceso_en = NOW() WHERE id = %s",
                (usuario_id,),
            )
            cursor.execute(
                """
                UPDATE contadores_acceso
                SET intentos = 0,
                    ventana_inicia_en = NULL,
                    ultimo_intento_en = NULL,
                    bloqueado_hasta = NULL
                WHERE tipo = 'CUENTA_IP' AND correo_clave = %s
                  AND direccion_ip = %s
                """,
                (correo, direccion_ip),
            )
            _auditar_acceso(
                cursor,
                usuario_id=usuario_id,
                correo=correo,
                evento="LOGIN",
                resultado="EXITO",
                direccion_ip=direccion_ip,
                user_agent=user_agent,
                detalle="Inicio de sesión correcto.",
            )
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def buscar_usuario_por_correo(correo: str):
    """
    Busca un usuario por correo electrónico.

    Args:
        correo: Correo del usuario.

    Returns:
        dict | None: Usuario encontrado o None.
    """
    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    correo,
                    password_hash,
                    estado,
                    correo_verificado,
                    requiere_verificacion_correo,
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


# ============================================================
# ROLES DEL USUARIO
# ============================================================
#
# Para el Panel Administrativo (Etapa 1) necesitamos saber
# qué roles tiene asignado un usuario autenticado.
#
# Las tablas REALES (dump identidad) son:
#
#     usuario_roles
#         - id
#         - usuario_id      (FK -> usuarios.id)
#         - rol_id          (FK -> roles.id)
#         - estado          ('ACTIVO' / 'INACTIVO')
#
#     roles
#         - id
#         - codigo          ('GERENTE', 'ADMINISTRADOR',
#                            'INVENTARIO',
#                            'PEDIDOS_LOGISTICA',
#                            'REPARTIDOR')
#         - estado          ('ACTIVO' / 'INACTIVO')
#
# Hacemos INNER JOIN entre ambas tablas y devolvemos
# SOLO los roles ACTIVOS del usuario.
#
# Esta es una consulta de SOLO LECTURA: no modifica
# las tablas, solo las consulta para poblar session["roles"].
# ============================================================


def listar_roles_usuario(
    usuario_id: str,
):
    """
    Lista los códigos de rol ACTIVOS de un usuario.

    Consulta las tablas reales `usuario_roles` y `roles`
    (dominio identidad) haciendo INNER JOIN por rol_id.

    Devuelve únicamente los roles en estado 'ACTIVO',
    tanto a nivel del vínculo (usuario_roles.estado)
    como a nivel del rol (roles.estado).

    En la Etapa 1 se usa tras la autenticación para
    poblar session["roles"]: así el decorador
    admin_required sabe si el usuario es GERENTE
    o ADMINISTRADOR (los únicos con acceso al panel).

    Returns:
        list[str]: Códigos de rol activos (ej. ["GERENTE"]).
    """

    conexion = conexion_identidad()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    r.codigo

                FROM usuario_roles AS ur

                INNER JOIN roles AS r
                    ON r.id = ur.rol_id

                WHERE
                    ur.usuario_id = %s
                    AND ur.estado = 'ACTIVO'
                    AND r.estado = 'ACTIVO'

                ORDER BY
                    r.codigo ASC
                """,
                (
                    usuario_id,
                ),
            )

            filas = cursor.fetchall()

            return [
                fila["codigo"]
                for fila in filas
            ]

    finally:

        conexion.close()


def obtener_contexto_autorizacion_usuario(usuario_id: str):
    """Consulta el estado de la cuenta y todos sus roles activos de una vez.

    Esta consulta se usa al proteger una petición. El ``LEFT JOIN`` permite
    reconocer a un usuario activo aunque no tenga roles, algo normal para un
    cliente. Así evitamos hacer una consulta para el usuario y otra para sus
    permisos en cada página.
    """

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
                    u.requiere_verificacion_correo,
                    r.codigo AS rol_codigo
                FROM usuarios AS u
                LEFT JOIN usuario_roles AS ur
                    ON ur.usuario_id = u.id
                    AND ur.estado = 'ACTIVO'
                LEFT JOIN roles AS r
                    ON r.id = ur.rol_id
                    AND r.estado = 'ACTIVO'
                WHERE u.id = %s
                ORDER BY r.codigo ASC
                """,
                (usuario_id,),
            )
            filas = cursor.fetchall()
    finally:
        conexion.close()

    if not filas:
        return None
    return {
        "id": filas[0]["id"],
        "correo": filas[0]["correo"],
        "estado": filas[0]["estado"],
        "correo_verificado": bool(filas[0].get("correo_verificado")),
        "requiere_verificacion_correo": bool(
            filas[0].get("requiere_verificacion_correo")
        ),
        "roles": [
            fila["rol_codigo"]
            for fila in filas
            if fila.get("rol_codigo")
        ],
    }


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
    rol_codigo: str = "CLIENTE",
    verificacion_correo=None,
):
    """
    Crea usuario, perfil y rol inicial dentro de una única transacción.

    Si el rol no existe/está inactivo o alguna inserción falla, no queda una
    cuenta parcial. El rol se resuelve por código dentro de esta misma
    transacción; no se modifican vínculos de cuentas existentes.
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
                    correo_verificado,
                    requiere_verificacion_correo
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'ACTIVO',
                    FALSE,
                    TRUE
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

            cursor.execute(
                """
                SELECT id
                FROM roles
                WHERE codigo = %s AND estado = 'ACTIVO'
                LIMIT 1
                """,
                (rol_codigo,),
            )
            rol = cursor.fetchone()
            if not rol:
                raise RuntimeError(
                    "No existe un rol activo para completar el registro."
                )

            cursor.execute(
                """
                INSERT INTO usuario_roles (
                    id, usuario_id, rol_id, asignado_por_usuario_id, estado
                )
                VALUES (%s, %s, %s, NULL, 'ACTIVO')
                """,
                (str(uuid.uuid4()), usuario_id, rol["id"]),
            )

            if not verificacion_correo:
                raise RuntimeError(
                    "El registro nuevo requiere una solicitud de correo."
                )
            insertar_solicitud(cursor, verificacion_correo)

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


def obtener_nombre_cliente_constancia(usuario_id):
    """Devuelve solo el nombre necesario para una constancia de compra.

    No proyecta correo, DNI, teléfono ni datos de facturación.
    """

    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT CONCAT_WS(
                    ' ', p.nombres, p.apellido_paterno, p.apellido_materno
                ) AS nombre_cliente
                FROM usuarios u
                INNER JOIN perfiles p ON p.usuario_id = u.id
                WHERE u.id = %s AND u.estado = 'ACTIVO'
                LIMIT 1
                """,
                (usuario_id,),
            )
            fila = cursor.fetchone()
            return (fila.get("nombre_cliente") or "").strip() if fila else None
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

def buscar_distritos_activos():
    """Devuelve todos los distritos activos con sus nombres
    de provincia y departamento para resolver el distrito
    de un destino geocodificado."""

    conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    di.id,
                    di.provincia_id,
                    di.nombre,
                    p.departamento_id,
                    p.nombre AS provincia_nombre,
                    de.nombre AS departamento_nombre
                FROM distritos di
                JOIN provincias p ON p.id = di.provincia_id
                JOIN departamentos de ON de.id = p.departamento_id
                WHERE
                    di.estado = 'ACTIVO'
                    AND p.estado = 'ACTIVO'
AND de.estado = 'ACTIVO'
                ORDER BY di.nombre ASC
                """
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
    latitud=None,
    longitud=None,
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
                    latitud,
                    longitud,
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
                    latitud,
                    longitud,
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


def listar_direcciones_usuario(usuario_id):
    """Solo direcciones activas del titular, con ubigeo para los selectores."""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT d.*, di.nombre AS distrito_nombre,
                       p.id AS provincia_id, p.departamento_id,
                       p.nombre AS provincia_nombre, de.nombre AS departamento_nombre
                FROM direcciones d
                JOIN distritos di ON di.id = d.distrito_id
                JOIN provincias p ON p.id = di.provincia_id
                JOIN departamentos de ON de.id = p.departamento_id
                WHERE d.usuario_id = %s AND d.estado = 'ACTIVA'
                  AND di.estado = 'ACTIVO'
                ORDER BY d.es_principal DESC, d.creado_en DESC
            """, (usuario_id,))
            return cursor.fetchall()
    finally:
        conexion.close()

# ============================================================
# GUARDAR DATOS DE FACTURACIÓN
# Implementación rama: serna
# ============================================================

def guardar_datos_facturacion(
    facturacion_id,
    usuario_id,
    tipo_contribuyente,
    dni=None,
    ruc=None,
    nombre_facturacion=None,
    razon_social=None,
    distrito_id=None,
    direccion_fiscal=None,
    conexion=None,
):
    """
    Guarda los datos de facturación verificados del usuario.

    ``tipo_contribuyente`` corresponde a la semántica histórica de la columna
    ``datos_facturacion.tipo``: únicamente ``PERSONA`` o ``EMPRESA``. No debe
    recibir el tipo de comprobante ``BOLETA``/``FACTURA``.

    Si el mismo documento ya existe como registro activo,
    se actualiza en lugar de crear un duplicado.

    El registro utilizado queda marcado como predeterminado.
    """

    propia = conexion is None

    if propia:
        conexion = conexion_identidad()

    try:
        with conexion.cursor() as cursor:

            # ------------------------------------------------
            # 1. Buscar un registro existente
            # ------------------------------------------------

            if tipo_contribuyente == "PERSONA":

                cursor.execute(
                    """
                    SELECT id
                    FROM datos_facturacion
                    WHERE
                        usuario_id = %s
                        AND tipo = 'PERSONA'
                        AND dni = %s
                        AND estado = 'ACTIVO'
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (
                        usuario_id,
                        dni,
                    ),
                )

            elif tipo_contribuyente == "EMPRESA":

                cursor.execute(
                    """
                    SELECT id
                    FROM datos_facturacion
                    WHERE
                        usuario_id = %s
                        AND tipo = 'EMPRESA'
                        AND ruc = %s
                        AND estado = 'ACTIVO'
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (
                        usuario_id,
                        ruc,
                    ),
                )

            else:
                raise ValueError(
                    "Tipo de facturación inválido."
                )

            existente = cursor.fetchone()

            # ------------------------------------------------
            # 2. Quitar condición de predeterminado
            #    a los registros anteriores
            # ------------------------------------------------

            cursor.execute(
                """
                UPDATE datos_facturacion
                SET es_predeterminado = 0
                WHERE
                    usuario_id = %s
                    AND estado = 'ACTIVO'
                """,
                (
                    usuario_id,
                ),
            )

            # ------------------------------------------------
            # 3. Actualizar si ya existe
            # ------------------------------------------------

            if existente:

                cursor.execute(
                    """
                    UPDATE datos_facturacion
                    SET
                        dni = %s,
                        ruc = %s,
                        nombre_facturacion = %s,
                        razon_social = %s,
                        distrito_id = %s,
                        direccion_fiscal = %s,
                        es_predeterminado = 1
                    WHERE id = %s
                    """,
                    (
                        dni,
                        ruc,
                        nombre_facturacion,
                        razon_social,
                        distrito_id,
                        direccion_fiscal,
                        existente["id"],
                    ),
                )

                resultado_id = existente["id"]

            # ------------------------------------------------
            # 4. Crear si todavía no existe
            # ------------------------------------------------

            else:

                cursor.execute(
                    """
                    INSERT INTO datos_facturacion (
                        id,
                        usuario_id,
                        tipo_contribuyente,
                        dni,
                        ruc,
                        nombre_facturacion,
                        razon_social,
                        distrito_id,
                        direccion_fiscal,
                        es_predeterminado,
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
                        %s,
                        %s,
                        1,
                        'ACTIVO'
                    )
                    """,
                    (
                        facturacion_id,
                        usuario_id,
                        tipo,
                        dni,
                        ruc,
                        nombre_facturacion,
                        razon_social,
                        distrito_id,
                        direccion_fiscal,
                    ),
                )

                resultado_id = facturacion_id

        if propia:
            conexion.commit()

        return resultado_id

    except Exception:
        if propia:
            conexion.rollback()
        raise

    finally:
        if propia:
            conexion.close()
