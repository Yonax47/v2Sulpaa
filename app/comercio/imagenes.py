"""
Imágenes reales del catálogo SULPAA.

============================================================
PROPÓSITO
============================================================

Esta es la ÚNICA fuente de verdad para decidir qué imagen le
corresponde a un producto, según su sabor y su presentación.

Antes cada página elegía la imagen por su cuenta (y a veces de
forma incorrecta). Por ejemplo, Favoritos mostraba SIEMPRE la
botella de Café sin importar el sabor. Ahora todas las páginas
( Tienda, Ficha, Favoritos y carrito ) usan estas mismas reglas.

============================================================
CÓMO DECIDE
============================================================

1. Usa datos confiables del catálogo: el sabor y la
   presentación. NO adivina a partir de textos largos como el
   nombre comercial, salvo para los packs (que no tienen sabor
   propio y sí lo llevan en su nombre).

2. Si ninguna imagen encaja, devuelve None. En ese caso la
   interfaz muestra un dibujo neutro (placeholder), nunca una
   imagen de otro sabor.

============================================================
IMÁGENES DISPONIBLES (reales)
============================================================

- Botellas 330 ml con foto propia por sabor:
  Café, Jamaica, Kion y Limón.

- Botella de 1 litro: una sola imagen genérica.

- Barril: una sola imagen genérica.

- Packs de 6 unidades: una foto por sabor (Café, Jamaica,
  Kion, Limón) y una foto de pack mixto.

Los demás sabores (Piña, Base Natural, Frutos Rojos, Menta,
Arándanos, Fresa, Naranja, Maracuyá...) todavía NO tienen foto
real; por eso se resuelven con el placeholder.
"""

import unicodedata


# ============================================================
# 1. RUTAS REALES DE LAS IMÁGENES
# ============================================================
# Las rutas son relativas a la carpeta /static, igual que las
# usa url_for('static', filename=...).

# Botella de 330 ml con foto propia, por sabor.
IMAGEN_BOTELLA_POR_SABOR = {
    "cafe": "img/BotellaCafe.webp",
    "jamaica": "img/Botellaflordejamaica.webp",
    "kion": "img/Botellakion.webp",
    "limon": "img/Botellalimon.webp",
}

# Pack de 6 unidades con foto propia, por sabor.
IMAGEN_PACK_POR_SABOR = {
    "cafe": "img/Pack6unidadescafe.jpg",
    "jamaica": "img/Pack6unidadesJamaica.jpg",
    "kion": "img/Pack6unidadeskion.jpg",
    "limon": "img/Pack6unidadeslimon.jpg",
}

# Imágenes genéricas (sirven para cualquier sabor).
IMAGEN_BARRIL = "img/Barrilsulpaa.webp"
IMAGEN_BOTELLA_LITRO = "img/Botellalitrosulpaa.webp"
IMAGEN_PACK_MIXTO = "img/Packmixto.jpg"


# ============================================================
# 2. NORMALIZAR TEXTO
# ============================================================

def _normalizar(texto):
    """
    Convierte un texto a una forma comparable.

    - Quita espacios de los extremos.
    - Pasa a minúsculas.
    - Elimina tildes (Café -> cafe, Limón -> limon).

    Así "Café" y "cafe" se consideran iguales, pero sin depender
    de coincidencias ambiguas de texto.
    """

    if texto is None:
        return ""

    limpio = str(texto).strip().lower()

    # Separamos cada carácter en su forma base + acento y nos
    # quedamos solo con la base (así "ó" se vuelve "o").
    descompuesto = unicodedata.normalize("NFKD", limpio)

    return "".join(
        caracter
        for caracter in descompuesto
        if not unicodedata.combining(caracter)
    )


# ============================================================
# 3. RESOLVER LA IMAGEN DE UN PRODUCTO
# ============================================================

def resolver_imagen_producto(
    sabor=None,
    presentacion=None,
    tipo=None,
    nombre=None,
):
    """
    Devuelve la ruta (relativa a /static) de la imagen real que
    le corresponde a un producto, o None si no hay imagen.

    Parámetros:
        sabor (str | None):
            Sabor real del catálogo (ej. "Café").
        presentacion (str | None):
            Presentación real (ej. "Botella 330 ml", "Barril 30 L").
        tipo (str | None):
            "VARIANTE" o "PACK". Los packs no tienen sabor propio.
        nombre (str | None):
            Nombre comercial o del pack. Se usa solo para saber
            qué sabor tiene un pack.
    """

    tipo_txt = _normalizar(tipo)
    sabor_txt = _normalizar(sabor)
    presentacion_txt = _normalizar(presentacion)
    nombre_txt = _normalizar(nombre)

    # --------------------------------------------------------
    # PACKS: usan una foto por sabor, o la del pack mixto.
    # --------------------------------------------------------
    es_pack = tipo_txt == "pack" or "pack" in presentacion_txt

    if es_pack:

        # El sabor del pack puede venir en el campo sabor o,
        # más frecuentemente, dentro del nombre del pack.
        for clave, ruta in IMAGEN_PACK_POR_SABOR.items():

            if clave == sabor_txt or clave in nombre_txt:

                return ruta

        # Si no reconocemos el sabor, es un pack combinado.
        return IMAGEN_PACK_MIXTO

    # --------------------------------------------------------
    # BARRILES: cambian de forma, no de sabor.
    # --------------------------------------------------------
    if "barril" in presentacion_txt:

        return IMAGEN_BARRIL

    # --------------------------------------------------------
    # BOTELLA DE 1 LITRO: imagen genérica real.
    # --------------------------------------------------------
    if "1 l" in presentacion_txt or "litro" in presentacion_txt:

        return IMAGEN_BOTELLA_LITRO

    # --------------------------------------------------------
    # BOTELLAS CON FOTO PROPIA POR SABOR
    # (normalmente la botella de 330 ml).
    # --------------------------------------------------------
    if sabor_txt in IMAGEN_BOTELLA_POR_SABOR:

        return IMAGEN_BOTELLA_POR_SABOR[sabor_txt]

    # --------------------------------------------------------
    # Sin imagen real disponible: la interfaz usará placeholder.
    # --------------------------------------------------------
    return None
