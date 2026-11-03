"""
Configuración central de acceso a las bases de datos de SULPAA.

Este archivo es la única fuente de configuración de conexiones.
Los demás módulos no deben crear conexiones PyMySQL manualmente.

Optimización de rendimiento:

Cada repositorio abre una conexión nueva y la cierra al terminar. Eso
obliga a pagar el coste de conectar (red + autenticación) varias veces
por página. Para evitarlo, dentro de UNA misma solicitud HTTP se
reutiliza una conexión por esquema; al terminar la solicitud todas las
conexiones reutilizadas se cierran de verdad.

El número de conexiones reutilizadas por proceso está limitado para no
agotar `max_user_connections` de MariaDB. Si se alcanza el límite, se
vuelve al comportamiento anterior: abrir y cerrar cada conexión.
"""

import os
import threading

import pymysql
from dotenv import load_dotenv
from flask import current_app, g, has_app_context


# Carga las variables definidas en el archivo .env.
load_dotenv()


# ============================================================
# AISLAMIENTO DEL ENTORNO DE PRUEBAS
# ============================================================

# Los cuatro dominios usan estas variables. En pruebas se agrega ``_TEST``;
# nunca se toma el valor productivo como respaldo porque un error de
# configuración no debe terminar escribiendo en Alwaysdata.
VARIABLES_ESQUEMA = {
    "DB_IDENTIDAD": "identidad",
    "DB_COMERCIO": "comercio",
    "DB_INVENTARIO": "inventario",
    "DB_OPERACIONES": "operaciones",
}
VARIABLES_PRUEBA_OBLIGATORIAS = (
    "DB_HOST_TEST",
    "DB_PORT_TEST",
    "DB_USER_TEST",
    "DB_PASSWORD_TEST",
    "DB_IDENTIDAD_TEST",
    "DB_COMERCIO_TEST",
    "DB_INVENTARIO_TEST",
    "DB_OPERACIONES_TEST",
    "DB_TEST_SCHEMA_PREFIX",
)
ESQUEMAS_PRODUCTIVOS_CONOCIDOS = frozenset({
    "base1sulpaa_identidad",
    "base1sulpaa_comercio",
    "base1sulpaa_inventario",
    "base1sulpaa_operaciones",
})


def _es_marcador_ejemplo(valor):
    """Reconoce valores de plantilla que nunca deben llegar a una conexión."""

    texto = str(valor or "").strip()
    return not texto or (texto.startswith("<") and texto.endswith(">"))


def _valor_verdadero(valor):
    """Interpreta los valores comunes usados en variables booleanas."""

    return str(valor or "").strip().lower() in ("1", "true", "yes", "on")


def modo_pruebas_activo():
    """Indica si las conexiones deben usar exclusivamente la configuración TEST.

    El ejecutor oficial define ``SULPAA_TESTING=1`` antes de importar la
    aplicación. También se reconoce ``app.testing`` para proteger pruebas que
    creen una aplicación Flask directamente.
    """

    if _valor_verdadero(os.getenv("SULPAA_TESTING")):
        return True
    return has_app_context() and bool(current_app.testing)


