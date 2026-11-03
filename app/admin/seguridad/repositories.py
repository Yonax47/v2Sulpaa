"""Consultas y transacciones del centro de seguridad de Identidad."""

from app.config.database import conexion_identidad


_ESTADO_SQL = """
CASE
    WHEN b.desbloqueado_en IS NOT NULL THEN 'DESBLOQUEADO'
    WHEN b.expira_en <= NOW(6) THEN 'EXPIRADO'
    ELSE 'ACTIVO'
END
"""


def _condiciones(filtros, alias="b"):
    """Construye filtros parametrizados para bloqueo, cuenta, IP y fechas."""

    partes = []
    parametros = []
    if filtros.get("cuenta"):
        partes.append(f"{alias}.correo_objetivo LIKE %s")
        parametros.append(f"%{filtros['cuenta']}%")
    if filtros.get("ip"):
        partes.append(f"{alias}.direccion_ip = %s")
        parametros.append(filtros["ip"])
    if filtros.get("desde"):
        partes.append(f"{alias}.bloqueado_en >= %s")
        parametros.append(filtros["desde"])
    if filtros.get("hasta"):
        partes.append(f"{alias}.bloqueado_en <= %s")
        parametros.append(filtros["hasta"])
    if filtros.get("estado"):
        partes.append(f"({_ESTADO_SQL}) = %s")
        parametros.append(filtros["estado"])
    return partes, parametros


