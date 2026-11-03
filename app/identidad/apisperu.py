"""
Cliente para consultas DNI/RUC mediante APIsPERU.

La credencial permanece únicamente en el backend.
Nunca debe enviarse al navegador.
"""

import os
import requests

APISPERU_BASE_URL = "https://dniruc.apisperu.com/api/v1"
APISPERU_TIMEOUT = (3.05, 10)


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
            "tipo_error": "INVALIDO",
        }

    try:
        response = requests.get(
            f"{APISPERU_BASE_URL}/dni/{dni}",
            params={"token": _obtener_token()},
            timeout=APISPERU_TIMEOUT,
            # La credencial viaja en la URL. Una redirección inesperada
            # podría enviarla a otro host; el proveedor no necesita redirigir.
            allow_redirects=False,
        )

    except (requests.RequestException, RuntimeError):
        return {
            "ok": False,
            "mensaje": (
                "No fue posible comunicarse "
                "con el servicio de consulta."
            ),
            "tipo_error": "NO_DISPONIBLE",
        }

    if response.status_code != 200:
        # 401/403/429 indican un problema del servicio o de la credencial,
        # no un DNI inexistente. Solo 404/400 se tratan como documento no
        # encontrado para no culpar al usuario de una caída del proveedor.
        no_disponible = (
            response.status_code >= 500
            or response.status_code in (401, 403, 429)
        )
        return {
            "ok": False,
            "mensaje": (
                "No se pudieron obtener "
                "los datos del DNI."
            ),
            "tipo_error": (
                "NO_DISPONIBLE" if no_disponible else "INVALIDO"
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
            "tipo_error": "NO_DISPONIBLE",
        }

    if not isinstance(datos, dict):
        return {
            "ok": False,
            "mensaje": (
                "El servicio devolvió "
                "una respuesta inválida."
            ),
            "tipo_error": "NO_DISPONIBLE",
        }

    if datos.get("success") is False:
        return {
            "ok": False,
            "mensaje": "No se encontró un DNI válido.",
            "tipo_error": "INVALIDO",
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
            timeout=APISPERU_TIMEOUT,
            allow_redirects=False,
        )

    except (requests.RequestException, RuntimeError):
        return {
            "ok": False,
            "mensaje": (
                "No fue posible comunicarse "
                "con el servicio de consulta."
            ),
            "tipo_error": "NO_DISPONIBLE",
        }

    if response.status_code != 200:
        return {
            "ok": False,
            "mensaje": (
                "No se pudieron obtener "
                "los datos del RUC."
            ),
            "tipo_error": (
                "NO_DISPONIBLE"
                if response.status_code >= 500
                or response.status_code in (401, 403, 429)
                else "INVALIDO"
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
            "tipo_error": "NO_DISPONIBLE",
        }

    if not isinstance(datos, dict):
        return {
            "ok": False,
            "mensaje": (
                "El servicio devolvió "
                "una respuesta inválida."
            ),
            "tipo_error": "NO_DISPONIBLE",
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
