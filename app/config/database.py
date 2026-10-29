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
from flask import g, has_app_context


# Carga las variables definidas en el archivo .env.
load_dotenv()


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
    """Abre una conexión PyMySQL nueva, sin reutilización."""
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
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
    return crear_conexion(os.getenv("DB_IDENTIDAD"))


def conexion_comercio():
    """Retorna una conexión al dominio de Comercio."""
    return crear_conexion(os.getenv("DB_COMERCIO"))


def conexion_inventario():
    """Retorna una conexión al dominio de Inventario."""
    return crear_conexion(os.getenv("DB_INVENTARIO"))


def conexion_operaciones():
    """Retorna una conexión al dominio de Operaciones."""
    return crear_conexion(os.getenv("DB_OPERACIONES"))
