"""Servicio de solo lectura para constancias informativas de compra."""

import re

from app.comercio.pdf import generar_pdf_constancia
from app.comercio.repositories import (
    obtener_detalles_pedido,
    obtener_pedido_usuario,
)
from app.identidad.repositories import obtener_nombre_cliente_constancia
from app.operaciones.repositories import obtener_entrega_pedido, obtener_pago_pedido


_ESTADOS_PEDIDO = {
    "CREADO": "Creado",
    "CONFIRMADO": "Confirmado",
    "EN_PREPARACION": "En preparación",
    "LISTO": "Listo",
    "EN_CAMINO": "En camino",
    "COMPLETADO": "Completado",
    "CANCELADO": "Cancelado",
}

_TIPOS_ENTREGA = {
    "RECOJO_LOCAL": "Recojo local",
    "DELIVERY_LOCAL": "Delivery local",
    "TRANSPORTISTA_ASOCIADO": "Transportista asociado",
}


def _texto(valor, maximo=250):
    """Normaliza texto para PDF sin conservar controles invisibles."""

    limpio = " ".join(str(valor or "").replace("\x00", "").split())
    return limpio[:maximo]


def _datos_entrega(entrega):
    if not entrega:
        return None

    tipo = str(entrega.get("tipo_entrega") or "").upper()
    resultado = {
        "tipo": _TIPOS_ENTREGA.get(tipo, _texto(tipo) or "No especificado"),
        "estado": _texto(entrega.get("estado")) or "No especificado",
    }

    if tipo == "RECOJO_LOCAL" and entrega.get("recojo"):
        recojo = entrega["recojo"]
        resultado.update({
            "destino": _texto(recojo.get("nombre_punto")),
            "direccion": _texto(recojo.get("direccion")),
        })
    elif tipo == "DELIVERY_LOCAL" and entrega.get("delivery"):
        delivery = entrega["delivery"]
        resultado.update({
            "destino": "Dirección de entrega",
            "direccion": _texto(delivery.get("direccion")),
            "referencia": _texto(delivery.get("referencia")),
        })
    elif tipo == "TRANSPORTISTA_ASOCIADO" and entrega.get("transportista"):
        envio = entrega["transportista"]
        resultado.update({
            "destino": _texto(envio.get("sucursal_destino")),
            "direccion": _texto(envio.get("direccion_destino")),
            "transportista": _texto(envio.get("transportista_nombre")),
            "servicio": _texto(envio.get("servicio_nombre")),
        })

    return resultado


def obtener_datos_constancia(usuario_id, pedido_id):
    """Obtiene exclusivamente datos backend de un pedido propio."""

    if not usuario_id or not pedido_id:
        return None

    pedido = obtener_pedido_usuario(usuario_id=usuario_id, pedido_id=pedido_id)
    if not pedido:
        return None

    detalles = obtener_detalles_pedido(pedido_id)
    pago = obtener_pago_pedido(pedido_id)
    entrega = obtener_entrega_pedido(pedido_id)
    nombre_cliente = obtener_nombre_cliente_constancia(usuario_id)

    return {
        "empresa": "Corporación Sulpaa S.A.C.",
        "numero_pedido": _texto(pedido.get("numero_pedido"), 60),
        "fecha": pedido.get("creado_en"),
        "cliente": _texto(nombre_cliente, 180) or "Cliente SULPAA",
        "estado": _ESTADOS_PEDIDO.get(
            pedido.get("estado"), _texto(pedido.get("estado")) or "No especificado"
        ),
        "moneda": _texto(pedido.get("moneda"), 10) or "PEN",
        "productos": [
            {
                "nombre": _texto(detalle.get("nombre_articulo"), 220),
                "cantidad": int(detalle.get("cantidad") or 0),
                "precio_unitario": float(detalle.get("precio_unitario") or 0),
                "subtotal": float(detalle.get("subtotal_linea") or 0),
            }
            for detalle in detalles
        ],
        "subtotal": float(pedido.get("subtotal") or 0),
        "descuento": float(pedido.get("descuento_total") or 0),
        "costo_entrega": float(pedido.get("costo_entrega") or 0),
        "total": float(pedido.get("total") or 0),
        "metodo_pago": _texto(pago.get("metodo_nombre"), 120) if pago else None,
        "modalidad_pago": _texto(pago.get("modalidad"), 80) if pago else None,
        "entrega": _datos_entrega(entrega),
    }


def nombre_archivo_constancia(numero_pedido):
    seguro = re.sub(r"[^A-Za-z0-9_-]+", "-", str(numero_pedido or "pedido"))
    seguro = seguro.strip("-_")[:80] or "pedido"
    return f"constancia-compra-{seguro}.pdf"


def generar_constancia_compra(usuario_id, pedido_id):
    """Genera bytes en memoria; no crea ni modifica registros."""

    datos = obtener_datos_constancia(usuario_id, pedido_id)
    if not datos:
        return None
    return {
        "contenido": generar_pdf_constancia(datos),
        "nombre_archivo": nombre_archivo_constancia(datos["numero_pedido"]),
    }
