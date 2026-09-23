"""Reglas de negocio del módulo administrativo de entregas.

Este módulo reutiliza la lógica transaccional del dominio Operaciones
(que ya exige bloqueo, historial y commit único entre esquemas) y solo
proyecta sus errores como ReglaEntregaError para la interfaz.
"""

from app.operaciones import services as operaciones_services


class ReglaEntregaError(Exception):
    """Error de negocio seguro para mostrar en la interfaz administrativa."""


ROLES_ENTREGAS = ("GERENTE", "ADMINISTRADOR", "PEDIDOS_LOGISTICA")

ETIQUETAS_ESTADO_ENTREGA = operaciones_services._etiqueta_estado_entrega
ETIQUETAS_TIPO_ENTREGA = operaciones_services._etiqueta_tipo_entrega


def _ejecutar(operacion, *argumentos, **opciones):
    """Ejecuta un service de Operaciones traduciendo sus errores de negocio."""
    try:
        return operacion(*argumentos, **opciones)
    except operaciones_services.ReglaOperativaError as error:
        raise ReglaEntregaError(str(error)) from error


def listar_entregas(filtros):
    """Lista entregas reales con etiquetas de presentación."""
    filtros = filtros or {}
    return _ejecutar(
        operaciones_services.listar_entregas_operativa,
        estado=filtros.get("estado"),
        tipo=filtros.get("tipo"),
        busqueda=filtros.get("q"),
    )


def obtener_detalle(entrega_id):
    """Devuelve el detalle operativo completo de una entrega."""
    detalle = _ejecutar(
        operaciones_services.obtener_detalle_entrega_operativa, entrega_id
    )
    return enriquecer_detalle(detalle)


def enriquecer_detalle(detalle):
    """Proyecta etiquetas legibles sobre el detalle real entregado."""
    if not detalle:
        return None
    detalle["estado_label"] = ETIQUETAS_ESTADO_ENTREGA(detalle["estado"])
    detalle["tipo_label"] = ETIQUETAS_TIPO_ENTREGA(detalle["tipo_entrega"])
    detalle["pago_modalidad_label"] = str(
        detalle.get("pago_modalidad") or "No registrada"
    ).replace("_", " ").title()
    detalle["pago_estado_label"] = _etiqueta_pago(detalle.get("pago_estado"))
    detalle["pago_metodo_label"] = (
        detalle.get("pago_metodo_nombre") or "No registrado"
    )
    if detalle.get("transportista"):
        envio = detalle["transportista"]
        envio["estado_label"] = operaciones_services.ETIQUETAS_ENVIO.get(
            envio.get("estado"), envio.get("estado") or "—"
        )
    for incidencia in detalle.get("incidencias") or []:
        incidencia["estado_label"] = _incidencia_label(incidencia["estado"])
    return detalle


def listar_repartidores():
    """Lista la planilla real de repartidores."""
    repartidores = _ejecutar(
        operaciones_services.listar_repartidores_operativa
    )
    for repartidor in repartidores:
        repartidor["disponible_label"] = (
            "Disponible" if repartidor.get("disponible") else "En reparto"
        )
        repartidor["estado_label"] = str(
            repartidor.get("estado") or "ACTIVO"
        ).capitalize()
    return repartidores


def marcar_listo(actor_id, roles, entrega_id):
    return _ejecutar(
        operaciones_services.marcar_entrega_listo, actor_id, roles, entrega_id
    )


def confirmar_recojo_disponible(actor_id, roles, entrega_id):
    return _ejecutar(
        operaciones_services.confirmar_recojo_disponible,
        actor_id, roles, entrega_id,
    )


def programar(actor_id, roles, entrega_id, fecha_programada):
    return _ejecutar(
        operaciones_services.programar_entrega,
        actor_id, roles, entrega_id, fecha_programada,
    )


def asignar(actor_id, roles, entrega_id, repartidor_id):
    return _ejecutar(
        operaciones_services.asignar_repartidor,
        actor_id, roles, entrega_id, repartidor_id,
    )


def iniciar(actor_id, roles, entrega_id):
    return _ejecutar(
        operaciones_services.iniciar_reparto, actor_id, roles, entrega_id
    )


def confirmar_entrega(actor_id, roles, entrega_id, codigo_cliente):
    return _ejecutar(
        operaciones_services.confirmar_entrega,
        actor_id, roles, entrega_id, codigo_cliente,
    )


def confirmar_recojo(actor_id, roles, entrega_id, codigo_cliente):
    return _ejecutar(
        operaciones_services.confirmar_recojo,
        actor_id, roles, entrega_id, codigo_cliente,
    )


def confirmar_pago_anticipado(actor_id, roles, pedido_id):
    return _ejecutar(
        operaciones_services.confirmar_pago_anticipado,
        actor_id, roles, pedido_id,
    )


def registrar_incidencia(actor_id, roles, entrega_id, tipo, descripcion):
    return _ejecutar(
        operaciones_services.registrar_incidencia,
        actor_id, roles, entrega_id, tipo, descripcion,
    )


def resolver_incidencia(actor_id, roles, incidencia_id):
    return _ejecutar(
        operaciones_services.resolver_incidencia,
        actor_id, roles, incidencia_id,
    )


def cancelar(actor_id, roles, entrega_id, motivo):
    return _ejecutar(
        operaciones_services.cancelar_entrega,
        actor_id, roles, entrega_id, motivo,
    )


def actualizar_envio(actor_id, roles, entrega_id, estado_nuevo,
                     codigo_seguimiento=None, url_seguimiento=None,
                     ubicacion_texto=None):
    return _ejecutar(
        operaciones_services.actualizar_estado_envio,
        actor_id, roles, entrega_id, estado_nuevo,
        codigo_seguimiento=codigo_seguimiento,
        url_seguimiento=url_seguimiento,
        ubicacion_texto=ubicacion_texto,
    )


def registrar_repartidor(actor_id, roles, datos):
    """Registra un repartidor real validando y traduciendo errores."""
    return _ejecutar(
        operaciones_services.registrar_repartidor,
        actor_id=actor_id,
        roles=roles,
        correo=datos.get("correo"),
        password=datos.get("password"),
        nombres=datos.get("nombres"),
        apellido_paterno=datos.get("apellido_paterno"),
        apellido_materno=datos.get("apellido_materno"),
        telefono=datos.get("telefono"),
        dni=datos.get("dni"),
    )


def _etiqueta_pago(estado):
    return {
        "PENDIENTE": "Pendiente",
        "EN_REVISION": "En revisión",
        "PAGADO": "Pagado",
        "RECHAZADO": "Rechazado",
        "CANCELADO": "Cancelado",
        "REEMBOLSADO": "Reembolsado",
    }.get(str(estado or "").upper(), str(estado or "No registrado") or "No registrado")


def _incidencia_label(estado):
    return {
        "ABIERTA": "Abierta",
        "EN_REVISION": "En revisión",
        "RESUELTA": "Resuelta",
        "CERRADA": "Cerrada",
    }.get(str(estado or "").upper(), str(estado or "—") or "—")