def validar_configuracion_pruebas():
    """Valida todas las variables TEST antes de abrir una conexión.

    La función falla de forma cerrada: si falta un dato, un esquema no tiene
    el prefijo autorizado, coincide con producción o se reutiliza el usuario
    productivo, no se llama a PyMySQL. El resultado solo contiene valores del
    entorno de pruebas y nunca completa campos con variables de producción.
    """

    faltantes = [
        variable
        for variable in VARIABLES_PRUEBA_OBLIGATORIAS
        if variable not in os.environ
    ]
    if faltantes:
        raise RuntimeError(
            "Falta configurar el entorno aislado de pruebas: "
            + ", ".join(faltantes)
        )

    host = str(os.environ["DB_HOST_TEST"]).strip()
    usuario = str(os.environ["DB_USER_TEST"]).strip()
    prefijo = str(os.environ["DB_TEST_SCHEMA_PREFIX"]).strip()
    password = os.environ["DB_PASSWORD_TEST"]
    if any(_es_marcador_ejemplo(valor) for valor in (
        host, usuario, password, prefijo
    )):
        raise RuntimeError(
            "La configuración TEST contiene campos vacíos o marcadores de "
            "ejemplo."
        )
    if not prefijo.replace("_", "a").isalnum():
        raise RuntimeError("DB_TEST_SCHEMA_PREFIX contiene caracteres inválidos.")

    try:
        puerto = int(os.environ["DB_PORT_TEST"])
    except (TypeError, ValueError):
        raise RuntimeError("DB_PORT_TEST debe ser un número válido.") from None
    if not 1 <= puerto <= 65535:
        raise RuntimeError("DB_PORT_TEST debe estar entre 1 y 65535.")

    esquemas = {}
    productivos_configurados = {
        str(os.getenv(variable) or "").strip().lower()
        for variable in VARIABLES_ESQUEMA
        if str(os.getenv(variable) or "").strip()
    }
    prohibidos = set(ESQUEMAS_PRODUCTIVOS_CONOCIDOS) | productivos_configurados

    for variable, dominio in VARIABLES_ESQUEMA.items():
        nombre = str(os.environ[f"{variable}_TEST"]).strip()
        if not nombre or not nombre.replace("_", "a").isalnum():
            raise RuntimeError(f"{variable}_TEST no es un esquema MySQL válido.")
        if nombre.lower() in prohibidos:
            raise RuntimeError(
                f"{variable}_TEST apunta a un esquema productivo prohibido."
            )
        if not nombre.startswith(prefijo):
            raise RuntimeError(
                f"{variable}_TEST debe comenzar con el prefijo de pruebas."
            )
        esquemas[dominio] = nombre

    if len(set(esquemas.values())) != len(esquemas):
        raise RuntimeError("Cada dominio debe usar un esquema TEST diferente.")

    usuario_productivo = str(os.getenv("DB_USER") or "").strip()
    if usuario_productivo and usuario == usuario_productivo:
        raise RuntimeError(
            "DB_USER_TEST debe ser diferente del usuario de producción."
        )

    host_productivo = str(os.getenv("DB_HOST") or "").strip().lower()
    if host_productivo and host.lower() == host_productivo:
        raise RuntimeError(
            "DB_HOST_TEST debe ser diferente del host de producción."
        )

    password_productivo = os.getenv("DB_PASSWORD")
    if password_productivo and password == password_productivo:
        raise RuntimeError(
            "DB_PASSWORD_TEST debe ser diferente de la contraseña productiva."
        )

    return {
        "host": host,
        "port": puerto,
        "user": usuario,
        "password": password,
        "esquemas": esquemas,
    }


def nombre_esquema(variable):
    """Resuelve un esquema productivo o TEST según el entorno actual."""

    if variable not in VARIABLES_ESQUEMA:
        raise RuntimeError(f"La variable {variable} no pertenece a SULPAA.")
    if modo_pruebas_activo():
        configuracion = validar_configuracion_pruebas()
        return configuracion["esquemas"][VARIABLES_ESQUEMA[variable]]

    nombre = str(os.getenv(variable) or "").strip()
    if not nombre or not nombre.replace("_", "a").isalnum():
        raise RuntimeError(f"La variable {variable} no contiene un esquema válido.")
    return nombre


# ============================================================
# LÍMITES DE CONEXIONES REUTILIZADAS
# ============================================================

# Cuántas conexiones puede conservar abiertas cada proceso mientras
# atiende solicitudes. Se puede ajustar con DB_MAX_CONEXIONES_CACHE.
try:
    MAX_CONEXIONES_CACHE = max(
        1,
        int(os.getenv("DB_MAX_CONEXIONES_CACHE", "8")),
    )
except ValueError:
    MAX_CONEXIONES_CACHE = 8


_conexiones_reservadas = 0
_cerrojo_conexiones = threading.Lock()


def _reservar_hueco():
    """Reserva un hueco del límite del proceso. True si hay espacio."""
    global _conexiones_reservadas

    with _cerrojo_conexiones:
        if _conexiones_reservadas >= MAX_CONEXIONES_CACHE:
            return False
        _conexiones_reservadas += 1
        return True


def _liberar_hueco():
    """Devuelve un hueco cuando una conexión reutilizada se cierra."""
    global _conexiones_reservadas

    with _cerrojo_conexiones:
        if _conexiones_reservadas > 0:
            _conexiones_reservadas -= 1


# ============================================================
# CONEXIÓN COMPARTIDA DURANTE UNA SOLICITUD
# ============================================================

