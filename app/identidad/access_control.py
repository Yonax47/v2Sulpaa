"""Cálculos puros para ventanas y duración de bloqueos de acceso."""

from datetime import timedelta


def evaluar_fallo_contador(
    *,
    intentos,
    ventana_inicia_en,
    bloqueado_hasta,
    ahora,
    limite,
    ventana_minutos,
    bloqueo_minutos,
):
    """Calcula el siguiente estado de un contador tras un fallo.

    La ventana empieza con el primer fallo. Al cumplirse exactamente su
    duración, el contador anterior deja de participar y el fallo actual inicia
    una ventana nueva. Al alcanzar el límite, la expiración queda exactamente
    ``bloqueo_minutos`` después del instante actual.
    """

    if bloqueado_hasta and bloqueado_hasta > ahora:
        return {
            "intentos": int(intentos or 0),
            "ventana_inicia_en": ventana_inicia_en,
            "bloqueado_hasta": bloqueado_hasta,
            "bloqueo_nuevo": False,
            "bloqueo_vigente": True,
        }

    vencida = (
        not ventana_inicia_en
        or ahora >= ventana_inicia_en + timedelta(minutes=ventana_minutos)
    )
    if vencida:
        intentos = 0
        ventana_inicia_en = ahora

    intentos = int(intentos or 0) + 1
    bloqueo_nuevo = intentos >= limite
    bloqueado_hasta = (
        ahora + timedelta(minutes=bloqueo_minutos)
        if bloqueo_nuevo
        else None
    )
    return {
        "intentos": intentos,
        "ventana_inicia_en": ventana_inicia_en,
        "bloqueado_hasta": bloqueado_hasta,
        "bloqueo_nuevo": bloqueo_nuevo,
        "bloqueo_vigente": False,
    }
