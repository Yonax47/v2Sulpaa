"""
Servicios del módulo administrativo de Encuestas (Bloque 4).

Son envoltorios finos sobre el dominio ``app.encuestas``, que concentra
las reglas de negocio y las transacciones reales. El panel solo lee y
rehabilita invitaciones (nunca modifica respuestas).
"""

from app.encuestas.services import (
    ROLES_ENCUESTAS,
    ReglaEncuestaError,
    listar_encuestas as listar_del_dominio,
    obtener_detalle_encuesta as detalle_del_dominio,
    reenviar_invitacion as reenviar_del_dominio,
)

ROLES_ENCUESTAS_ADMIN = ROLES_ENCUESTAS


def listar_encuestas(filtros=None):
    """Lista encuestas con filtros de estado y período."""
    filtros = filtros or {}
    return listar_del_dominio({
        "estado": filtros.get("estado"),
        "desde": filtros.get("desde"),
        "hasta": filtros.get("hasta"),
    })


def obtener_detalle(encuesta_id):
    """Devuelve la encuesta con su respuesta y eventos."""
    detalle = detalle_del_dominio(encuesta_id)
    if not detalle:
        raise ReglaEncuestaError("La encuesta no existe.")
    return detalle


def reenviar(actor_id, roles, encuesta_id):
    """Rehabilita la invitación PORTAL y audita el reintento."""
    return reenviar_del_dominio(actor_id, roles, encuesta_id)