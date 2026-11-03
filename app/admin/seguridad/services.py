"""Reglas del centro administrativo de seguridad de accesos."""

import ipaddress
from datetime import datetime

from app.admin.seguridad import repositories as repos


ESTADOS = frozenset({"ACTIVO", "EXPIRADO", "DESBLOQUEADO"})


def _autorizar_gerente(roles):
    """Impide que otros roles consulten o modifiquen bloqueos."""

    if "GERENTE" not in set(roles or []):
        raise PermissionError("Solo GERENTE administra bloqueos de acceso.")


def normalizar_filtros(filtros):
    """Limpia filtros de pantalla sin convertirlos en fragmentos SQL."""

    datos = dict(filtros or {})
    cuenta = str(datos.get("cuenta") or "").strip().lower()[:150]
    ip = str(datos.get("ip") or "").strip()
    if ip:
        try:
            ip = ipaddress.ip_address(ip).compressed
        except ValueError:
            ip = ""
    estado = str(datos.get("estado") or "").strip().upper()
    if estado not in ESTADOS:
        estado = ""
    def fecha(clave, fin=False):
        """Acepta solo fechas ISO y completa el límite del día."""

        texto = str(datos.get(clave) or "").strip()[:10]
        if not texto:
            return ""
        try:
            datetime.strptime(texto, "%Y-%m-%d")
        except ValueError:
            return ""
        return texto + (" 23:59:59" if fin else " 00:00:00")

    return {
        "cuenta": cuenta,
        "ip": ip,
        "estado": estado,
        "desde": fecha("desde"),
        "hasta": fecha("hasta", fin=True),
    }


def formatear_tiempo_restante(segundos):
    """Convierte segundos restantes en un texto corto para la interfaz."""

    total = max(0, int(segundos or 0))
    minutos, segundos = divmod(total, 60)
    horas, minutos = divmod(minutos, 60)
    if horas:
        return f"{horas} h {minutos} min"
    if minutos:
        return f"{minutos} min {segundos} s"
    return f"{segundos} s"


def listar_centro_seguridad(roles, filtros=None, pagina=1, por_pagina=25):
    """Obtiene indicadores, bloqueos paginados y desbloqueos recientes."""

    _autorizar_gerente(roles)
    filtros = normalizar_filtros(filtros)
    try:
        pagina = max(1, int(pagina))
    except (TypeError, ValueError):
        pagina = 1
    try:
        por_pagina = max(5, min(100, int(por_pagina)))
    except (TypeError, ValueError):
        por_pagina = 25

    total = repos.contar_bloqueos(filtros)
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = min(pagina, paginas)
    bloqueos = repos.listar_bloqueos(
        filtros, por_pagina, (pagina - 1) * por_pagina
    )
    for bloqueo in bloqueos:
        bloqueo["tiempo_restante"] = formatear_tiempo_restante(
            bloqueo.get("segundos_restantes")
        )
    return {
        "indicadores": repos.obtener_indicadores(filtros),
        "bloqueos": bloqueos,
        "desbloqueos": repos.listar_desbloqueos(limite=10),
        "filtros": filtros,
        "total": total,
        "pagina": pagina,
        "paginas": paginas,
        "por_pagina": por_pagina,
    }


def obtener_detalle_bloqueo(roles, bloqueo_id):
    """Devuelve un bloqueo con su historial de desbloqueo, si existe."""

    _autorizar_gerente(roles)
    bloqueo = repos.obtener_bloqueo(bloqueo_id)
    if not bloqueo:
        return None
    bloqueo["tiempo_restante"] = formatear_tiempo_restante(
        bloqueo.get("segundos_restantes")
    )
    bloqueo["desbloqueos"] = repos.listar_desbloqueos(bloqueo_id)
    return bloqueo


def desbloquear_acceso(roles, bloqueo_id, actor_id, motivo, direccion_ip):
    """Valida el motivo y delega el desbloqueo atómico al repositorio."""

    _autorizar_gerente(roles)
    motivo = str(motivo or "").strip()
    if len(motivo) < 5 or len(motivo) > 500:
        return {
            "ok": False,
            "mensaje": "Indica un motivo de entre 5 y 500 caracteres.",
        }
    if not actor_id or not direccion_ip:
        return {
            "ok": False,
            "mensaje": "No se pudo verificar al responsable del desbloqueo.",
        }

    estado = repos.desbloquear_bloqueo(
        bloqueo_id, actor_id, motivo, direccion_ip
    )
    mensajes = {
        "DESBLOQUEADO": "El bloqueo fue finalizado correctamente.",
        "NO_EXISTE": "El bloqueo solicitado no existe.",
        "YA_DESBLOQUEADO": "El bloqueo ya había sido desbloqueado.",
        "EXPIRADO": "El bloqueo ya expiró y no requiere intervención.",
    }
    return {
        "ok": estado == "DESBLOQUEADO",
        "estado": estado,
        "mensaje": mensajes[estado],
    }
