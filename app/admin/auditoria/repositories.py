"""Acceso a datos del módulo administrativo de Auditoría.

Tabla real (operaciones): ``auditoria_operaciones``.
Es append-only: la interfaz solo permite consultar, nunca
editar ni eliminar eventos.

Además, para mostrar el responsable y su rol, se une con las
tablas reales de identidad (``usuarios``, ``perfiles``,
``usuario_roles``, ``roles``) por ``usuario_id``. La unión es de
solo lectura y no modifica el registro histórico.
"""

import json
from app.config.database import conexion_operaciones, nombre_esquema

# Nombres exactos que NUNCA deben guardarse en la auditoría. Se mantienen
# separados de las reglas por prefijo/sufijo para no eliminar campos
# operativos legítimos como ``codigo_seguimiento`` o ``metodo_pago``.
_CLAVES_SENSIBLES = frozenset({
    "password",
    "password_hash",
    "passwd",
    "contrasena",
    "contraseña",
    "credential",
    "credentials",
    "token",
    "csrf_token",
    "_csrf_token",
    "access_token",
    "refresh_token",
    "auth_token",
    "authentication_token",
    "token_hash",
    "api_key",
    "apikey",
    "private_key",
    "secret_key",
    "client_secret",
    "secret",
    "clave",
    "authorization",
    "cookie",
    "session",
    "session_id",
})


def _es_clave_sensible(clave):
    """Reconoce nombres habituales de credenciales sin mirar su valor.

    Se normalizan mayúsculas y guiones para cubrir formularios, JSON y datos
    provenientes de proveedores distintos. Además de la lista exacta, se
    protegen variantes como ``usuario_password`` o ``proveedor_api_key``.
    """

    nombre = str(clave or "").strip().lower().replace("-", "_")
    if nombre in _CLAVES_SENSIBLES:
        return True
    return (
        nombre.startswith((
            "password_",
            "passwd_",
            "contrasena_",
            "contraseña_",
            "token_",
            "secret_",
            "private_key_",
            "clave_privada_",
            "api_key_",
            "authorization_",
            "cookie_",
            "session_",
            "credential_",
            "credentials_",
        ))
        or nombre.endswith((
            "_password",
            "_passwd",
            "_contrasena",
            "_contraseña",
            "_token",
            "_token_hash",
            "_api_key",
            "_private_key",
            "_clave_privada",
            "_secret",
            "_credential",
            "_credentials",
        ))
    )


def _esquema(variable):
    """Resuelve el esquema correcto sin mezclar producción y pruebas."""
    return nombre_esquema(variable)


def _limpiar(datos):
    """Quita cualquier dato sensible antes de serializar a JSON."""
    if datos is None:
        return None
    if isinstance(datos, dict):
        limpio = {}
        for clave, valor in datos.items():
            if _es_clave_sensible(clave):
                continue
            limpio[clave] = _limpiar(valor)
        return limpio
    if isinstance(datos, (list, tuple)):
        return [_limpiar(elemento) for elemento in datos]
    return datos


def _serializar(datos):
    """Convierte a texto JSON seguro, o None si no hay contenido."""
    if datos is None:
        return None
    limpio = _limpiar(datos)
    return json.dumps(limpio, ensure_ascii=False, default=str)


