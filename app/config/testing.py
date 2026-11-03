"""Configuración central de seguridad para las pruebas automatizadas.

Por defecto, una aplicación de prueba conserva CSRF y la revalidación de
sesiones. Las pruebas antiguas que solo estudian reglas de negocio pueden
pedir una excepción explícita. Esa excepción nunca funciona fuera de
``TESTING``, aunque alguien coloque la bandera por error en producción.
"""


CLAVE_OMITIR_SEGURIDAD = "OMITIR_SEGURIDAD_EN_PRUEBAS"


def configurar_seguridad_pruebas(app):
    """Define valores seguros sin sobrescribir decisiones explícitas."""

    app.config.setdefault(CLAVE_OMITIR_SEGURIDAD, False)


def seguridad_puede_omitirse(app):
    """Autoriza la excepción únicamente en una prueba que la pidió."""

    return bool(
        app.testing
        and app.config.get(CLAVE_OMITIR_SEGURIDAD) is True
    )


def configurar_como_produccion(app):
    """Activa en pruebas los mismos controles de una aplicación normal."""

    app.config.update({
        "TESTING": True,
        CLAVE_OMITIR_SEGURIDAD: False,
        "CSRF_ENABLED": True,
    })
