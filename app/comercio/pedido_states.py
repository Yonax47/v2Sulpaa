"""Contrato central de estados comerciales de un pedido.

Este módulo evita que rutas y plantillas decidan transiciones mediante
comparaciones dispersas. La fase operativa actual habilita únicamente
CREADO -> CONFIRMADO -> EN_PREPARACION; los estados terminales quedan
definidos para conservar el contrato global, pero no exponen acciones
administrativas.

EN_PREPARACION es el tercer estado canónico del PEDIDO y coincide con el
estado EN_PREPARACION de la ENTREGA, pero son dominios independientes:
ambos persistidos en tablas distintas y con responsabilidades distintas.
"""

ESTADO_CREADO = "CREADO"
ESTADO_CONFIRMADO = "CONFIRMADO"
ESTADO_EN_PREPARACION = "EN_PREPARACION"
ESTADO_COMPLETADO = "COMPLETADO"
ESTADO_CANCELADO = "CANCELADO"

ESTADOS_PEDIDO = frozenset({
    ESTADO_CREADO,
    ESTADO_CONFIRMADO,
    ESTADO_EN_PREPARACION,
    ESTADO_COMPLETADO,
    ESTADO_CANCELADO,
})

# Solo estas aristas están operativas en el primer bloque. COMPLETADO y
# CANCELADO no aparecen porque sus reglas integrales pertenecen a fases futuras.
TRANSICIONES_HABILITADAS = {
    ESTADO_CREADO: frozenset({ESTADO_CONFIRMADO}),
    ESTADO_CONFIRMADO: frozenset({ESTADO_EN_PREPARACION}),
}

ETIQUETAS_ESTADO_PEDIDO = {
    ESTADO_CREADO: "Pedido recibido",
    ESTADO_CONFIRMADO: "Pedido confirmado",
    ESTADO_EN_PREPARACION: "En preparación",
    ESTADO_COMPLETADO: "Completado",
    ESTADO_CANCELADO: "Cancelado",
}


def normalizar_estado(estado):
    """Normaliza un estado para compararlo contra el contrato canónico."""
    return str(estado or "").strip().upper()


def transicion_permitida(estado_anterior, estado_nuevo):
    """Indica si una transición está habilitada en la fase actual."""
    anterior = normalizar_estado(estado_anterior)
    nuevo = normalizar_estado(estado_nuevo)
    return nuevo in TRANSICIONES_HABILITADAS.get(anterior, frozenset())


def etiqueta_estado_pedido(estado):
    """Entrega una etiqueta legible sin alterar el valor persistido."""
    estado_normalizado = normalizar_estado(estado)
    return ETIQUETAS_ESTADO_PEDIDO.get(
        estado_normalizado,
        estado_normalizado or "—",
    )
