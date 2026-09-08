"""
Cliente para consultas DNI/RUC mediante APIsPERU.

La credencial permanece únicamente en el backend.
Nunca debe enviarse al navegador.
"""

import os
import requests

APISPERU_BASE_URL = "https://dniruc.apisperu.com/api/v1"


# ============================================================
# TOKEN
# ============================================================

def _obtener_token():
    """
    Obtiene el token configurado en variables de entorno.
    """

    token = (
        os.getenv("APISPERU_TOKEN") or ""
    ).strip()

    if not token:
        raise RuntimeError(
            "APISPERU_TOKEN no está configurado."
        )

    return token


# ============================================================
# CONSULTA DNI
# ============================================================

def consultar_dni(dni):
    """
    Consulta un DNI en APIsPERU.
    """

    dni = (dni or "").strip()

    if not dni.isdigit() or len(dni) != 8:
        return {
            "ok": False,
            "mensaje": "El DNI debe tener 8 dígitos.",
        }

    try:
        response = requests.get(
            f"{APISPERU_BASE_URL}/dni/{dni}",
            params={"token": _obtener_token()},
            timeout=10,
        )

    except requests.RequestException:
        return {
            "ok": False,
            "mensaje": (
                "No fue posible comunicarse "
                "con el servicio de consulta."
            ),
        }

    if response.status_code != 200:
        return {
            "ok": False,
            "mensaje": (
                "No se pudieron obtener "
                "los datos del DNI."
            ),
        }

    try:
        datos = response.json()

    except ValueError:
        return {
            "ok": False,
            "mensaje": (
                "El servicio devolvió "
                "una respuesta inválida."
            ),
        }

    return {
        "ok": True,
        "dni": str(datos.get("dni") or dni),
        "nombres": (datos.get("nombres") or "").strip(),
        "apellido_paterno": (
            datos.get("apellidoPaterno") or ""
        ).strip(),
        "apellido_materno": (
            datos.get("apellidoMaterno") or ""
        ).strip(),
    }


# ============================================================
# CONSULTA RUC
# ============================================================

def consultar_ruc(ruc):
    """
    Consulta un RUC en APIsPERU.

    Retorna únicamente la información que utilizará
    el módulo de facturación de SULPAA.
    """

    ruc = (ruc or "").strip()

    if not ruc.isdigit() or len(ruc) != 11:
        return {
            "ok": False,
            "mensaje": "El RUC debe tener 11 dígitos.",
        }

    try:
        response = requests.get(
            f"{APISPERU_BASE_URL}/ruc/{ruc}",
            params={"token": _obtener_token()},
            timeout=10,
        )

    except requests.RequestException:
        return {
            "ok": False,
            "mensaje": (
                "No fue posible comunicarse "
                "con el servicio de consulta."
            ),
        }

    if response.status_code != 200:
        return {
            "ok": False,
            "mensaje": (
                "No se pudieron obtener "
                "los datos del RUC."
            ),
        }

    try:
        datos = response.json()

    except ValueError:
        return {
            "ok": False,
            "mensaje": (
                "El servicio devolvió "
                "una respuesta inválida."
            ),
        }

    # APIsPERU responde success=false cuando el RUC no existe.
    if datos.get("success") is False:
        return {
            "ok": False,
            "mensaje": (
                datos.get("message")
                or "No se encontró el RUC."
            ),
        }

    return {
        "ok": True,
        "ruc": str(datos.get("ruc") or ruc),
        "razon_social": (
            datos.get("razonSocial") or ""
        ).strip(),
        "direccion": (
            datos.get("direccion") or ""
        ).strip(),
        "estado": (
            datos.get("estado") or ""
        ).strip(),
        "condicion": (
            datos.get("condicion") or ""
        ).strip(),
        "departamento": (
            datos.get("departamento") or ""
        ).strip(),
        "provincia": (
            datos.get("provincia") or ""
        ).strip(),
        "distrito": (
            datos.get("distrito") or ""
        ).strip(),
    }