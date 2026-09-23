"""
Acceso a datos del dominio Encuestas de SULPAA V2.

Tablas del Bloque 4 (operaciones):
- encuestas             (cabecera de la encuesta única por pedido).
- encuesta_respuestas   (1:1 con encuestas: calificaciones 1-5).
- encuesta_eventos      (evidencia auditable de la invitación).

Convenciones (patrón de la casa):

- Las funciones de escritura reciben la ``conexion`` y los
  ``esquemas`` de la transacción en curso cuando se invocan dentro de un
  ``UnidadTrabajo``; las de lectura abren su propia conexión cuando no
  participan de una transacción.
- El token se persiste únicamente como ``token_hash`` (SHA-256) y
  ``token_cifrado`` (Fernet). Nunca en claro.
"""

import uuid

# ============================================================
# ESCRITURA DENTRO DE UNA TRANSACCIÓN (UnidadTrabajo)
# ============================================================

def insertar_encuesta(conexion, esquemas, pedido_id, entrega_id,
                      usuario_id, token_hash, token_cifrado):
    """Crea la encuesta única del pedido. Idempotente por pedido_id.

    Si ya existe una encuesta para el mismo pedido (retry/refresh),
    devuelve la fila existente sin duplicar ni sobrescribir.
    """
    operaciones = esquemas["operaciones"]
    fila = buscar_por_pedido(conexion, esquemas, pedido_id)
    if fila:
        return {"encuesta": fila, "nueva": False, "id": fila["id"]}

    encuesta_id = uuid.uuid4()
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.encuestas
                (id, pedido_id, entrega_id, usuario_id, estado, canal,
                 token_hash, token_cifrado)
            VALUES (%s, %s, %s, %s, 'PENDIENTE', 'PORTAL', %s, %s)
            """,
            (encuesta_id, pedido_id, entrega_id, usuario_id,
             token_hash, token_cifrado),
        )
    return {
        "encuesta": {
            "id": encuesta_id, "pedido_id": pedido_id,
            "entrega_id": entrega_id, "usuario_id": usuario_id,
            "estado": "PENDIENTE", "canal": "PORTAL",
        },
        "nueva": True,
        "id": encuesta_id,
    }


def buscar_por_pedido(conexion, esquemas, pedido_id):
    """Lee la encuesta de un pedido (una como máximo por UNIQUE)."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, pedido_id, entrega_id, usuario_id, estado, canal,
                   token_hash, token_cifrado, enviado_en, respondido_en
            FROM {operaciones}.encuestas
            WHERE pedido_id = %s LIMIT 1
            """,
            (pedido_id,),
        )
        return cursor.fetchone()


def buscar_por_id(conexion, esquemas, encuesta_id):
    """Lee una encuesta por su id (para el módulo administrativo)."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, pedido_id, entrega_id, usuario_id, estado, canal,
                   token_hash, token_cifrado, enviado_en, respondido_en,
                   creado_en
            FROM {operaciones}.encuestas
            WHERE id = %s LIMIT 1
            """,
            (encuesta_id,),
        )
        return cursor.fetchone()


def buscar_por_hash(conexion, esquemas, token_hash):
    """Busca la encuesta por el hash del token (portal público)."""
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT e.id, e.pedido_id, e.entrega_id, e.usuario_id, e.estado,
                   e.canal, e.token_hash, e.token_cifrado, e.enviado_en,
                   e.respondido_en, e.creado_en,
                   p.numero_pedido
            FROM {operaciones}.encuestas AS e
            LEFT JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
            WHERE e.token_hash = %s LIMIT 1
            """,
            (token_hash,),
        )
        return cursor.fetchone()


def bloquear_por_pedido(conexion, esquemas, pedido_id):
    """BLOQUEA la encuesta del pedido para resolverla dentro de la transacción."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, pedido_id, entrega_id, usuario_id, estado, canal,
                   token_hash, token_cifrado, enviado_en, respondido_en
            FROM {operaciones}.encuestas
            WHERE pedido_id = %s LIMIT 1 FOR UPDATE
            """,
            (pedido_id,),
        )
        return cursor.fetchone()


def marcar_estado(conexion, esquemas, encuesta_id, estado,
                  enviado_en=False, respondido_en=False):
    """Actualiza el estado de la encuesta y sus marcas temporales."""
    operaciones = esquemas["operaciones"]
    asignaciones = ["estado = %s"]
    parametros = [estado]
    if enviado_en:
        asignaciones.append("enviado_en = NOW()")
    if respondido_en:
        asignaciones.append("respondido_en = NOW()")
    parametros.append(encuesta_id)
    with conexion.cursor() as cursor:
        cursor.execute(
            f"UPDATE {operaciones}.encuestas SET "
            + ", ".join(asignaciones)
            + " WHERE id = %s",
            tuple(parametros),
        )
        return cursor.rowcount == 1


