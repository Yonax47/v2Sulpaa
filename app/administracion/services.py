"""
Servicios del módulo Administración de SULPAA V2.
"""

from app.administracion.repositories import (
    obtener_perfil_administrador,
    actualizar_perfil_administrador,
)

from app.shared.validators import (
    validar_nombre,
    validar_telefono_peru,
    normalizar_telefono,
)


def obtener_perfil_admin(usuario_id):
    perfil = obtener_perfil_administrador(usuario_id)

    if not perfil:
        return {
            "ok": False,
            "mensaje": "No se encontró el perfil del administrador.",
        }

    return {"ok": True, "perfil": perfil}


def actualizar_perfil_admin(
    usuario_id,
    nombres,
    apellido_paterno,
    apellido_materno,
    telefono,
):
    nombres = (nombres or "").strip()
    apellido_paterno = (apellido_paterno or "").strip()
    apellido_materno = (apellido_materno or "").strip() or None
    telefono = normalizar_telefono(telefono)

    valido, mensaje = validar_nombre(nombres, "Los nombres", obligatorio=True)
    if not valido:
        return {"ok": False, "mensaje": mensaje}

    valido, mensaje = validar_nombre(
        apellido_paterno, "El apellido paterno", obligatorio=True
    )
    if not valido:
        return {"ok": False, "mensaje": mensaje}

    valido, mensaje = validar_telefono_peru(telefono, obligatorio=True)
    if not valido:
        return {"ok": False, "mensaje": mensaje}

    actualizar_perfil_administrador(
        usuario_id=usuario_id,
        nombres=nombres,
        apellido_paterno=apellido_paterno,
        apellido_materno=apellido_materno,
        telefono=telefono,
    )

    return {"ok": True, "mensaje": "Perfil actualizado correctamente."}