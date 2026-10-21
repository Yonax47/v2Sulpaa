"""
Punto de entrada de SULPAA V2.

En producción (Railway u otro PaaS) el servidor lo levanta
Gunicorn mediante el Procfile:

    web: gunicorn -c gunicorn.conf.py run:app

Gunicorn importa este módulo y toma el objeto `app` que se
crea a nivel de módulo. El bloque `if __name__ == "__main__"`
SÓLO se usa para desarrollo local.

Variables de entorno utilizadas aquí:

- FLASK_ENV  -> "production" desactiva el depurador.
- HOST       -> interfaz de escucha en desarrollo.
- PORT       -> puerto en desarrollo.
"""

import os

from app import create_app


# La aplicación se crea al importar el módulo, de modo que
# tanto Gunicorn como el modo local usan la misma instancia.
app = create_app()


if __name__ == "__main__":

    # En producción NUNCA se activa el depurador.
    # En desarrollo se puede forzar con FLASK_DEBUG=1.
    entorno_produccion = (
        os.getenv("FLASK_ENV", "").strip().lower() == "production"
    )

    debug = (not entorno_produccion) and (
        os.getenv("FLASK_DEBUG", "0").strip() == "1"
    )

    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=debug,
    )
