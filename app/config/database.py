"""Configuración central de las cuatro bases SQL Server de SULPAA."""

import os
import re

import pyodbc
from dotenv import load_dotenv


# Carga las variables definidas en el archivo .env.
load_dotenv()


class CursorDiccionario:
    """Adaptador para conservar el contrato de cursores existente."""

    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback):
        self.close()

    @staticmethod
    def _fila_a_diccionario(columnas, fila):
        if fila is None:
            return None
        return dict(zip(columnas, tuple(fila)))

    @staticmethod
    def _adaptar_limit(consulta):
        """Convierte cada ``LIMIT 1`` en ``SELECT TOP 1``."""

        coincidencias = list(re.finditer(
            r"\bLIMIT\s+1\b",
            consulta,
            flags=re.IGNORECASE,
        ))

        for coincidencia in reversed(coincidencias):
            profundidad = 0
            profundidad_limit = 0

            for caracter in consulta[:coincidencia.start()]:
                if caracter == "(":
                    profundidad += 1
                elif caracter == ")":
                    profundidad -= 1

            profundidad_limit = profundidad
            candidatos = list(re.finditer(
                r"\bSELECT\b",
                consulta[:coincidencia.start()],
                flags=re.IGNORECASE,
            ))

            for candidato in reversed(candidatos):
                profundidad_select = 0
                for caracter in consulta[:candidato.start()]:
                    if caracter == "(":
                        profundidad_select += 1
                    elif caracter == ")":
                        profundidad_select -= 1

                if profundidad_select == profundidad_limit:
                    despues = consulta[candidato.end():]
                    consulta = (
                        consulta[:coincidencia.start()]
                        + consulta[coincidencia.end():]
                    )
                    if not re.match(r"\s+TOP\s+1\b", despues, re.IGNORECASE):
                        consulta = (
                            consulta[:candidato.end()]
                            + " TOP 1"
                            + consulta[candidato.end():]
                        )
                    break

        return consulta

    def execute(self, consulta, parametros=()):
        consulta = re.sub(r"%s", "?", consulta)
        consulta = re.sub(r"\bNOW\(\)", "GETDATE()", consulta, flags=re.IGNORECASE)
        consulta = re.sub(r"\bTRUE\b", "1", consulta, flags=re.IGNORECASE)
        consulta = re.sub(r"\bFALSE\b", "0", consulta, flags=re.IGNORECASE)
        consulta = re.sub(r"\s+FOR\s+UPDATE\b", "", consulta, flags=re.IGNORECASE)
        consulta = self._adaptar_limit(consulta)
        return self._cursor.execute(consulta, parametros)

    def fetchone(self):
        columnas = [columna[0] for columna in self._cursor.description]
        return self._fila_a_diccionario(columnas, self._cursor.fetchone())

    def fetchall(self):
        columnas = [columna[0] for columna in self._cursor.description]
        return [
            self._fila_a_diccionario(columnas, fila)
            for fila in self._cursor.fetchall()
        ]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        self._cursor.close()


class ConexionSQLServer:
    """Conexión con cursores compatibles con los repositorios actuales."""

    def __init__(self, conexion):
        self._conexion = conexion

    def cursor(self):
        return CursorDiccionario(self._conexion.cursor())

    def commit(self):
        self._conexion.commit()

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        self._conexion.close()


def _variable_por_dominio(prefijo, nombre, valor_predeterminado=None):
    """Lee una variable específica del dominio con fallback global."""

    return os.getenv(
        f"{prefijo}_DB_{nombre}",
        os.getenv(f"DB_{nombre}", valor_predeterminado),
    )


def crear_conexion(nombre_base_datos=None, prefijo=None):
    """
    Crea una conexión a una base de datos de SULPAA.

    Args:
        nombre_base_datos: Nombre de la base de datos destino.

    Returns:
        ConexionSQLServer: Conexión con cursores que devuelven diccionarios.
    """
    if prefijo:
        nombre_base_datos = _variable_por_dominio(
            prefijo,
            "NAME",
            nombre_base_datos,
        )

    if not nombre_base_datos:
        raise ValueError("Falta configurar el nombre de una base de datos SQL Server.")

    servidor = _variable_por_dominio(prefijo, "HOST", "localhost")
    puerto = _variable_por_dominio(prefijo, "PORT", "1433")
    controlador = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    usuario = _variable_por_dominio(prefijo, "USER")
    password = _variable_por_dominio(prefijo, "PASSWORD")
    confianza = _variable_por_dominio(
        prefijo,
        "TRUSTED_CONNECTION",
        "no",
    ).lower() in {"1", "true", "yes"}

    servidor_sql = (
        servidor
        if servidor.lower().startswith(("lpc:", "np:", "admin:"))
        else f"{servidor},{puerto}"
    )

    partes = [
        f"DRIVER={{{controlador}}}",
        f"SERVER={servidor_sql}",
        f"DATABASE={nombre_base_datos}",
        f"Encrypt={_variable_por_dominio(prefijo, 'ENCRYPT', 'yes')}",
        "TrustServerCertificate="
        f"{_variable_por_dominio(prefijo, 'TRUST_SERVER_CERTIFICATE', 'yes')}",
    ]

    if confianza:
        partes.append("Trusted_Connection=yes")
    else:
        if not usuario or password is None:
            raise ValueError("Configura DB_USER y DB_PASSWORD para SQL Server.")
        partes.extend([
            f"UID={usuario}",
            f"PWD={password}",
        ])

    return ConexionSQLServer(pyodbc.connect(";".join(partes), autocommit=False))


def conexion_identidad():
    """Retorna una conexión al dominio de Identidad."""
    return crear_conexion(prefijo="IDENTIDAD")


def conexion_comercio():
    """Retorna una conexión al dominio de Comercio."""
    return crear_conexion(prefijo="COMERCIO")


def conexion_inventario():
    """Retorna una conexión al dominio de Inventario."""
    return crear_conexion(prefijo="INVENTARIO")


def conexion_operaciones():
    """Retorna una conexión al dominio de Operaciones."""
    return crear_conexion(prefijo="OPERACIONES")