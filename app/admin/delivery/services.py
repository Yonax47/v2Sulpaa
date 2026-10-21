"""Lógica del módulo administrativo de Configuración de Delivery.

Reglas principales:

1. La configuración se apoya en las tablas REALES del delivery.
2. La fórmula del costo NO se duplica aquí: se reutiliza
   ``calcular_costo_delivery_local`` de ``app.operaciones.services``,
   la misma que usa el checkout.
3. Solo GERENTE y ADMINISTRADOR pueden consultar; solo GERENTE
   puede modificar la tarifa (es información de dinero).
4. Cada cambio real deja un evento en la auditoría.
"""
import logging
from decimal import Decimal, InvalidOperation

from app.admin.auditoria.services import registrar_evento
from app.admin.delivery import repositories as repos
from app.operaciones.services import calcular_costo_delivery_local

logger = logging.getLogger(__name__)

ROLES_LECTURA = ("GERENTE", "ADMINISTRADOR")
ROLES_EDICION = ("GERENTE",)

# Campo editable => (etiqueta, admite_vacio).
CAMPOS_NUMERICOS = (
    ("tarifa_base", "Tarifa base", False),
    ("km_incluidos", "Kilómetros incluidos", False),
    ("precio_km_adicional", "Precio por km adicional", False),
    ("peso_incluido_kg", "Peso incluido (kg)", False),
    ("precio_kg_adicional", "Precio por kg adicional", False),
    ("distancia_maxima_km", "Distancia máxima (km)", True),
    ("peso_maximo_kg", "Peso máximo (kg)", True),
    ("monto_envio_gratis", "Monto para envío gratis", True),
)


class ErrorDelivery(Exception):
    """Error de negocio de la Configuración de Delivery."""


def _permitido_lectura(roles):
    return bool(set(roles or []) & set(ROLES_LECTURA))


def _permitido_edicion(roles):
    return bool(set(roles or []) & set(ROLES_EDICION))


def obtener_configuracion_delivery(roles):
    """Configuración completa de delivery para la vista administrativa."""
    if not _permitido_lectura(roles):
        raise PermissionError(
            "No autorizado para ver la configuración de delivery."
        )

    return {
        "ok": True,
        "puede_editar": _permitido_edicion(roles),
        "tarifa_activa": repos.obtener_tarifa_delivery_activa(),
        "tarifas": repos.listar_tarifas_delivery(),
        "transportistas": repos.listar_transportistas(),
        "tarifarios": repos.listar_tarifarios_transportista(),
        "coberturas": repos.listar_coberturas_activas(),
    }


def _a_decimal(valor, etiqueta, admite_vacio=False):
    """Convierte a Decimal sin inventar valores."""
    if valor is None or str(valor).strip() == "":
        if admite_vacio:
            return None, None
        return None, "%s es obligatorio." % etiqueta
    try:
        numero = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None, "%s debe ser un número válido." % etiqueta
    if numero < 0:
        return None, "%s no puede ser negativo." % etiqueta
    return numero, None


def validar_datos_tarifa(datos):
    """Valida y normaliza los campos editables de la tarifa.

    Devuelve (datos_limpios, error). No toca la base de datos.
    """
    datos = dict(datos or {})
    limpios = {"nombre": (datos.get("nombre") or "").strip()}

    if not limpios["nombre"]:
        return None, "El nombre de la tarifa es obligatorio."

    for campo, etiqueta, admite_vacio in CAMPOS_NUMERICOS:
        numero, error = _a_decimal(
            datos.get(campo), etiqueta, admite_vacio=admite_vacio
        )
        if error:
            return None, error
        if numero is None:
            limpios[campo] = None
        else:
            limpios[campo] = str(numero)

    return limpios, None


def actualizar_tarifa_delivery_admin(
    roles,
    actor_id,
    actor_roles,
    tarifa_id,
    datos,
    direccion_ip=None,
):
    """Valida, guarda y audita un cambio real de la tarifa de delivery."""
    if not _permitido_edicion(roles):
        raise PermissionError(
            "Solo un gerente puede modificar la tarifa de delivery."
        )

    tarifa = repos.obtener_tarifa_delivery_activa()
    if not tarifa or tarifa["id"] != tarifa_id:
        raise ErrorDelivery("No se encontró la tarifa activa indicada.")

    limpios, error = validar_datos_tarifa(datos)
    if error:
        raise ErrorDelivery(error)

    anteriores = {
        campo: (str(tarifa.get(campo)) if tarifa.get(campo) is not None else None)
        for campo, _, _ in CAMPOS_NUMERICOS
    }
    anteriores["nombre"] = tarifa.get("nombre")

    try:
        repos.actualizar_tarifa_delivery(tarifa_id, limpios)
    except Exception:
        logger.exception("Falló la actualización de la tarifa %s", tarifa_id)
        registrar_evento(
            usuario_id=actor_id,
            modulo="DELIVERY",
            entidad="tarifa_delivery",
            accion="ACTUALIZAR_TARIFA",
            rol_actual=actor_roles,
            entidad_id=tarifa_id,
            tipo_operacion="ACTUALIZAR",
            resultado="FALLO",
            detalle="No se pudo actualizar la tarifa de delivery.",
            direccion_ip=direccion_ip,
        )
        raise ErrorDelivery(
            "No se pudo guardar la tarifa. No se registró ningún cambio."
        )

    registrar_evento(
        usuario_id=actor_id,
        modulo="DELIVERY",
        entidad="tarifa_delivery",
        accion="ACTUALIZAR_TARIFA",
        rol_actual=actor_roles,
        entidad_id=tarifa_id,
        tipo_operacion="ACTUALIZAR",
        resultado="EXITO",
        detalle="Tarifa '%s' actualizada." % limpios["nombre"],
        datos_anteriores=anteriores,
        datos_nuevos=limpios,
        direccion_ip=direccion_ip,
    )
    return True


def simular_cotizacion(roles, distancia_km, peso_kg, subtotal, tarifa=None):
    """Simula el costo con la MISMA fórmula del checkout."""
    if not _permitido_lectura(roles):
        raise PermissionError("No autorizado para simular delivery.")

    tarifa = tarifa or repos.obtener_tarifa_delivery_activa()
    if not tarifa:
        raise ErrorDelivery("No existe una tarifa de delivery activa.")

    try:
        distancia = Decimal(str(distancia_km))
        peso = Decimal(str(peso_kg))
        subtotal_dec = Decimal(str(subtotal))
    except (InvalidOperation, ValueError, TypeError):
        raise ErrorDelivery("Distancia, peso y subtotal deben ser números.")

    if distancia <= 0:
        raise ErrorDelivery("La distancia debe ser mayor que cero.")
    if peso <= 0:
        raise ErrorDelivery("El peso debe ser mayor que cero.")
    if subtotal_dec < 0:
        raise ErrorDelivery("El subtotal no puede ser negativo.")

    return calcular_costo_delivery_local(
        tarifa, distancia, peso, subtotal_dec
    )
