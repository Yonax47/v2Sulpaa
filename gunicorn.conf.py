"""
Configuración de Gunicorn para SULPAA V2 en Railway.

Railway (y cualquier otro PaaS) expone el puerto de escucha
a través de la variable de entorno PORT. Gunicorn NO lee esa
variable por sí solo, por lo que este archivo la traduce.

Diseño:
- Escucha en 0.0.0.0 (necesario en contenedores).
- Puerto tomado de PORT, con 8000 como respaldo local.
- Se usa el modo thread ("gthread") porque la aplicación abre
  conexiones MySQL por petición y es más ligero en memoria
  que varios procesos de workers.
- Logs a stdout/stderr para que Railway los capture.

Este archivo NO contiene secretos: sólo lectura de entorno.
"""

import os


# ============================================================
# PUERTO DE ESCUCHA
# ============================================================
#
# Railway inyecta PORT automáticamente. No se puede fijar
# un puerto concreto en el contenedor.
# ============================================================

bind = "0.0.0.0:%s" % os.getenv("PORT", "8000")


# ============================================================
# PROCESOS Y HILOS
# ============================================================
#
# Una sola aplicación + hilos es suficiente para este sistema:
# cada petición abre y cierra sus propias conexiones MySQL
# con pymysql, sin estado compartido en memoria.
# ============================================================

workers = int(os.getenv("GUNICORN_WORKERS", "2"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "8"))


# ============================================================
# TIEMPOS LÍMITE
# ============================================================
#
# El checkout y los reportes administrativos pueden tardar
# más que el valor por defecto de Gunicorn (30 s).
# ============================================================

timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5


# ============================================================
# SEGURIDAD Y RENDIMIENTO
# ============================================================

# Se desactiva la verificación de la versión de Flask porque
# la fábrica ya valida su propia configuración al arrancar.
check_config = False

# Sólo se registran peticiones anómalas; el resto va a stdout.
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Gunicorn no debe servir la aplicación en modo debug.
reload = False
