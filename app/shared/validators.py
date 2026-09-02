"""
Validadores reutilizables de SULPAA V2.

Este módulo centraliza las reglas de validación que pueden
utilizarse en diferentes partes del sistema.

IMPORTANTE:
- Aquí no se realizan consultas SQL.
- Aquí no existe lógica específica de Flask.
- Las funciones reciben datos y devuelven resultados.
"""

import re


# ============================================================
# EXPRESIONES REGULARES REUTILIZABLES
# ============================================================

# Permite:
# - letras mayúsculas y minúsculas
# - vocales con tilde
# - ñ
# - espacios
# - guiones
#
# Ejemplos válidos:
# Carlos Alberto
# José Luis
# María-José
PATRON_NOMBRE = re.compile(
    r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s'-]+$"
)


# Formato básico y seguro para correos.
PATRON_CORREO = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)


def validar_nombre(
    valor: str,
    nombre_campo: str = "El nombre",
    obligatorio: bool = True,
):
    """
    Valida nombres y apellidos.

    Returns:
        tuple[bool, str | None]
        - True, None si es válido.
        - False, mensaje si existe un problema.
    """

    valor = (valor or "").strip()

    if not valor:
        if obligatorio:
            return False, f"{nombre_campo} es obligatorio."

        return True, None

    if len(valor) < 2:
        return False, f"{nombre_campo} debe tener al menos 2 caracteres."

    if len(valor) > 80:
        return False, f"{nombre_campo} es demasiado largo."

    if not PATRON_NOMBRE.fullmatch(valor):
        return (
            False,
            f"{nombre_campo} solo puede contener letras, espacios y guiones.",
        )

    return True, None


def validar_dni(
    dni: str | None,
    obligatorio: bool = False,
):
    """
    Valida un DNI peruano.

    Para esta versión comprobamos el formato:
    exactamente 8 dígitos numéricos.

    La validación contra RENIEC podrá incorporarse después
    mediante un servicio externo, sin modificar esta regla base.
    """

    dni = (dni or "").strip()

    if not dni:
        if obligatorio:
            return False, "El DNI es obligatorio."

        return True, None

    if not dni.isdigit():
        return False, "El DNI solo puede contener números."

    if len(dni) != 8:
        return False, "El DNI debe contener exactamente 8 dígitos."

    return True, None


def validar_telefono_peru(
    telefono: str,
    obligatorio: bool = True,
):
    """
    Valida teléfonos móviles peruanos.

    Regla actual:
    - 9 dígitos.
    - Solo números.
    - Debe iniciar con 9.
    """

    telefono = (telefono or "").strip()

    # Eliminamos espacios que el usuario podría escribir
    # visualmente dentro del número.
    telefono = telefono.replace(" ", "")

    if not telefono:
        if obligatorio:
            return False, "El teléfono es obligatorio."

        return True, None

    if not telefono.isdigit():
        return False, "El teléfono solo puede contener números."

    if len(telefono) != 9:
        return False, "El teléfono debe contener exactamente 9 dígitos."

    if not telefono.startswith("9"):
        return False, "El teléfono móvil debe comenzar con 9."

    return True, None


def normalizar_telefono(
    telefono: str,
):
    """
    Elimina espacios antes de guardar el teléfono.

    Ejemplo:
    '999 888 777'
    pasa a:
    '999888777'
    """

    return (telefono or "").replace(" ", "").strip()


def validar_correo(
    correo: str,
):
    """
    Valida el formato general del correo electrónico.
    """

    correo = (correo or "").strip().lower()

    if not correo:
        return False, "El correo electrónico es obligatorio."

    if len(correo) > 150:
        return False, "El correo electrónico es demasiado largo."

    if " " in correo:
        return False, "El correo electrónico no puede contener espacios."

    if not PATRON_CORREO.fullmatch(correo):
        return False, "Ingresa un correo electrónico válido."

    return True, None


def validar_password(
    password: str,
):
    """
    Valida una contraseña para cuentas SULPAA.

    Reglas:
    - mínimo 8 caracteres
    - máximo 72 caracteres
    - al menos una letra
    - al menos un número

    bcrypt utiliza únicamente los primeros 72 bytes,
    por eso definimos también un límite superior.
    """

    password = password or ""

    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."

    if len(password) > 72:
        return False, "La contraseña no puede superar los 72 caracteres."

    if not re.search(r"[A-Za-z]", password):
        return False, "La contraseña debe contener al menos una letra."

    if not re.search(r"\d", password):
        return False, "La contraseña debe contener al menos un número."

    return True, None