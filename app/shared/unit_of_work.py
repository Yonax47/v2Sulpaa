"""Unidad de trabajo para operaciones atómicas entre esquemas SULPAA."""

from app.config.database import crear_conexion, nombre_esquema


def esquemas_sulpaa():
    """Devuelve los nombres confiables usados en SQL entre esquemas."""
    return {
        "comercio": nombre_esquema("DB_COMERCIO"),
        "operaciones": nombre_esquema("DB_OPERACIONES"),
        "identidad": nombre_esquema("DB_IDENTIDAD"),
        "inventario": nombre_esquema("DB_INVENTARIO"),
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
        # Esta conexión NO se reutiliza: la unidad de trabajo necesita
        # un commit/rollback propio y aislado de las lecturas de la
        # solicitud.
        self.conexion = crear_conexion(
            self.esquemas["comercio"],
            reutilizar=False,
        )
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
