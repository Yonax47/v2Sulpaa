"""Lógica del módulo administrativo de Usuarios y Roles.

Reglas principales:

1. NADIE se guarda "a medias": usuario + perfil + roles se escriben
   en una sola transacción (repositorio). Si algo falla, se revierte
   y el mensaje lo dice; nunca se muestra "guardado" sin ser cierto.
2. Correo y DNI son únicos (se comprueba antes y lo refuerza la BD).
3. La contraseña se guarda SIEMPRE con bcrypt; nunca en texto plano.
4. Roles: se trabaja con los códigos REALES del catálogo (roles).
5. Solo el rol GERENTE puede conceder o retirar el rol GERENTE.
6. Cada cambio real (crear, activar/desactivar, asignar roles) deja
   un evento en la auditoría DESPUÉS de confirmarse.
"""

import logging
import uuid

import bcrypt

from app.admin.auditoria.services import registrar_evento
from app.admin.usuarios import repositories as repos
from app.shared.validators import (
    normalizar_telefono,
    validar_correo,
    validar_dni,
    validar_nombre,
    validar_password,
    validar_telefono_peru,
)

logger = logging.getLogger(__name__)

# Roles con acceso a la administración de usuarios.
ROLES_USUARIOS = ("GERENTE", "ADMINISTRADOR")

# Código del rol gerencial que solo GERENTE puede otorgar/quitar.
ROL_GERENTE = "GERENTE"

ESTADOS_USUARIO = ("ACTIVO", "INACTIVO", "SUSPENDIDO")


class ErrorUsuarios(Exception):
    """Error de negocio del módulo Usuarios y Roles."""


def _puede_administrar(roles):
    return bool(set(roles or []) & set(ROLES_USUARIOS))


def _es_gerente(roles):
    return ROL_GERENTE in set(roles or [])


def _exigir_permiso(roles):
    if not _puede_administrar(roles):
        raise PermissionError("No autorizado para administrar usuarios.")


def listar_roles_admin(roles):
    """Catálogo de roles activos (para selects y filtros)."""
    _exigir_permiso(roles)
    return repos.listar_roles()


def listar_usuarios_admin(roles, filtros=None, pagina=1, por_pagina=20):
    """Lista paginada de usuarios con sus roles reales."""
    _exigir_permiso(roles)

    filtros = dict(filtros or {})
    try:
        pagina = max(1, int(pagina))
    except (TypeError, ValueError):
        pagina = 1
    try:
        por_pagina = int(por_pagina)
    except (TypeError, ValueError):
        por_pagina = 20
    por_pagina = max(5, min(100, por_pagina))

    total = repos.contar_usuarios(filtros)
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    if pagina > paginas:
        pagina = paginas

    filas = repos.listar_usuarios(
        filtros,
        limite=por_pagina,
        offset=(pagina - 1) * por_pagina,
    )
    usuarios = []
    for fila in filas:
        fila = dict(fila)
        fila["roles_lista"] = (
            [codigo for codigo in (fila.get("roles_csv") or "").split(",") if codigo]
        )
        usuarios.append(fila)

    return {
        "ok": True,
        "usuarios": usuarios,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": paginas,
        "filtros": filtros,
    }


def obtener_usuario_admin(roles, usuario_id):
    """Detalle de un usuario (para edición de roles y estado)."""
    _exigir_permiso(roles)
    return repos.obtener_usuario(usuario_id)


def crear_usuario_admin(roles, actor_id, actor_roles, datos, direccion_ip=None):
    """Crea un usuario interno con sus roles en una sola transacción.

    Devuelve el id del usuario creado. Si algo falla, lanza
    ErrorUsuarios con un mensaje claro y NO deja nada grabado.
    """
    _exigir_permiso(roles)

    correo = (datos.get("correo") or "").strip().lower()
    nombres = (datos.get("nombres") or "").strip()
    apellido_paterno = (datos.get("apellido_paterno") or "").strip()
    apellido_materno = (datos.get("apellido_materno") or "").strip() or None
    dni = (datos.get("dni") or "").strip() or None
    telefono = normalizar_telefono(datos.get("telefono") or "")
    password = datos.get("password") or ""

    valido, mensaje = validar_correo(correo)
    if not valido:
        raise ErrorUsuarios(mensaje)

    valido, mensaje = validar_nombre(nombres, "Los nombres", obligatorio=True)
    if not valido:
        raise ErrorUsuarios(mensaje)

    valido, mensaje = validar_nombre(
        apellido_paterno, "El apellido paterno", obligatorio=True
    )
    if not valido:
        raise ErrorUsuarios(mensaje)

    valido, mensaje = validar_nombre(
        apellido_materno, "El apellido materno", obligatorio=False
    )
    if not valido:
        raise ErrorUsuarios(mensaje)

    valido, mensaje = validar_dni(dni, obligatorio=False)
    if not valido:
        raise ErrorUsuarios(mensaje)

    valido, mensaje = validar_telefono_peru(telefono, obligatorio=True)
    if not valido:
        raise ErrorUsuarios(mensaje)

    valido, mensaje = validar_password(password)
    if not valido:
        raise ErrorUsuarios(mensaje)

    if repos.correo_existe(correo):
        raise ErrorUsuarios("Ya existe una cuenta con ese correo.")

    if dni and repos.dni_existe(dni):
        raise ErrorUsuarios("El DNI ya se encuentra registrado.")

    # Roles solicitados: se validan contra el catálogo real.
    roles_catalogo = {fila["codigo"]: fila["id"] for fila in repos.listar_roles()}
    codigos_solicitados = [
        codigo for codigo in (datos.get("roles") or []) if codigo
    ]
    for codigo in codigos_solicitados:
        if codigo not in roles_catalogo:
            raise ErrorUsuarios("El rol '%s' no existe." % codigo)
    if ROL_GERENTE in codigos_solicitados and not _es_gerente(actor_roles):
        raise ErrorUsuarios(
            "Solo un gerente puede asignar el rol GERENTE."
        )

    rol_ids = [roles_catalogo[codigo] for codigo in dict.fromkeys(codigos_solicitados)]

    usuario_id = str(uuid.uuid4())
    perfil_id = str(uuid.uuid4())
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    try:
        repos.crear_usuario_con_roles(
            usuario_id=usuario_id,
            perfil_id=perfil_id,
            correo=correo,
            password_hash=password_hash,
            nombres=nombres,
            apellido_paterno=apellido_paterno,
            apellido_materno=apellido_materno,
            dni=dni,
            telefono=telefono,
            rol_ids=rol_ids,
            asignado_por=actor_id,
        )
    except Exception:
        logger.exception("Falló la creación del usuario %s", correo)
        registrar_evento(
            usuario_id=actor_id,
            modulo="USUARIOS",
            entidad="usuario",
            accion="CREAR_USUARIO",
            rol_actual=actor_roles,
            entidad_id=None,
            tipo_operacion="CREAR",
            resultado="FALLO",
            detalle="No se pudo crear el usuario %s." % correo,
            direccion_ip=direccion_ip,
        )
        raise ErrorUsuarios(
            "No se pudo guardar el usuario. No se registró ningún cambio."
        )

    registrar_evento(
        usuario_id=actor_id,
        modulo="USUARIOS",
        entidad="usuario",
        accion="CREAR_USUARIO",
        rol_actual=actor_roles,
        entidad_id=usuario_id,
        tipo_operacion="CREAR",
        resultado="EXITO",
        detalle="Usuario %s creado con roles: %s."
        % (correo, ", ".join(codigos_solicitados) or "sin roles"),
        datos_nuevos={"correo": correo, "roles": codigos_solicitados},
        direccion_ip=direccion_ip,
    )
    return usuario_id


