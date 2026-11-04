"""
Servicios del módulo administrativo de Encuestas (Bloque 4).

Son envoltorios finos sobre el dominio ``app.encuestas``, que concentra
las reglas de negocio y las transacciones reales. El panel solo lee y
rehabilita invitaciones (nunca modifica respuestas).
"""

from app.encuestas.services import (
    ROLES_ENCUESTAS,
    ReglaEncuestaError,
    agregar_encuestas as agregar_del_dominio,
    listar_encuestas as listar_del_dominio,
    obtener_detalle_encuesta as detalle_del_dominio,
    reenviar_invitacion as reenviar_del_dominio,
)

ROLES_ENCUESTAS_ADMIN = ROLES_ENCUESTAS


def listar_encuestas(filtros=None, pagina=None, por_pagina=25):
    """Lista encuestas con filtros de estado y período."""
    filtros = filtros or {}
    return listar_del_dominio({
        "estado": filtros.get("estado"),
        "desde": filtros.get("desde"),
        "hasta": filtros.get("hasta"),
    }, pagina=pagina, por_pagina=por_pagina)


def estadisticas_encuestas(encuestas):
    """Agrega conteos reales por estado y satisfacción (sin inventar).

    Se calcula sobre la MISMA lista que se muestra, por lo que el
    gráfico siempre coincide con la tabla. La satisfacción solo
    promedia calificaciones realmente respondidas (1..5).
    """
    por_estado = {}
    calificaciones = []
    recomendarian = 0
    respuestas = 0

    for encuesta in encuestas or []:
        estado = encuesta.get("estado") or "SIN_ESTADO"
        por_estado[estado] = por_estado.get(estado, 0) + 1

        calificacion = encuesta.get("calificacion_general")
        if calificacion is not None:
            respuestas += 1
            try:
                calificaciones.append(float(calificacion))
            except (TypeError, ValueError):
                pass

        if encuesta.get("recomendaria") in (1, True) or str(
            encuesta.get("recomendaria") or ""
        ).strip().upper() in ("SI", "1"):
            recomendarian += 1

    promedio = (
        round(sum(calificaciones) / len(calificaciones), 2)
        if calificaciones
        else None
    )

    return {
        "por_estado": [
            {"estado": estado, "cantidad": cantidad}
            for estado, cantidad in sorted(por_estado.items())
        ],
        "respuestas": respuestas,
        "promedio": promedio,
        "recomendarian": recomendarian,
    }


def estadisticas_encuestas_filtradas(filtros=None):
    """Agrega TODO el conjunto filtrado, no solo la página visible.

    La analítica del panel debe describir el período consultado; usar
    ``estadisticas_encuestas(encuestas)`` limitaba los totales a las 25
    filas de la página y los hacía cambiar al paginar.
    """
    filas = agregar_del_dominio(filtros or {})
    por_estado = []
    respuestas = 0
    suma_calificaciones = 0.0
    recomendarian = 0

    for fila in filas or []:
        por_estado.append({
            "estado": fila.get("estado") or "SIN_ESTADO",
            "cantidad": int(fila.get("cantidad") or 0),
        })
        respuestas += int(fila.get("respuestas") or 0)
        suma_calificaciones += float(fila.get("suma") or 0)
        recomendarian += int(fila.get("recomendarian") or 0)

    promedio = (
        round(suma_calificaciones / respuestas, 2) if respuestas else None
    )
    return {
        "por_estado": por_estado,
        "respuestas": respuestas,
        "promedio": promedio,
        "recomendarian": recomendarian,
    }


def obtener_detalle(encuesta_id):
    """Devuelve la encuesta con su respuesta y eventos."""
    detalle = detalle_del_dominio(encuesta_id)
    if not detalle:
        raise ReglaEncuestaError("La encuesta no existe.")
    return detalle


def reenviar(actor_id, roles, encuesta_id):
    """Rehabilita la invitación PORTAL y audita el reintento."""
    return reenviar_del_dominio(actor_id, roles, encuesta_id)