def insertar_evento(
    usuario_id,
    modulo,
    entidad,
    accion,
    entidad_id=None,
    datos_anteriores=None,
    datos_nuevos=None,
    direccion_ip=None,
):
    """Inserta un único evento de auditoría y confirma la transacción.

    Se usa DESPUÉS de que la operación principal terminó. Si la
    auditoría falla, el error sube a quien la invoca para que decida
    (el Service normalmente solo lo registra en el log).
    """
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auditoria_operaciones (
                    usuario_id,
                    modulo,
                    entidad,
                    entidad_id,
                    accion,
                    datos_anteriores,
                    datos_nuevos,
                    direccion_ip
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    usuario_id,
                    modulo,
                    entidad,
                    entidad_id,
                    accion,
                    _serializar(datos_anteriores),
                    _serializar(datos_nuevos),
                    direccion_ip,
                ),
            )
            nuevo_id = cursor.lastrowid
        conexion.commit()
        return nuevo_id
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def _condiciones(filtros):
    """Construye WHERE parametrizado sin concatenar valores."""
    sql = []
    params = []
    if filtros.get("usuario_id"):
        sql.append("a.usuario_id = %s")
        params.append(filtros["usuario_id"])
    if filtros.get("modulo"):
        sql.append("a.modulo = %s")
        params.append(filtros["modulo"])
    if filtros.get("accion"):
        sql.append("a.accion = %s")
        params.append(filtros["accion"])
    if filtros.get("entidad"):
        sql.append("a.entidad = %s")
        params.append(filtros["entidad"])
    if filtros.get("desde"):
        sql.append("a.creado_en >= %s")
        params.append(filtros["desde"])
    if filtros.get("hasta"):
        sql.append("a.creado_en <= %s")
        params.append(filtros["hasta"])
    return sql, params


def listar_eventos(filtros, limite=25, offset=0):
    """Lista eventos paginados, ya resueltos con responsable y rol."""
    identidad = _esquema("DB_IDENTIDAD")
    clausulas, params = _condiciones(filtros)
    where = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""

    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.usuario_id,
                    a.modulo,
                    a.entidad,
                    a.entidad_id,
                    a.accion,
                    a.datos_anteriores,
                    a.datos_nuevos,
                    a.direccion_ip,
                    a.creado_en,
                    u.correo AS usuario_correo,
                    p.nombres AS usuario_nombres,
                    p.apellido_paterno AS usuario_apellido,
                    (
                        SELECT GROUP_CONCAT(r.codigo ORDER BY r.codigo)
                        FROM {identidad}.usuario_roles ur
                        JOIN {identidad}.roles r ON r.id = ur.rol_id
                        WHERE ur.usuario_id = a.usuario_id
                          AND ur.estado = 'ACTIVO'
                          AND r.estado = 'ACTIVO'
                    ) AS usuario_roles
                FROM auditoria_operaciones AS a
                LEFT JOIN {identidad}.usuarios AS u ON u.id = a.usuario_id
                LEFT JOIN {identidad}.perfiles AS p ON p.usuario_id = a.usuario_id
                {where}
                ORDER BY a.creado_en DESC, a.id DESC
                LIMIT %s OFFSET %s
                """.format(identidad=identidad, where=where),
                params + [int(limite), int(offset)],
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def contar_eventos(filtros):
    """Cuenta los eventos que cumplen los filtros (para paginar)."""
    clausulas, params = _condiciones(filtros)
    where = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM auditoria_operaciones AS a "
                + where,
                params,
            )
            return cursor.fetchone()["total"]
    finally:
        conexion.close()


def obtener_evento(evento_id):
    """Devuelve un evento puntual con su responsable resuelto."""
    identidad = _esquema("DB_IDENTIDAD")
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.*,
                    u.correo AS usuario_correo,
                    p.nombres AS usuario_nombres,
                    p.apellido_paterno AS usuario_apellido
                FROM auditoria_operaciones AS a
                LEFT JOIN {identidad}.usuarios AS u ON u.id = a.usuario_id
                LEFT JOIN {identidad}.perfiles AS p ON p.usuario_id = a.usuario_id
                WHERE a.id = %s
                LIMIT 1
                """.format(identidad=identidad),
                (int(evento_id),),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def listar_modulos():
    """Lista los módulos realmente presentes en la auditoría."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT modulo FROM auditoria_operaciones ORDER BY modulo"
            )
            return [fila["modulo"] for fila in cursor.fetchall()]
    finally:
        conexion.close()


def listar_acciones():
    """Lista las acciones realmente registradas."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT accion FROM auditoria_operaciones ORDER BY accion"
            )
            return [fila["accion"] for fila in cursor.fetchall()]
    finally:
        conexion.close()
