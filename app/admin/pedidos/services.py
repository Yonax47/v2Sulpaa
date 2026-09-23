"""Reglas de negocio del módulo administrativo de pedidos."""

from datetime import date

from app.admin.pedidos import repositories
from app.comercio.pedido_states import (
    ESTADO_CONFIRMADO,
    ESTADO_CREADO,
    ESTADO_EN_PREPARACION,
    etiqueta_estado_pedido,
    transicion_permitida,
)
from app.shared.unit_of_work import UnidadTrabajo


ROLES_OPERACION_PEDIDOS = frozenset({
    "GERENTE",
    "ADMINISTRADOR",
    "PEDIDOS_LOGISTICA",
})

ETIQUETAS_PAGO = {
    "PENDIENTE": "Pendiente",
    "EN_REVISION": "En revisión",
    "PAGADO": "Pagado",
    "RECHAZADO": "Rechazado",
    "CANCELADO": "Cancelado",
    "REEMBOLSADO": "Reembolsado",
}

ETIQUETAS_ENTREGA = {
    "PENDIENTE": "Pendiente",
    "EN_PREPARACION": "En preparación",
    "LISTO": "Listo",
    "PROGRAMADO": "Programado",
    "EN_TRANSITO": "En tránsito",
    "LISTO_PARA_RECOJO": "Listo para recojo",
    "ENTREGADO": "Entregado",
    "CANCELADO": "Cancelado",
    "INCIDENCIA": "Incidencia",
}

ETIQUETAS_TIPO_ENTREGA = {
    "RECOJO_LOCAL": "Recojo en local",
    "DELIVERY_LOCAL": "Delivery local",
    "TRANSPORTISTA_ASOCIADO": "Transportista asociado",
}


class ReglaPedidoError(Exception):
    """Error de negocio seguro para mostrar en la interfaz administrativa."""


def _etiqueta(valor, catalogo):
    normalizado = str(valor or "").strip().upper()
    return catalogo.get(normalizado, normalizado or "No registrado")


def _fecha_filtro(valor, nombre):
    """Valida fechas ISO antes de enviarlas como parámetros SQL."""
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError) as error:
        raise ReglaPedidoError(f"{nombre} no es válida.") from error


def _normalizar_roles(roles):
    return {str(rol).strip().upper() for rol in (roles or [])}


def _puede_operar(roles):
    return bool(_normalizar_roles(roles) & ROLES_OPERACION_PEDIDOS)


def _validar_pago(pago):
    """Aplica el contrato de pagos anticipados y pagos offline.

    Un pago anticipado requiere evidencia PAGADO. Contra entrega y pago en
    local pueden permanecer PENDIENTE durante confirmación y preparación.
    Estados rechazados o cancelados nunca habilitan una transición.
    """
    if not pago:
        raise ReglaPedidoError("El pedido no tiene un pago registrado.")
    modalidad = str(pago.get("modalidad") or "").upper()
    estado = str(pago.get("estado") or "").upper()
    if modalidad == "ANTICIPADO" and estado != "PAGADO":
        raise ReglaPedidoError(
            "El pago anticipado debe estar pagado antes de continuar."
        )
    if modalidad in {"CONTRA_ENTREGA", "PAGO_EN_LOCAL"}:
        if estado not in {"PENDIENTE", "PAGADO"}:
            raise ReglaPedidoError(
                "El estado actual del pago no permite procesar el pedido."
            )
        return
    if modalidad != "ANTICIPADO":
        raise ReglaPedidoError("La modalidad de pago no es válida.")


def _acciones_disponibles(estado, roles):
    """Calcula acciones en backend; la plantilla solo las representa."""
    if not _puede_operar(roles):
        return []
    if estado == ESTADO_CREADO:
        return [{"codigo": "CONFIRMAR", "etiqueta": "Confirmar pedido"}]
    if estado == ESTADO_CONFIRMADO:
        return [{"codigo": "INICIAR_PREPARACION",
                 "etiqueta": "Iniciar preparación"}]
    return []


