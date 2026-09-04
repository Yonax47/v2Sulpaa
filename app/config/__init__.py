"""Configuración compartida de SULPAA."""

from app.config.database import (
	conexion_comercio,
	conexion_identidad,
	conexion_inventario,
	conexion_operaciones,
	crear_conexion,
)

__all__ = [
	"conexion_comercio",
	"conexion_identidad",
	"conexion_inventario",
	"conexion_operaciones", 
	"crear_conexion",
]