def cambiar_estado_usuario_admin(
    roles, actor_id, actor_roles, usuario_id, nuevo_estado, direccion_ip=None
):
    """Activa o desactiva una cuenta. Nunca permite auto-desactivarse."""
    _exigir_permiso(roles)

    nuevo_estado = (nuevo_estado or "").strip().upper()
    if nuevo_estado not in ESTADOS_USUARIO:
        raise ErrorUsuarios("Estado de usuario inválido.")

    usuario = repos.obtener_usuario(usuario_id)
    if not usuario:
        raise ErrorUsuarios("El usuario no existe.")

    if usuario_id == actor_id and nuevo_estado != "ACTIVO":
        raise ErrorUsuarios("No puedes desactivar tu propia cuenta.")

    estado_anterior = usuario["estado"]
    if estado_anterior == nuevo_estado:
        return True

    repos.actualizar_estado_usuario(usuario_id, nuevo_estado)

    registrar_evento(
        usuario_id=actor_id,
        modulo="USUARIOS",
        entidad="usuario",
        accion="CAMBIAR_ESTADO",
        rol_actual=actor_roles,
        entidad_id=usuario_id,
        tipo_operacion="ACTUALIZAR",
        resultado="EXITO",
        detalle="Estado de %s: %s -> %s."
        % (usuario["correo"], estado_anterior, nuevo_estado),
        datos_anteriores={"estado": estado_anterior},
        datos_nuevos={"estado": nuevo_estado},
        direccion_ip=direccion_ip,
    )
    return True


def asignar_roles_usuario_admin(
    roles, actor_id, actor_roles, usuario_id, codigos, direccion_ip=None
):
    """Deja al usuario EXACTAMENTE con los roles indicados.

    Solo GERENTE puede conceder o retirar el rol GERENTE.
    """
    _exigir_permiso(roles)

    usuario = repos.obtener_usuario(usuario_id)
    if not usuario:
        raise ErrorUsuarios("El usuario no existe.")

    catalogo = {fila["codigo"]: fila["id"] for fila in repos.listar_roles()}
    codigos_nuevos = list(dict.fromkeys(codigo for codigo in (codigos or []) if codigo))
    for codigo in codigos_nuevos:
        if codigo not in catalogo:
            raise ErrorUsuarios("El rol '%s' no existe." % codigo)

    anteriores = [fila["codigo"] for fila in usuario["roles"]]

    toca_gerente = ROL_GERENTE in anteriores or ROL_GERENTE in codigos_nuevos
    if toca_gerente and not _es_gerente(actor_roles):
        raise ErrorUsuarios("Solo un gerente puede gestionar el rol GERENTE.")

    if usuario_id == actor_id and ROL_GERENTE not in codigos_nuevos:
        raise ErrorUsuarios("No puedes retirarte tu propio rol GERENTE.")

    if anteriores == codigos_nuevos:
        return True

    rol_ids = [catalogo[codigo] for codigo in codigos_nuevos]
    repos.reemplazar_roles(usuario_id, rol_ids, asignado_por=actor_id)

    registrar_evento(
        usuario_id=actor_id,
        modulo="USUARIOS",
        entidad="usuario_roles",
        accion="ASIGNAR_ROLES",
        rol_actual=actor_roles,
        entidad_id=usuario_id,
        tipo_operacion="ACTUALIZAR",
        resultado="EXITO",
        detalle="Roles de %s: [%s] -> [%s]."
        % (
            usuario["correo"],
            ", ".join(anteriores),
            ", ".join(codigos_nuevos),
        ),
        datos_anteriores={"roles": anteriores},
        datos_nuevos={"roles": codigos_nuevos},
        direccion_ip=direccion_ip,
    )
    return True
