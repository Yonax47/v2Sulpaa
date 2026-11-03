"""Validaciones puras del catálogo comercial de SULPAA V2.

Aquí viven las reglas que no necesitan base de datos: textos, slugs,
números, fechas, montos, rangos de precio y composición de packs.

Se separaron del Service para poder probarlas con dobles seguros y para
que las mismas reglas se usen al crear y al editar. Todas lanzan
``ErrorCatalogo`` con un mensaje entendible para la persona que administra.
"""

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation


# ============================================================
# CONSTANTES DEL CATÁLOGO REAL
# ============================================================

# Solo estos roles pueden administrar el catálogo comercial.
ROLES_CATALOGO = ("GERENTE", "ADMINISTRADOR")

# Estados permitidos por los CHECK de la base de datos.
ESTADOS = ("ACTIVO", "INACTIVO")

# Tipos de unidad aceptados por ``presentaciones.tipo_unidad``.
TIPOS_UNIDAD = ("ML", "L", "G", "KG", "UNIDAD")

# Tipos de pack aceptados por ``packs.tipo``.
TIPOS_PACK = ("FIJO", "PERSONALIZABLE")

# Moneda por defecto del catálogo actual.
MONEDA_POR_DEFECTO = "PEN"


class ErrorCatalogo(Exception):
    """Error de negocio seguro para mostrar en la interfaz administrativa."""


# ============================================================
# TEXTOS Y SLUGS
# ============================================================

def normalizar_texto(valor, campo, obligatorio=True, maximo=150):
    """Limpia un texto, comprueba su tamaño y lo devuelve sin extremos.

    ``campo`` se usa solo para construir un mensaje claro. Nunca se
    interpola ningún valor recibido directamente en una consulta SQL.
    """

    texto = str(valor or "").strip()

    if not texto:
        if obligatorio:
            raise ErrorCatalogo(f"{campo} es obligatorio.")
        return None

    if len(texto) > maximo:
        raise ErrorCatalogo(
            f"{campo} no puede superar los {maximo} caracteres."
        )

    return texto


def generar_slug(texto, maximo=170):
    """Convierte un texto legible en un identificador seguro para URL.

    - Quita tildes y signos.
    - Une palabras con guiones.
    - Nunca deja barras, puntos ni caracteres de control.

    El resultado se usa como valor parametrizado; no se concatena en SQL.
    """

    limpio = unicodedata.normalize("NFKD", str(texto or ""))
    limpio = "".join(
        caracter
        for caracter in limpio
        if not unicodedata.combining(caracter)
    )
    limpio = limpio.lower()
    limpio = re.sub(r"[^a-z0-9]+", "-", limpio)
    limpio = re.sub(r"-{2,}", "-", limpio).strip("-")

    if not limpio:
        raise ErrorCatalogo(
            "No fue posible generar un identificador (slug) con ese nombre."
        )

    return limpio[:maximo].strip("-")


def normalizar_busqueda(valor):
    """Recorta el texto de búsqueda para no enviar espacios innecesarios."""

    return str(valor or "").strip()[:120]


# ============================================================
# NÚMEROS Y MONTOS
# ============================================================

def normalizar_entero(valor, campo, minimo=0, maximo=None):
    """Convierte un valor de formulario en entero dentro de un rango."""

    if valor is None or str(valor).strip() == "":
        raise ErrorCatalogo(f"{campo} es obligatorio.")

    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ErrorCatalogo(f"{campo} debe ser un número entero.") from None

    if numero < minimo:
        raise ErrorCatalogo(
            f"{campo} debe ser mayor o igual a {minimo}."
        )
    if maximo is not None and numero > maximo:
        raise ErrorCatalogo(
            f"{campo} no puede ser mayor que {maximo}."
        )
    return numero


def normalizar_decimal(
    valor,
    campo,
    obligatorio=True,
    mayor_que_cero=False,
    maximo=None,
):
    """Convierte un valor en ``Decimal`` sin aceptar texto ambiguo."""

    texto = str(valor or "").strip().replace(",", ".")

    if not texto:
        if obligatorio:
            raise ErrorCatalogo(f"{campo} es obligatorio.")
        return None

    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        raise ErrorCatalogo(f"{campo} debe ser un número válido.") from None

    if not numero.is_finite():
        raise ErrorCatalogo(f"{campo} debe ser un número válido.")

    if mayor_que_cero and numero <= 0:
        raise ErrorCatalogo(f"{campo} debe ser mayor que cero.")

    if numero < 0:
        raise ErrorCatalogo(f"{campo} no puede ser negativo.")

    if maximo is not None and numero > maximo:
        raise ErrorCatalogo(f"{campo} no puede ser mayor que {maximo}.")

    return numero


def validar_monto(monto):
    """Regla de negocio de precios: mayor que cero y con dos decimales.

    La base de datos solo exige ``monto >= 0``. La tienda no debe mostrar
    productos gratuitos por error, así que aquí se exige un monto positivo.
    """

    numero = normalizar_decimal(
        monto,
        "El monto",
        obligatorio=True,
        mayor_que_cero=True,
        maximo=Decimal("99999999.99"),
    )

    return numero.quantize(Decimal("0.01"))


def normalizar_estado(valor, por_defecto="ACTIVO"):
    """Devuelve únicamente ACTIVO o INACTIVO, en mayúsculas."""

    estado = str(valor or por_defecto).strip().upper()

    if estado not in ESTADOS:
        raise ErrorCatalogo("El estado indicado no es válido.")

    return estado


