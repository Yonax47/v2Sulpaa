"""Reglas de negocio del módulo Mi perfil."""

from app.identidad.repositories import listar_direcciones_usuario
from app.identidad.services import (
    listar_departamentos,
    registrar_direccion_usuario,
    registrar_facturacion_checkout,
)
from app.perfil import repositories
from app.shared.validators import normalizar_telefono, validar_telefono_peru


# Roles que la interfaz muestra con acceso directo al perfil. La lista es
# informativa: el autoservicio no depende de ella porque una cuenta recién
# registrada puede no tener todavía filas en ``usuario_roles``.
ROLES_PERFIL = frozenset({
    "CLIENTE", "REPARTIDOR", "VENDEDOR", "ADMINISTRADOR", "GERENTE",
})


class ErrorPerfil(Exception):
    """Error seguro de autorización o validación del perfil."""


def _validar_acceso(usuario_id, roles=None):
    """Exige una cuenta autenticada; jamás un identificador de otro usuario.

    ``login_required`` ya revalidó la sesión y el estado ACTIVO antes de
    llamar a este servicio. No se exige un rol concreto para no bloquear a
    cuentas nuevas sin rol asignado. Todos los repositorios reciben el
    ``usuario_id`` tomado de la sesión, nunca de un formulario o de la URL.
    """

    if not usuario_id:
        raise ErrorPerfil("No fue posible identificar la cuenta autenticada.")


def obtener_mi_perfil(usuario_id, roles):
    _validar_acceso(usuario_id, roles)
    perfil = repositories.obtener_perfil(usuario_id)
    if not perfil:
        raise ErrorPerfil("No se encontró un perfil activo para esta cuenta.")
    return {
        "perfil": perfil,
        "direcciones": listar_direcciones_usuario(usuario_id),
        "facturacion": repositories.listar_facturacion(usuario_id),
        "departamentos": listar_departamentos(),
    }


def actualizar_mi_telefono(usuario_id, roles, telefono):
    _validar_acceso(usuario_id, roles)
    telefono = normalizar_telefono(telefono)
    valido, mensaje = validar_telefono_peru(telefono, obligatorio=True)
    if not valido:
        raise ErrorPerfil(mensaje)
    if not repositories.obtener_perfil(usuario_id):
        raise ErrorPerfil("No se encontró un perfil activo para esta cuenta.")
    repositories.actualizar_telefono(usuario_id, telefono)
    return {"ok": True, "mensaje": "Teléfono actualizado correctamente."}


def crear_mi_direccion(usuario_id, roles, datos):
    _validar_acceso(usuario_id, roles)
    # La primera dirección activa siempre debe ser principal para que el
    # checkout tenga una opción válida desde el primer uso.
    existentes = listar_direcciones_usuario(usuario_id)
    es_principal = datos.get("es_principal") in {True, "1", "on"}
    if not existentes or not any(item.get("es_principal") for item in existentes):
        # La primera dirección, o la única que quede si los datos históricos
        # no tienen principal, se convierte en la opción por defecto.
        es_principal = True

    resultado = registrar_direccion_usuario(
        usuario_id=usuario_id,
        distrito_id=datos.get("distrito_id"),
        direccion=datos.get("direccion"),
        referencia=datos.get("referencia"),
        alias=datos.get("alias"),
        es_principal=es_principal,
    )
    if not resultado.get("ok"):
        raise ErrorPerfil(resultado.get("mensaje") or "Dirección inválida.")
    return resultado


def elegir_direccion_principal(usuario_id, roles, direccion_id):
    _validar_acceso(usuario_id, roles)
    if not repositories.marcar_direccion_principal(usuario_id, direccion_id):
        raise ErrorPerfil("La dirección indicada no está disponible.")
    return {"ok": True, "mensaje": "Dirección principal actualizada."}


def desactivar_mi_direccion(usuario_id, roles, direccion_id):
    _validar_acceso(usuario_id, roles)
    if not repositories.desactivar_direccion(usuario_id, direccion_id):
        raise ErrorPerfil("La dirección indicada no está disponible.")
    return {"ok": True, "mensaje": "Dirección desactivada correctamente."}


def crear_mi_facturacion(usuario_id, roles, tipo, documento):
    _validar_acceso(usuario_id, roles)
    resultado = registrar_facturacion_checkout(
        usuario_id=usuario_id,
        tipo_comprobante=tipo,
        documento=documento,
    )
    if not resultado.get("ok"):
        raise ErrorPerfil(resultado.get("mensaje") or "Datos inválidos.")
    return resultado


def elegir_facturacion_predeterminada(usuario_id, roles, facturacion_id):
    _validar_acceso(usuario_id, roles)
    if not repositories.marcar_facturacion_predeterminada(
        usuario_id, facturacion_id
    ):
        raise ErrorPerfil("Los datos de facturación no están disponibles.")
    return {"ok": True, "mensaje": "Facturación predeterminada actualizada."}


def desactivar_mi_facturacion(usuario_id, roles, facturacion_id):
    _validar_acceso(usuario_id, roles)
    if not repositories.desactivar_facturacion(usuario_id, facturacion_id):
        raise ErrorPerfil("Los datos de facturación no están disponibles.")
    return {"ok": True, "mensaje": "Datos de facturación desactivados."}
