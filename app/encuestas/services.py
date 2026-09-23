"""
Reglas de negocio del dominio Encuestas de SULPAA V2.

Metodología KPI-09 (autorizada):

- Una encuesta NUNCA es "enviada" al momento de crearse. La fila nace
  en ``PENDIENTE`` y el evento ``CREADA`` solo documenta su creación.
- La invitación electrónica cuenta como ``INVITACION_OK`` ÚNICAMENTE
  cuando el canal PORTAL efectivamente habilita el enlace al cliente
  (la pantalla del pedido se abre con el CTA de la encuesta). Esa
  publicacion es idempotente: un solo evento por encuesta, sin dobles
  conteos (COUNT DISTINCT a nivel de pedido en el KPI).
- Responder una encuesta es irreversible y soło una vez: la base lo
  garantiza con ``UNIQUE(encuesta_id)`` en ``encuesta_respuestas``.
"""

from app.config.database import crear_conexion, conexion_operaciones
from app.encuestas import codigos as codigos_token
from app.encuestas import repositories as repos
from app.shared.unit_of_work import esquemas_sulpaa

# Roles que pueden operar encuestas desde el panel administrativo.
ROLES_ENCUESTAS = ("GERENTE", "ADMINISTRADOR")

_PALABRAS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ReglaEncuestaError(Exception):
    """Regla de negocio violada en el flujo de encuestas."""


# ============================================================
# CREACIÓN TRAS LA CONFIRMACIÓN DE LA ENTREGA
# ============================================================