def registrar_evento(conexion, esquemas, encuesta_id, tipo,
                     detalle=None, actor_id=None):
    """Registra un evento auditable de la encuesta."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.encuesta_eventos
                (encuesta_id, tipo, detalle, usuario_responsable_id)
            VALUES (%s, %s, %s, %s)
            """,
            (encuesta_id, tipo, detalle, actor_id),
        )
        return True


def ya_fue_publicada(conexion, esquemas, encuesta_id):
    """Indica si la encuesta ya registró una invitación efectiva (KPI-09)."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM {operaciones}.encuesta_eventos
            WHERE encuesta_id = %s AND tipo = 'INVITACION_OK'
            """,
            (encuesta_id,),
        )
        return int(cursor.fetchone()["total"]) > 0


def insertar_respuesta(conexion, esquemas, encuesta_id, calificacion_general,
                       calificacion_producto, calificacion_entrega,
                       calificacion_atencion, recomendaria, comentario):
    """Persiste la respuesta 1:1 y devuelve True o False si ya existía."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.encuesta_respuestas
                (encuesta_id, calificacion_general, calificacion_producto,
                 calificacion_entrega, calificacion_atencion,
                 recomendaria, comentario)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (encuesta_id, calificacion_general, calificacion_producto,
             calificacion_entrega, calificacion_atencion,
             recomendaria, (comentario or "").strip()[:500] or None),
        )
        return True


def existe_respuesta(conexion, esquemas, encuesta_id):
    """Verifica si la encuesta ya fue respondida (constraint de UI + BD)."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM {operaciones}.encuesta_respuestas
            WHERE encuesta_id = %s
            """,
            (encuesta_id,),
        )
        return int(cursor.fetchone()["total"]) > 0


# ============================================================
# LECTURAS PARA EL MÓDULO ADMINISTRATIVO
# ============================================================

def listar_encuestas(esquemas=None, estado=None, desde=None, hasta=None,
                     limite=200):
    """Lista encuestas con número de pedido y calificación respondida."""
    from app.shared.unit_of_work import esquemas_sulpaa
    from app.config.database import conexion_operaciones

    esquemas = esquemas or esquemas_sulpaa()
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]

    where = []
    parametros = []
    if estado:
        where.append("e.estado = %s")
        parametros.append(estado)
    if desde:
        where.append("e.creado_en >= %s")
        parametros.append(desde)
    if hasta:
        where.append("e.creado_en < DATE_ADD(%s, INTERVAL 1 DAY)")
        parametros.append(hasta)

    condicion = ((" WHERE " + " AND ".join(where)) if where else "")

    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            consulta = (
                f"""
                SELECT e.id, e.pedido_id, e.entrega_id, e.usuario_id,
                       e.estado, e.canal, e.enviado_en, e.respondido_en,
                       e.creado_en,
                       p.numero_pedido,
                       r.calificacion_general, r.recomendaria
                FROM {operaciones}.encuestas AS e
                LEFT JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
                LEFT JOIN {operaciones}.encuesta_respuestas AS r
                    ON r.encuesta_id = e.id
                {condicion}
                ORDER BY e.creado_en DESC
                LIMIT %s
                """
            )
            cursor.execute(consulta, parametros + [limite])
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_detalle(esquemas=None, encuesta_id=None):
    """Devuelve encuesta + respuesta + total de eventos."""
    from app.shared.unit_of_work import esquemas_sulpaa
    from app.config.database import conexion_operaciones

    esquemas = esquemas or esquemas_sulpaa()
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]

    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT e.id, e.pedido_id, e.entrega_id, e.usuario_id,
                       e.estado, e.canal, e.enviado_en, e.respondido_en,
                       e.creado_en, e.actualizado_en,
                       p.numero_pedido, p.origen, p.total, p.moneda,
                       r.calificacion_general, r.calificacion_producto,
                       r.calificacion_entrega, r.calificacion_atencion,
                       r.recomendaria, r.comentario, r.creado_en AS resp_creado
                FROM {operaciones}.encuestas AS e
                LEFT JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
                LEFT JOIN {operaciones}.encuesta_respuestas AS r
                    ON r.encuesta_id = e.id
                WHERE e.id = %s LIMIT 1
                """,
                (encuesta_id,),
            )
            encuesta = cursor.fetchone()
            if not encuesta:
                return None
            cursor.execute(
                f"""
                SELECT tipo, detalle, usuario_responsable_id, creado_en
                FROM {operaciones}.encuesta_eventos
                WHERE encuesta_id = %s
                ORDER BY creado_en DESC
                """,
                (encuesta_id,),
            )
            encuesta["eventos"] = cursor.fetchall()
            return encuesta
    finally:
        conexion.close()