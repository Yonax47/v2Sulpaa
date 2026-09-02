"""
Configuración central de acceso a las bases de datos de SULPAA.

Este archivo es la única fuente de configuración de conexiones.
Los demás módulos no deben crear conexiones PyMySQL manualmente.
"""

import os

import pymysql
from dotenv import load_dotenv


# Carga las variables definidas en el archivo .env.
load_dotenv()


def crear_conexion(nombre_base_datos: str):
    """
    Crea una conexión a una base de datos de SULPAA.

    Args:
        nombre_base_datos: Nombre de la base de datos destino.

    Returns:
        pymysql.Connection: Conexión configurada con DictCursor.
    """
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