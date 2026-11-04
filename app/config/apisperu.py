"""Configuración del rate limit distribuido para APIsPERU."""

import os


def _booleano(nombre, predeterminado=False):
    valor = os.getenv(nombre)
    if valor is None:
        return predeterminado
    return valor.strip().lower() in {"1", "true", "yes", "on"}


def _entero(nombre, predeterminado, minimo, maximo):
    try:
        valor = int(os.getenv(nombre, str(predeterminado)))
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{nombre} debe ser un entero.") from error
    if not minimo <= valor <= maximo:
        raise RuntimeError(
            f"{nombre} debe estar entre {minimo} y {maximo}."
        )
    return valor


def configurar_apisperu(app):
    """Mantiene el contador apagado hasta aprobar explícitamente 005."""

    solicitado = _booleano("APISPERU_RATE_LIMIT_ENABLED", False)
    migracion_aprobada = _booleano(
        "APISPERU_RATE_LIMIT_MIGRATION_APPROVED", False
    )
    clave = str(os.getenv("APISPERU_RATE_LIMIT_KEY") or "").strip()

    if solicitado and not migracion_aprobada:
        raise RuntimeError(
            "APISPERU_RATE_LIMIT_ENABLED requiere confirmar primero la "
            "migración 005 con APISPERU_RATE_LIMIT_MIGRATION_APPROVED=1."
        )
    if solicitado and len(clave) < 32:
        raise RuntimeError(
            "APISPERU_RATE_LIMIT_KEY debe tener al menos 32 caracteres."
        )

    app.config.update({
        "APISPERU_RATE_LIMIT_ENABLED": bool(
            solicitado and migracion_aprobada
        ),
        "APISPERU_RATE_LIMIT_MIGRATION_APPROVED": migracion_aprobada,
        "APISPERU_RATE_LIMIT_KEY": clave,
        "APISPERU_RATE_LIMIT_MAX_DNI": _entero(
            "APISPERU_RATE_LIMIT_MAX_DNI", 5, 1, 100
        ),
        "APISPERU_RATE_LIMIT_MAX_RUC": _entero(
            "APISPERU_RATE_LIMIT_MAX_RUC", 5, 1, 100
        ),
        "APISPERU_RATE_LIMIT_WINDOW_SECONDS": _entero(
            "APISPERU_RATE_LIMIT_WINDOW_SECONDS", 600, 30, 86400
        ),
    })