def obtener_indicadores(filtros):
    """Cuenta fallos y estados sin modificar episodios expirados."""

    partes, parametros = _condiciones(filtros)
    where = " WHERE " + " AND ".join(partes) if partes else ""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN ({_ESTADO_SQL}) = 'ACTIVO'
                                      THEN 1 ELSE 0 END), 0) AS activos,
                    COALESCE(SUM(CASE WHEN ({_ESTADO_SQL}) = 'EXPIRADO'
                                      THEN 1 ELSE 0 END), 0) AS expirados,
                    COALESCE(SUM(CASE WHEN ({_ESTADO_SQL}) = 'DESBLOQUEADO'
                                      THEN 1 ELSE 0 END), 0) AS desbloqueados
                FROM bloqueos_acceso b
                {where}
                """,
                parametros,
            )
            bloqueos = cursor.fetchone()

            auditoria_where = [
                "evento IN ('LOGIN_FALLIDO', 'LOGIN_BLOQUEADO')"
            ]
            auditoria_params = []
            if filtros.get("cuenta"):
                auditoria_where.append("correo_intentado LIKE %s")
                auditoria_params.append(f"%{filtros['cuenta']}%")
            if filtros.get("ip"):
                auditoria_where.append("direccion_ip = %s")
                auditoria_params.append(filtros["ip"])
            if filtros.get("desde"):
                auditoria_where.append("creado_en >= %s")
                auditoria_params.append(filtros["desde"])
            if filtros.get("hasta"):
                auditoria_where.append("creado_en <= %s")
                auditoria_params.append(filtros["hasta"])
            cursor.execute(
                "SELECT COUNT(*) AS total FROM auditoria_accesos WHERE "
                + " AND ".join(auditoria_where),
                auditoria_params,
            )
            fallos = int(cursor.fetchone()["total"])
    finally:
        conexion.close()
    return {
        "fallos": fallos,
        "activos": int(bloqueos["activos"] or 0),
        "expirados": int(bloqueos["expirados"] or 0),
        "desbloqueados": int(bloqueos["desbloqueados"] or 0),
    }


def contar_bloqueos(filtros):
    """Cuenta episodios para calcular la paginación."""

    partes, parametros = _condiciones(filtros)
    where = " WHERE " + " AND ".join(partes) if partes else ""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM bloqueos_acceso b {where}",
                parametros,
            )
            return int(cursor.fetchone()["total"])
    finally:
        conexion.close()


def listar_bloqueos(filtros, limite, offset):
    """Lista episodios con estado y segundos restantes calculados por MySQL."""

    partes, parametros = _condiciones(filtros)
    where = " WHERE " + " AND ".join(partes) if partes else ""
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT b.*, ({_ESTADO_SQL}) AS estado,
                       GREATEST(TIMESTAMPDIFF(SECOND, NOW(6), b.expira_en), 0)
                           AS segundos_restantes
                FROM bloqueos_acceso b
                {where}
                ORDER BY b.bloqueado_en DESC, b.id DESC
                LIMIT %s OFFSET %s
                """,
                parametros + [limite, offset],
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_bloqueo(bloqueo_id):
    """Obtiene un episodio y su estado actual derivado del reloj de MySQL."""

    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT b.*, ({_ESTADO_SQL}) AS estado,
                       GREATEST(TIMESTAMPDIFF(SECOND, NOW(6), b.expira_en), 0)
                           AS segundos_restantes
                FROM bloqueos_acceso b
                WHERE b.id = %s
                """,
                (bloqueo_id,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


def listar_desbloqueos(bloqueo_id=None, limite=100):
    """Devuelve el historial manual con el correo del gerente responsable."""

    condicion = "WHERE d.bloqueo_id = %s" if bloqueo_id is not None else ""
    parametros = [bloqueo_id] if bloqueo_id is not None else []
    conexion = conexion_identidad()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT d.id, d.bloqueo_id, d.desbloqueado_por_id, d.motivo,
                       d.direccion_ip, d.creado_en, u.correo AS actor_correo,
                       b.correo_objetivo, b.direccion_ip AS bloqueo_ip
                FROM desbloqueos_acceso d
                JOIN bloqueos_acceso b ON b.id = d.bloqueo_id
                LEFT JOIN usuarios u ON u.id = d.desbloqueado_por_id
                {condicion}
                ORDER BY d.creado_en DESC, d.id DESC
                LIMIT %s
                """,
                parametros + [limite],
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def desbloquear_bloqueo(bloqueo_id, actor_id, motivo, direccion_ip):
    """Finaliza un bloqueo una sola vez mediante una transacción.

    ``FOR UPDATE`` hace que dos gerentes concurrentes esperen la misma fila.
    El segundo verá el desbloqueo ya confirmado y no podrá duplicar historial.
    """

    conexion = conexion_identidad()
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM bloqueos_acceso WHERE id = %s FOR UPDATE",
                (bloqueo_id,),
            )
            bloqueo = cursor.fetchone()
            if not bloqueo:
                conexion.rollback()
                return "NO_EXISTE"
            if bloqueo.get("desbloqueado_en"):
                conexion.rollback()
                return "YA_DESBLOQUEADO"

            cursor.execute("SELECT NOW(6) AS ahora")
            ahora = cursor.fetchone()["ahora"]
            if bloqueo["expira_en"] <= ahora:
                conexion.rollback()
                return "EXPIRADO"

            cursor.execute(
                """
                INSERT INTO desbloqueos_acceso (
                    bloqueo_id, desbloqueado_por_id, motivo, direccion_ip
                ) VALUES (%s, %s, %s, %s)
                """,
                (bloqueo_id, actor_id, motivo, direccion_ip),
            )
            cursor.execute(
                "UPDATE bloqueos_acceso SET desbloqueado_en = %s WHERE id = %s",
                (ahora, bloqueo_id),
            )
            correo_clave = (
                bloqueo["correo_objetivo"]
                if bloqueo["tipo"] == "CUENTA_IP"
                else ""
            )
            cursor.execute(
                """
                UPDATE contadores_acceso
                SET intentos = 0, ventana_inicia_en = NULL,
                    ultimo_intento_en = NULL, bloqueado_hasta = NULL
                WHERE tipo = %s AND correo_clave = %s AND direccion_ip = %s
                """,
                (bloqueo["tipo"], correo_clave, bloqueo["direccion_ip"]),
            )
            cursor.execute(
                """
                INSERT INTO auditoria_accesos (
                    usuario_id, correo_intentado, evento, resultado,
                    direccion_ip, detalle
                ) VALUES (%s, %s, 'DESBLOQUEO_MANUAL', 'EXITO', %s, %s)
                """,
                (
                    actor_id,
                    bloqueo.get("correo_objetivo"),
                    direccion_ip,
                    (
                        f"Bloqueo {bloqueo_id} finalizado. Motivo: {motivo}"
                    )[:500],
                ),
            )
        conexion.commit()
        return "DESBLOQUEADO"
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
