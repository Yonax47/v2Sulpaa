"""Unidad de trabajo para operaciones atómicas entre esquemas SULPAA."""

import os
import re

from app.config.database import crear_conexion


_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")


def _nombre_esquema(variable):
    """Lee y valida un esquema configurado, nunca recibido desde HTTP."""
    nombre = str(os.getenv(variable) or "").strip()
    if not nombre or not _IDENTIFICADOR_SQL.fullmatch(nombre):
        raise RuntimeError(
            f"La variable {variable} no contiene un esquema MySQL válido."
        )
    return nombre


def esquemas_sulpaa():
    """Devuelve los nombres confiables usados en SQL entre esquemas."""
    return {
        "comercio": _nombre_esquema("DB_COMERCIO"),
        "operaciones": _nombre_esquema("DB_OPERACIONES"),
        "identidad": _nombre_esquema("DB_IDENTIDAD"),
    }


class UnidadTrabajo:
    """Controla una conexión, un commit único y rollback ante cualquier fallo.

    MySQL permite que una misma transacción InnoDB modifique tablas de varios
    esquemas cuando comparten servidor y credenciales. Los repositorios reciben
    ``conexion`` y no confirman por separado; el Service conserva así la
    responsabilidad de decidir cuándo la operación completa es consistente.
    """

    def __init__(self):
        self.esquemas = esquemas_sulpaa()
        self.conexion = None
        self._confirmada = False

    def __enter__(self):
        self.conexion = crear_conexion(self.esquemas["comercio"])
        return self

    def confirmar(self):
        """Confirma todas las escrituras coordinadas por el Service."""
        self.conexion.commit()
        self._confirmada = True

    def revertir(self):
        """Revierte explícitamente la operación sin ocultar su causa."""
        if self.conexion:
            self.conexion.rollback()

    def __exit__(self, tipo_error, error, traza):
        try:
            if self.conexion and (tipo_error is not None or not self._confirmada):
                self.conexion.rollback()
        finally:
            if self.conexion:
                self.conexion.close()
        return False
