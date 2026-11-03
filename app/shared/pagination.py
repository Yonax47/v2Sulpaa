"""Utilidades comunes para paginación administrativa del lado servidor."""

from math import ceil


PAGINA_PREDETERMINADA = 1
POR_PAGINA_PREDETERMINADO = 25
POR_PAGINA_MAXIMO = 100


def normalizar_paginacion(
    pagina=None,
    por_pagina=None,
    predeterminado=POR_PAGINA_PREDETERMINADO,
    maximo=POR_PAGINA_MAXIMO,
):
    """Convierte parámetros HTTP inseguros en límites enteros acotados."""
    try:
        pagina = int(pagina)
    except (TypeError, ValueError):
        pagina = PAGINA_PREDETERMINADA
    if pagina < 1:
        pagina = PAGINA_PREDETERMINADA

    try:
        por_pagina = int(por_pagina)
    except (TypeError, ValueError):
        por_pagina = predeterminado
    if por_pagina < 1 or por_pagina > maximo:
        por_pagina = predeterminado
    return pagina, por_pagina


def crear_paginacion(total, pagina, por_pagina, endpoint=None, filtros=None):
    """Crea metadatos consistentes y ajusta páginas fuera del rango real."""
    total = max(0, int(total or 0))
    pagina, por_pagina = normalizar_paginacion(pagina, por_pagina)
    paginas = max(1, ceil(total / por_pagina))
    pagina = min(pagina, paginas)
    return {
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "paginas": paginas,
        "offset": (pagina - 1) * por_pagina,
        "tiene_anterior": pagina > 1,
        "tiene_siguiente": pagina < paginas,
        "endpoint": endpoint,
        "filtros": {
            clave: valor
            for clave, valor in (filtros or {}).items()
            if valor not in (None, "", False)
        },
    }