def listar_pedidos_admin(filtros):
    """Prepara el listado administrativo a partir de datos reales."""
    filtros = filtros or {}
    busqueda = str(filtros.get("q") or "").strip()[:120]
    estado = str(filtros.get("estado") or "").strip().upper()
    if estado not in {"", "CREADO", "CONFIRMADO", "EN_PREPARACION",
                      "COMPLETADO", "CANCELADO"}:
        raise ReglaPedidoError("El filtro de estado no es válido.")
    fecha_desde = _fecha_filtro(filtros.get("fecha_desde"), "La fecha inicial")
    fecha_hasta = _fecha_filtro(filtros.get("fecha_hasta"), "La fecha final")
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise ReglaPedidoError("La fecha inicial no puede superar la final.")

    with UnidadTrabajo() as unidad:
        pedidos = repositories.listar_pedidos(
            unidad.conexion,
            unidad.esquemas,
            busqueda=busqueda or None,
            estado=estado or None,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
        # La lectura no necesita commit; el contexto cerrará con rollback inocuo.

    for pedido in pedidos:
        pedido["estado_label"] = etiqueta_estado_pedido(pedido["estado"])
        pedido["pago_estado_label"] = _etiqueta(
            pedido.get("pago_estado"), ETIQUETAS_PAGO
        )
        pedido["entrega_estado_label"] = _etiqueta(
            pedido.get("entrega_estado"), ETIQUETAS_ENTREGA
        )
        pedido["tipo_entrega_label"] = _etiqueta(
            pedido.get("tipo_entrega"), ETIQUETAS_TIPO_ENTREGA
        )
    return pedidos


def obtener_detalle_admin(pedido_id, roles):
    """Compone el detalle y sus acciones autorizadas desde backend."""
    if not pedido_id:
        return None
    with UnidadTrabajo() as unidad:
        pedido = repositories.obtener_cabecera_pedido(
            unidad.conexion, unidad.esquemas, pedido_id
        )
        if not pedido:
            return None
        pedido["productos"] = repositories.obtener_productos_pedido(
            unidad.conexion, unidad.esquemas, pedido_id
        )
        pedido["historial"] = repositories.obtener_historial_pedido(
            unidad.conexion, unidad.esquemas, pedido_id
        )
        pedido["entrega_detalle"] = repositories.obtener_entrega_detalle(
            unidad.conexion,
            unidad.esquemas,
            pedido.get("entrega_id"),
            pedido.get("tipo_entrega"),
        )

    pedido["estado_label"] = etiqueta_estado_pedido(pedido["estado"])
    pedido["pago_estado_label"] = _etiqueta(
        pedido.get("pago_estado"), ETIQUETAS_PAGO
    )
    pedido["entrega_estado_label"] = _etiqueta(
        pedido.get("entrega_estado"), ETIQUETAS_ENTREGA
    )
    pedido["tipo_entrega_label"] = _etiqueta(
        pedido.get("tipo_entrega"), ETIQUETAS_TIPO_ENTREGA
    )
    pedido["acciones"] = _acciones_disponibles(pedido["estado"], roles)
    for evento in pedido["historial"]:
        evento["estado_anterior_label"] = (
            etiqueta_estado_pedido(evento["estado_anterior"])
            if evento["estado_anterior"] else None
        )
        evento["estado_nuevo_label"] = etiqueta_estado_pedido(
            evento["estado_nuevo"]
        )
    return pedido


def _cambiar_estado(pedido_id, actor_id, roles, estado_esperado,
                    estado_nuevo, sincronizar_entrega=False):
    """Ejecuta una transición con bloqueo y commit único entre esquemas."""
    if not actor_id or not _puede_operar(roles):
        raise ReglaPedidoError("No tienes permisos para realizar esta acción.")
    if not transicion_permitida(estado_esperado, estado_nuevo):
        raise ReglaPedidoError("La transición solicitada no está habilitada.")

    with UnidadTrabajo() as unidad:
        contexto = repositories.bloquear_contexto_operativo(
            unidad.conexion, unidad.esquemas, pedido_id
        )
        if not contexto:
            raise ReglaPedidoError("El pedido solicitado no existe.")
        pedido = contexto["pedido"]
        if pedido["estado"] != estado_esperado:
            raise ReglaPedidoError(
                "El pedido ya no se encuentra en un estado que permita esta operación."
            )

        _validar_pago(contexto["pago"])
        entrega = contexto["entrega"]
        if not entrega:
            raise ReglaPedidoError(
                "El pedido no tiene una entrega registrada y no puede procesarse."
            )
        if entrega["estado"] != "PENDIENTE":
            raise ReglaPedidoError(
                "La entrega ya no se encuentra pendiente y requiere revisión."
            )

        if not repositories.actualizar_estado_pedido(
            unidad.conexion, unidad.esquemas, pedido_id,
            estado_esperado, estado_nuevo,
        ):
            raise ReglaPedidoError(
                "El pedido cambió mientras se procesaba la operación."
            )

        if sincronizar_entrega:
            if not repositories.actualizar_entrega_a_preparacion(
                unidad.conexion, unidad.esquemas, entrega["id"]
            ):
                raise ReglaPedidoError(
                    "La entrega cambió mientras se iniciaba la preparación."
                )
            repositories.insertar_historial_entrega(
                unidad.conexion,
                unidad.esquemas,
                entrega["id"],
                actor_id,
                "Preparación iniciada junto con el pedido administrativo.",
            )

        comentario = (
            "Pedido confirmado por operación administrativa."
            if estado_nuevo == ESTADO_CONFIRMADO
            else "Preparación iniciada por operación administrativa."
        )
        repositories.insertar_historial_pedido(
            unidad.conexion,
            unidad.esquemas,
            pedido_id,
            estado_esperado,
            estado_nuevo,
            actor_id,
            "EMPLEADO",
            comentario,
        )
        unidad.confirmar()
    return {"ok": True, "estado": estado_nuevo}


def confirmar_pedido(pedido_id, actor_id, roles):
    """Confirma un pedido CREADO sin modificar todavía su entrega."""
    return _cambiar_estado(
        pedido_id, actor_id, roles, ESTADO_CREADO, ESTADO_CONFIRMADO
    )


def iniciar_preparacion(pedido_id, actor_id, roles):
    """Inicia pedido y entrega de forma atómica y deja ambos historiales."""
    return _cambiar_estado(
        pedido_id,
        actor_id,
        roles,
        ESTADO_CONFIRMADO,
        ESTADO_EN_PREPARACION,
        sincronizar_entrega=True,
    )


def ejecutar_backfill_pedidos():
    """Ejecuta y confirma la regularización solo tras validar sus conteos."""
    with UnidadTrabajo() as unidad:
        resultado = repositories.ejecutar_backfill_historial(
            unidad.conexion, unidad.esquemas
        )
        unidad.confirmar()
    return resultado
