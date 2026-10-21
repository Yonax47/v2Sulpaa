"""Lógica del módulo administrativo de Auditoría.

Responsabilidades:

1. Ofrecer ``registrar_evento`` para que OTROS módulos dejen un
   rastro real de sus operaciones (crear, actualizar, eliminar,
   confirmar, cancelar, etc.), SIEMPRE después de confirmar el
   cambio en la base de datos.
2. Exponer la consulta de auditoría, restringida al rol
   gerencial real (``GERENTE``).

La auditoría es append-only: la interfaz solo permite consultar,
nunca editar ni eliminar eventos.
"""

import json
import logging

from app.admin.auditoria import repositories as repos

logger = logging.getLogger(__name__)

# El rol gerencial real (dump identidad) con acceso a la auditoría.
ROLES_AUDITORIA = ("GERENTE",)


def _permitido(roles):
    """El único rol autorizado a ver la auditoría es GERENTE."""
    return bool(set(roles or []) & set(ROLES_AUDITORIA))


def registrar_evento(
    usuario_id,
    modulo,
    entidad,
    accion,
    rol_actual=None,
    entidad_id=None,
    tipo_operacion=None,
    resultado="EXITO",
    detalle=None,
    datos_anteriores=None,
    datos_nuevos=None,
    direccion_ip=None,
):
    """Registra un evento de auditoría sin romper la operación original.

    Se llama SIEMPRE después de que la operación principal ya quedó
    confirmada. Si la auditoría falla, se registra en el log y se
    devuelve False; nunca se propaga la excepción para no revertir
    un cambio que ya fue válido.
    """
    rol_texto = ",".join(sorted(set(rol_actual or []))) if rol_actual else None

    datos_nuevos_completos = {
        "resultado": resultado,
        "tipo_operacion": tipo_operacion,
        "actor_rol": rol_texto,
        "detalle": detalle,
    }
    if datos_nuevos:
        datos_nuevos_completos.update(datos_nuevos)

    try:
        repos.insertar_evento(
            usuario_id=usuario_id,
            modulo=modulo,
            entidad=entidad,
            accion=accion,
            entidad_id=entidad_id,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos_completos,
            direccion_ip=direccion_ip,
        )
        return True
    except Exception:
        logger.exception(
            "No se pudo registrar el evento de auditoría %s/%s",
            modulo,
            accion,
        )
        return False


def _enriquecer(fila):
    """Añade campos legibles y separa resultado/tipo del JSON guardado."""
    fila = dict(fila)

    rol_csv = fila.get("usuario_roles")
    fila["usuario_roles_lista"] = (
        [codigo for codigo in rol_csv.split(",") if codigo]
        if rol_csv
        else []
    )

    nuevo = {}
    anterior = {}
    if fila.get("datos_nuevos"):
        try:
            parseado = json.loads(fila["datos_nuevos"])
            if isinstance(parseado, dict):
                nuevo = parseado
        except (ValueError, TypeError):
            nuevo = {}
    if fila.get("datos_anteriores"):
        try:
            parseado = json.loads(fila["datos_anteriores"])
            if isinstance(parseado, dict):
                anterior = parseado
        except (ValueError, TypeError):
            anterior = {}

    fila["resultado"] = str(nuevo.get("resultado") or "EXITO").upper()
    fila["tipo_operacion"] = nuevo.get("tipo_operacion") or ""
    fila["detalle"] = nuevo.get("detalle") or ""
    fila["actor_rol"] = nuevo.get("actor_rol") or ""
    fila["nuevos"] = nuevo
    fila["anteriores"] = anterior
    fila["responsable"] = (
        fila.get("usuario_correo") or fila.get("usuario_id") or "sistema"
    )
    return fila


def listar_eventos_admin(roles, filtros=None, pagina=1, por_pagina=25):
    """Devuelve los eventos paginados para el gerente autorizado.

    Args:
        roles: roles ACTIVOS de la sesión.
        filtros: dict con usuario_id, modulo, accion, entidad, desde, hasta.
        pagina: página solicitada (>= 1).
        por_pagina: tamaño de página (entre 5 y 100).
    """
    if not _permitido(roles):
        raise PermissionError("No autorizado para consultar la auditoría.")

    filtros = dict(filtros or {})

    try:
        pagina = int(pagina)
    except (TypeError, ValueError):
        pagina = 1
    if pagina < 1:
        pagina = 1

    try:
        por_pagina = int(por_pagina)
    except (TypeError, ValueError):
        por_pagina = 25
    por_pagina = max(5, min(100, por_pagina))

    total = repos.contar_eventos(filtros)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    if pagina > total_paginas:
        pagina = total_paginas

    eventos = repos.listar_eventos(
        filtros,
        limite=por_pagina,
        offset=(pagina - 1) * por_pagina,
    )

    return {
        "ok": True,
        "eventos": [_enriquecer(fila) for fila in eventos],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": total_paginas,
        "filtros": filtros,
    }


def obtener_evento_admin(roles, evento_id):
    """Devuelve el detalle de un evento, solo para el gerente."""
    if not _permitido(roles):
        raise PermissionError("No autorizado para consultar la auditoría.")

    fila = repos.obtener_evento(evento_id)
    if not fila:
        return None
    return _enriquecer(fila)


def opciones_filtros(roles):
    """Catálogos reales para los selectores de filtro."""
    if not _permitido(roles):
        raise PermissionError("No autorizado para consultar la auditoría.")
    return {
        "modulos": repos.listar_modulos(),
        "acciones": repos.listar_acciones(),
    }