class _ConexionCompartida:
    """
    Envuelve una conexión que se reutiliza durante la solicitud.

    Los repositorios ya cierran su conexión en ``finally``. Aquí
    ``close()`` no cierra nada: la conexión sigue viva hasta que Flask
    termina la solicitud. Cualquier otro método o atributo se delega a
    la conexión real, por lo que el comportamiento es idéntico.
    """

    def __init__(self, conexion):
        object.__setattr__(self, "_conexion", conexion)

    def close(self):
        """No cierra la conexión: se cierra al final de la solicitud."""

    def __getattr__(self, nombre):
        return getattr(self._conexion, nombre)

    def __setattr__(self, nombre, valor):
        setattr(self._conexion, nombre, valor)


def cerrar_conexiones_solicitud(_error=None):
    """
    Cierra de verdad las conexiones reutilizadas de la solicitud.

    Flask llama a esta función al terminar cada solicitud (también
    cuando hubo un error), así que ninguna conexión queda abierta
    fuera de su solicitud.
    """

    if not has_app_context():
        return

    cache = g.pop("_conexiones_sulpaa", None)

    if not cache:
        return

    for conexion in cache.values():

        try:
            conexion._conexion.close()
        except Exception:
            # Una conexión que ya no responde no debe romper la
            # respuesta al usuario; el proceso la descarta igual.
            pass
        finally:
            _liberar_hueco()


# ============================================================
# CREACIÓN DE CONEXIONES
# ============================================================

def _conexion_nueva(nombre_base_datos):
    """Abre una conexión nueva usando el entorno que corresponda."""

    if modo_pruebas_activo():
        configuracion = validar_configuracion_pruebas()
        if nombre_base_datos not in configuracion["esquemas"].values():
            raise RuntimeError(
                "La prueba intentó conectarse a un esquema no autorizado."
            )
        host = configuracion["host"]
        puerto = configuracion["port"]
        usuario = configuracion["user"]
        password = configuracion["password"]
    else:
        host = os.getenv("DB_HOST", "localhost")
        puerto = int(os.getenv("DB_PORT", "3306"))
        usuario = os.getenv("DB_USER", "root")
        password = os.getenv("DB_PASSWORD", "")

    return pymysql.connect(
        host=host,
        port=puerto,
        user=usuario,
        password=password,
        database=nombre_base_datos,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def crear_conexion(nombre_base_datos: str, reutilizar: bool = True):
    """
    Crea (o reutiliza) una conexión a una base de datos de SULPAA.

    Args:
        nombre_base_datos: Nombre de la base de datos destino.
        reutilizar: Si es False se abre una conexión independiente que
            debe cerrarse de verdad. Se usa en transacciones que
            controlan su propio commit/rollback.

    Returns:
        pymysql.Connection: Conexión configurada con DictCursor.
    """

    if not reutilizar or not has_app_context():
        return _conexion_nueva(nombre_base_datos)

    cache = getattr(g, "_conexiones_sulpaa", None)

    if cache is None:
        cache = {}
        g._conexiones_sulpaa = cache

    conexion = cache.get(nombre_base_datos)

    if conexion is not None:

        # Si algo cerró la conexión real, se descarta y se abre otra.
        if conexion._conexion.open:
            return conexion

        cache.pop(nombre_base_datos, None)
        _liberar_hueco()

    # Sin hueco disponible se mantiene el comportamiento anterior:
    # una conexión nueva que el repositorio cierra al terminar.
    if not _reservar_hueco():
        return _conexion_nueva(nombre_base_datos)

    try:
        conexion = _ConexionCompartida(
            _conexion_nueva(nombre_base_datos)
        )
    except Exception:
        _liberar_hueco()
        raise

    cache[nombre_base_datos] = conexion

    return conexion


def conexion_identidad():
    """Retorna una conexión al dominio de Identidad."""
    return crear_conexion(nombre_esquema("DB_IDENTIDAD"))


def conexion_comercio():
    """Retorna una conexión al dominio de Comercio."""
    return crear_conexion(nombre_esquema("DB_COMERCIO"))


def conexion_inventario():
    """Retorna una conexión al dominio de Inventario."""
    return crear_conexion(nombre_esquema("DB_INVENTARIO"))


def conexion_operaciones():
    """Retorna una conexión al dominio de Operaciones."""
    return crear_conexion(nombre_esquema("DB_OPERACIONES"))