def crear_encuesta_tras_completar(unidad, pedido_id):
    """Crea la encuesta PENDIENTE una vez que el pedido quedó COMPLETADO.

    Se invoca dentro de la misma ``UnidadTrabajo`` que completa el
    pedido (no surge de HTTP): asi la evidencia de la encuesta nace
    con la operación real. Idempotente: si una encuesta ya existe para
    el pedido, no se duplica ni se reinicia.
    """
    esquemas = unidad.esquemas
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]

    with unidad.conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT e.id AS entrega_id, p.usuario_id
            FROM {operaciones}.entregas AS e
            INNER JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
            WHERE e.pedido_id = %s AND e.estado = 'ENTREGADO'
            AND e.completado_en IS NOT NULL
            ORDER BY e.creado_en DESC LIMIT 1
            """,
            (pedido_id,),
        )
        fila = cursor.fetchone()

    if not fila:
        raise ReglaEncuestaError(
            "No se puede crear la encuesta sin una entrega ENTREGADO."
        )

    existente = repos.buscar_por_pedido(
        unidad.conexion, esquemas, pedido_id
    )
    if existente:
        return {
            "ok": True,
            "encuesta_id": existente["id"],
            "nueva": False,
        }

    token = codigos_token.generar_token()
    resultado = repos.insertar_encuesta(
        unidad.conexion, esquemas, pedido_id, fila["entrega_id"],
        fila["usuario_id"], codigos_token.hash_token(token),
        codigos_token.cifrar_token(token),
    )
    repos.registrar_evento(
        unidad.conexion, esquemas, resultado["id"], "CREADA",
        "Encuesta creada al completar el pedido entregado.", None,
    )
    return {
        "ok": True,
        "encuesta_id": resultado["id"],
        "nueva": True,
    }


# ============================================================
# PUBLICACIÓN DE LA INVITACIÓN (canal PORTAL)
# ============================================================

def _url_encuesta(token):
    """Devuelve la URL pública de la encuesta (se ensambla sin plano en BD)."""
    return "/encuesta/" + str(token)


def publicar_invitacion_lectura(pedido_id, usuario_id):
    """Habilita el CTA de la encuesta cuando el cliente abre su pedido.

    - Si la encuesta está PENDIENTE/ERROR_ENVIO: pasa a ENVIADA y
      registra EXACTAMENTE un evento ``INVITACION_OK`` (el enlace se
      puso efectivamente a disposición del cliente).
    - Este método corre desde el detalle del pedido, por lo que la
      invitación solo cuenta cuando el cliente consultó su pedido.

    Returns:
        dict con "disponible" (bool), "estado" y, si aplica, "url".
        None si el pedido no tiene encuesta.
    """
    esquemas = esquemas_sulpaa()
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            conexion.begin()

            encuesta = repos.buscar_por_pedido(
                conexion, esquemas, pedido_id
            )

            if not encuesta or encuesta["usuario_id"] != usuario_id:
                conexion.rollback()
                return None

            # Bloqueo la fila para resolverla sin carreras.
            encuesta = repos.bloquear_por_pedido(
                conexion, esquemas, pedido_id
            )
            if not encuesta:
                conexion.rollback()
                return None

            estado = encuesta["estado"]
            if estado == "RESPONDIDA":
                conexion.rollback()
                return {"disponible": True, "estado": "RESPONDIDA"}

            ya_publicada = repos.ya_fue_publicada(
                conexion, esquemas, encuesta["id"]
            )

            if estado == "PENDIENTE" or estado == "ERROR_ENVIO":
                repos.marcar_estado(
                    conexion, esquemas, encuesta["id"], "ENVIADA",
                    enviado_en=True,
                )
                if not ya_publicada:
                    repos.registrar_evento(
                        conexion, esquemas, encuesta["id"], "INVITACION_OK",
                        "Enlace de encuesta habilitado en el portal del cliente.",
                        None,
                    )
                estado = "ENVIADA"
            elif estado == "ENVIADA" and not ya_publicada:
                repos.registrar_evento(
                    conexion, esquemas, encuesta["id"], "INVITACION_OK",
                    "Enlace de encuesta habilitado en el portal del cliente.",
                    None,
                )

            token = codigos_token.descifrar_token(
                encuesta["token_cifrado"]
            )

            conexion.commit()
            return {
                "disponible": True,
                "estado": estado,
                "url": _url_encuesta(token) if token else None,
            }
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


# ============================================================
# PORTAL PÚBLICO DEL CLIENTE
# ============================================================

def validar_respuestas(datos):
    """Normaliza y valida las respuestas recibidas del formulario."""
    errores = []
    calificaciones = {}

    for campo in ("calificacion_general", "calificacion_producto",
                  "calificacion_entrega", "calificacion_atencion"):
        try:
            valor = int(datos.get(campo, 0) or 0)
        except (TypeError, ValueError):
            valor = 0
        if valor < 1 or valor > 5:
            errores.append(
                f"La calificación {campo} debe estar entre 1 y 5."
            )
        calificaciones[campo] = valor

    recomendaria = (datos.get("recomendaria") or "").strip().upper()
    if recomendaria not in ("SI", "NO"):
        errores.append("Indica si recomendarías SULPAA.")

    comentario = (datos.get("comentario") or "").strip()
    if len(comentario) > 500:
        errores.append("El comentario no puede superar 500 caracteres.")

    if errores:
        raise ReglaEncuestaError(" | ".join(errores))

    return {
        "calificacion_general": calificaciones["calificacion_general"],
        "calificacion_producto": calificaciones["calificacion_producto"],
        "calificacion_entrega": calificaciones["calificacion_entrega"],
        "calificacion_atencion": calificaciones["calificacion_atencion"],
        "recomendaria": recomendaria,
        "comentario": comentario,
    }


def obtener_encuesta_publica(token):
    """Devuelve los datos públicos de la encuesta para el formulario."""
    token = str(token or "").strip()
    if not token or len(token) < 8:
        raise ReglaEncuestaError("El enlace de encuesta no es válido.")

    esquemas = esquemas_sulpaa()
    conexion = conexion_operaciones()
    try:
        encuesta = repos.buscar_por_hash(
            conexion, esquemas, codigos_token.hash_token(token)
        )
    finally:
        conexion.close()

    if not encuesta:
        raise ReglaEncuestaError(
            "La encuesta no existe o el enlace expiró."
        )
    return {
        "estado": encuesta["estado"],
        "numero_pedido": encuesta.get("numero_pedido"),
        "encuesta_id": encuesta["id"],
    }


def responder_encuesta(token, datos):
    """Registra la respuesta del cliente y cierra la encuesta.

    La transacción garantiza la atomicidad: respuesta + estado
    RESPONDIDA + evento RESPONDIDA, o nada.
    """
    token = str(token or "").strip()
    if not token or len(token) < 8:
        raise ReglaEncuestaError("El enlace de encuesta no es válido.")

    respuestas = validar_respuestas(datos)

    esquemas = esquemas_sulpaa()
    conexion = conexion_operaciones()
    try:
        conexion.begin()
        encuesta = repos.buscar_por_hash(
            conexion, esquemas, codigos_token.hash_token(token)
        )
        if not encuesta:
            conexion.rollback()
            raise ReglaEncuestaError(
                "La encuesta no existe o el enlace expiró."
            )
        if encuesta["estado"] == "RESPONDIDA":
            conexion.rollback()
            raise ReglaEncuestaError(
                "Esta encuesta ya fue respondida."
            )
        if repos.existe_respuesta(conexion, esquemas, encuesta["id"]):
            conexion.rollback()
            raise ReglaEncuestaError(
                "Esta encuesta ya fue respondida."
            )

        repos.insertar_respuesta(
            conexion, esquemas, encuesta["id"],
            respuestas["calificacion_general"],
            respuestas["calificacion_producto"],
            respuestas["calificacion_entrega"],
            respuestas["calificacion_atencion"],
            respuestas["recomendaria"],
            respuestas["comentario"],
        )
        repos.marcar_estado(
            conexion, esquemas, encuesta["id"], "RESPONDIDA",
            respondido_en=True,
        )
        repos.registrar_evento(
            conexion, esquemas, encuesta["id"], "RESPONDIDA",
            "El cliente completó la encuesta de satisfacción.", None,
        )
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()

    return {"ok": True, "estado": "RESPONDIDA"}


# ============================================================
# ADMINISTRACIÓN DE ENCUESTAS
# ============================================================

def listar_encuestas(filtros=None):
    """Lista encuestas para el panel administrativo."""
    filtros = filtros or {}
    return repos.listar_encuestas(
        estado=filtros.get("estado") or None,
        desde=filtros.get("desde") or None,
        hasta=filtros.get("hasta") or None,
    )


def obtener_detalle_encuesta(encuesta_id):
    """Devuelve la encuesta con su respuesta y eventos."""
    return repos.obtener_detalle(encuesta_id=encuesta_id)


def reenviar_invitacion(actor_id, roles, encuesta_id):
    """Rehabilita la invitación PORTAL de una encuesta respondible.

    Registra SIEMPRE el evento ``REINTENTO`` (auditoría). Si la
    encuesta estaba en ``ERROR_ENVIO``, se activa de nuevo a
    ``ENVIADA`` y se registra su única ``INVITACION_OK`` (cuenta en el
    KPI-09, ya que el enlace vuelve a estar disponible).
    """
    roles_ok = set(roles or [])
    if not (roles_ok & set(ROLES_ENCUESTAS)):
        raise ReglaEncuestaError(
            "Solo GERENTE y ADMINISTRADOR gestionan encuestas."
        )

    esquemas = esquemas_sulpaa()
    conexion = conexion_operaciones()
    try:
        conexion.begin()
        encuesta = repos.buscar_por_id(
            conexion, esquemas, encuesta_id
        )
        if not encuesta:
            conexion.rollback()
            raise ReglaEncuestaError("La encuesta no existe.")
        if encuesta["estado"] == "RESPONDIDA":
            conexion.rollback()
            raise ReglaEncuestaError(
                "La encuesta ya fue respondida; no se puede reenviar."
            )

        repos.registrar_evento(
            conexion, esquemas, encuesta["id"], "REINTENTO",
            "Rehabilitación de la invitación desde administración.", actor_id,
        )

        if encuesta["estado"] == "ERROR_ENVIO":
            repos.marcar_estado(
                conexion, esquemas, encuesta["id"], "ENVIADA",
                enviado_en=True,
            )
            if not repos.ya_fue_publicada(conexion, esquemas, encuesta["id"]):
                repos.registrar_evento(
                    conexion, esquemas, encuesta["id"], "INVITACION_OK",
                    "Enlace de encuesta rehabilitado desde administración.",
                    actor_id,
                )
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()

    return {"ok": True, "estado": "ENVIADA"}