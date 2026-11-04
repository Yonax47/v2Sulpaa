"""Pausa explícita de presentación: no escribe estados, precios ni inventario.

IDs cotejados por SELECT en Alwaysdata. No es una regla sobre imágenes/nombres.
Producto padre común: 6f80a651-a0ce-11f1-b084-088fc316d95e.
"""

SUFIJO = "-a0cf-11f1-b084-088fc316d95e"
VARIANTES_PAUSADAS_POR_SABOR = {
    "Arándanos": ("eedbf037", "eedbf059", "eedbf06e", "eedbf082", "eedbf098"),
    "Base Natural": ("eedbeeae", "eedbeed4", "eedbeee9", "eedbeefe", "eedbef1e"),
    "Fresa": ("eedbf0c1", "eedbf0d7", "eedbf0ec", "eedbf100", "eedbf120"),
    "Frutos Rojos": ("eedbef3c", "eedbef51", "eedbef66", "eedbef86", "eedbef9a"),
    "Maracuyá": ("eedbf1bd", "eedbf1d3", "eedbf1f4", "eedbf20a", "eedbf220"),
    "Menta": ("eedbefb9", "eedbefcf", "eedbefef", "eedbf005", "eedbf019"),
    "Naranja": ("eedbf13e", "eedbf155", "eedbf16b", "eedbf18a", "eedbf19e"),
    "Piña": ("eedbee2c", "eedbee45", "eedbee65", "eedbee7a", "eedbee90"),
}
VARIANTES_PAUSADAS = frozenset(
    prefijo + SUFIJO for grupo in VARIANTES_PAUSADAS_POR_SABOR.values() for prefijo in grupo
)


def filtrar_presentacion_tienda(datos):
    """Solo la proyección de la tienda; no cambia validaciones transaccionales."""
    def visibles(filas):
        return [fila for fila in filas if fila.get("variante_id") not in VARIANTES_PAUSADAS]

    return {
        **datos,
        "catalogo": visibles(datos["catalogo"]),
        "variantes_330": visibles(datos["variantes_330"]),
        "packs_personalizados": [
            {**pack, "variantes_permitidas": visibles(pack.get("variantes_permitidas", []))}
            for pack in datos["packs_personalizados"]
        ],
    }