def normalizar_booleano(valor):
    """Interpreta los valores habituales de un checkbox como verdadero."""

    return str(valor or "").strip().lower() in (
        "1", "true", "on", "si", "sí", "yes",
    )


# ============================================================
# FECHAS Y VIGENCIAS DE PRECIO
# ============================================================

def normalizar_fecha(valor, campo, obligatorio=True):
    """Convierte ``datetime-local`` o una fecha ISO en ``datetime``.

    La base de datos guarda fechas sin zona horaria. Si el navegador
    envía una zona, se convierte a la hora local del servidor y se quita
    la zona para evitar comparaciones confusas.
    """

    texto = str(valor or "").strip()

    if not texto:
        if obligatorio:
            raise ErrorCatalogo(f"{campo} es obligatorio.")
        return None

    try:
        fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        raise ErrorCatalogo(
            f"{campo} debe tener una fecha y hora válidas."
        ) from None

    if fecha.tzinfo is not None:
        fecha = fecha.astimezone().replace(tzinfo=None)

    return fecha


def rangos_se_superponen(desde_a, hasta_a, desde_b, hasta_b):
    """Indica si dos vigencias se cruzan.

    Se usan intervalos semiabiertos: ``[desde, hasta)``. Así un precio que
    termina exactamente cuando empieza otro no se considera superpuesto.
    ``None`` en ``hasta`` significa "sin fecha de fin".
    """

    fin_a = hasta_a or datetime.max
    fin_b = hasta_b or datetime.max

    return desde_a < fin_b and desde_b < fin_a


def validar_rango_precio(desde, hasta):
    """Comprueba que la vigencia tenga sentido antes de guardarla."""

    if hasta is not None and hasta <= desde:
        raise ErrorCatalogo(
            "La fecha de fin debe ser posterior a la fecha de inicio."
        )


# ============================================================
# COMPOSICIÓN DE PACKS
# ============================================================

def validar_componentes_pack(cantidad_unidades, componentes):
    """Valida los componentes de un pack FIJO.

    ``componentes`` es una lista de diccionarios con ``variante_id`` y
    ``cantidad``. No se permiten repetidos porque la base de datos tiene
    una clave única por ``(pack_id, variante_id)``.
    """

    cantidad = normalizar_entero(
        cantidad_unidades,
        "La cantidad de unidades",
        minimo=1,
        maximo=60000,
    )

    if not componentes:
        raise ErrorCatalogo(
            "Un pack fijo necesita al menos una variante componente."
        )

    vistos = set()
    total = 0

    for componente in componentes:
        variante_id = str(componente.get("variante_id") or "").strip()
        if not variante_id:
            raise ErrorCatalogo("Cada componente necesita una variante válida.")
        if variante_id in vistos:
            raise ErrorCatalogo(
                "No se puede repetir la misma variante en un pack."
            )
        vistos.add(variante_id)

        total += normalizar_entero(
            componente.get("cantidad"),
            "La cantidad de cada componente",
            minimo=1,
            maximo=60000,
        )

    if total != cantidad:
        raise ErrorCatalogo(
            "La suma de los componentes debe coincidir con la cantidad "
            f"total del pack ({cantidad})."
        )

    return cantidad


def validar_reglas_pack(cantidad_unidades, reglas):
    """Valida las reglas de un pack PERSONALIZABLE.

    Cada regla indica cuántos sabores distintos se eligen y cuántas
    unidades se llevan de cada sabor. El producto debe coincidir con la
    cantidad total del pack.
    """

    cantidad = normalizar_entero(
        cantidad_unidades,
        "La cantidad de unidades",
        minimo=1,
        maximo=60000,
    )

    if not reglas:
        raise ErrorCatalogo(
            "Un pack personalizable necesita al menos una regla."
        )

    vistos = set()

    for regla in reglas:
        numero_sabores = normalizar_entero(
            regla.get("numero_sabores"),
            "El número de sabores",
            minimo=1,
            maximo=60000,
        )
        unidades_por_sabor = normalizar_entero(
            regla.get("unidades_por_sabor"),
            "Las unidades por sabor",
            minimo=1,
            maximo=60000,
        )

        clave = (numero_sabores, unidades_por_sabor)
        if clave in vistos:
            raise ErrorCatalogo(
                "No se puede repetir la misma regla en un pack."
            )
        vistos.add(clave)

        if numero_sabores * unidades_por_sabor != cantidad:
            raise ErrorCatalogo(
                "Cada regla debe sumar la cantidad total del pack "
                f"({cantidad} unidades)."
            )

    return cantidad


def calcular_stock_pack_fijo(componentes, disponibilidad):
    """Calcula cuántos packs completos se pueden armar con el stock real.

    Se usa el mínimo de ``stock_disponible // cantidad_requerida``. Es la
    misma regla que ya utiliza la tienda, reutilizada para no inventar
    stock propio de los packs.
    """

    limites = []

    for componente in componentes:
        disponible = int(
            (disponibilidad.get(componente["variante_id"]) or {}).get(
                "stock_disponible", 0
            )
            or 0
        )
        requerida = int(componente.get("cantidad") or 0)

        limites.append(disponible // requerida if requerida > 0 else 0)

    return min(limites) if limites else 0
