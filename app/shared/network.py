"""Utilidades para obtener direcciones IP sin leer cabeceras manualmente."""

import ipaddress


def obtener_ip_cliente(solicitud):
    """Devuelve la IP canónica que Flask considera origen de la petición.

    La función no consulta ``X-Forwarded-For``. Solo usa ``remote_addr``, que
    ProxyFix reemplaza cuando el número de proxies fue configurado y validado.
    Una dirección inválida devuelve ``None`` para que el login falle de forma
    segura cuando el sistema de bloqueo está activo.
    """

    valor = str(solicitud.remote_addr or "").strip()
    if not valor:
        return None
    try:
        return ipaddress.ip_address(valor).compressed
    except ValueError:
        return None


def obtener_agente_cliente(solicitud, limite=500):
    """Limita el agente del navegador al tamaño admitido por auditoría."""

    return str(solicitud.user_agent.string or "")[:limite] or None
