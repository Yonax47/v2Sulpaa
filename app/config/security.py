"""Configuración del bloqueo de accesos y de los proxies confiables."""

import os


def _booleano(nombre, predeterminado=False):
    """Lee una variable booleana sin aceptar valores ambiguos."""

    valor = os.getenv(nombre)
    if valor is None:
        return predeterminado
    return valor.strip().lower() in ("1", "true", "yes", "on")


def _entero_positivo(nombre, predeterminado, minimo=1, maximo=10080):
    """Lee un límite entero y detiene el arranque si es inseguro."""

    texto = str(os.getenv(nombre, predeterminado)).strip()
    try:
        valor = int(texto)
    except ValueError:
        raise RuntimeError(f"{nombre} debe ser un número entero.") from None
    if not minimo <= valor <= maximo:
        raise RuntimeError(
            f"{nombre} debe estar entre {minimo} y {maximo}."
        )
    return valor


def configurar_seguridad_accesos(app):
    """Carga límites y mantiene desactivada producción hasta validar Railway.

    El código puede desplegarse antes que la activación sin confiar en una
    cabecera de IP no verificada. En pruebas y desarrollo se usa directamente
    ``REMOTE_ADDR``; producción exige además la aprobación explícita del proxy.
    """

    app.config.update({
        "LOGIN_MAX_FALLOS_CUENTA_IP": _entero_positivo(
            "LOGIN_MAX_FALLOS_CUENTA_IP", 3, maximo=100
        ),
        "LOGIN_MAX_FALLOS_IP": _entero_positivo(
            "LOGIN_MAX_FALLOS_IP", 20, maximo=10000
        ),
        "LOGIN_VENTANA_MINUTOS": _entero_positivo(
            "LOGIN_VENTANA_MINUTOS", 15
        ),
        "LOGIN_BLOQUEO_MINUTOS": _entero_positivo(
            "LOGIN_BLOQUEO_MINUTOS", 15
        ),
        "LOGIN_BLOQUEO_SOLICITADO": _booleano(
            "LOGIN_BLOQUEO_HABILITADO", False
        ),
        "RAILWAY_PROXY_VALIDADO": _booleano(
            "RAILWAY_PROXY_VALIDADO", False
        ),
        "LOGIN_MIGRACION_APROBADA": _booleano(
            "LOGIN_MIGRACION_APROBADA", False
        ),
        "TRUSTED_PROXY_HOPS": _entero_positivo(
            "TRUSTED_PROXY_HOPS", 0, minimo=0, maximo=5
        ),
    })

    entorno_con_proxy = str(app.config.get("ENTORNO") or "").lower() in {
        "production",
        "staging",
    }
    proxy_validado = bool(app.config["RAILWAY_PROXY_VALIDADO"])
    migracion_aprobada = bool(app.config["LOGIN_MIGRACION_APROBADA"])
    # El centro administrativo consulta las tablas de la migración 002. Esta
    # bandera lo mantiene completamente inaccesible hasta que la aprobación
    # confirme que las tres tablas ya existen en el esquema de Identidad.
    app.config["CENTRO_SEGURIDAD_HABILITADO"] = migracion_aprobada
    app.config["LOGIN_BLOQUEO_HABILITADO"] = bool(
        app.config["LOGIN_BLOQUEO_SOLICITADO"]
        and migracion_aprobada
        and (not entorno_con_proxy or proxy_validado)
    )


def politica_bloqueos(app):
    """Devuelve únicamente los valores necesarios para evaluar un acceso."""

    return {
        "habilitado": bool(app.config.get("LOGIN_BLOQUEO_HABILITADO")),
        "max_cuenta_ip": int(app.config["LOGIN_MAX_FALLOS_CUENTA_IP"]),
        "max_ip": int(app.config["LOGIN_MAX_FALLOS_IP"]),
        "ventana_minutos": int(app.config["LOGIN_VENTANA_MINUTOS"]),
        "bloqueo_minutos": int(app.config["LOGIN_BLOQUEO_MINUTOS"]),
    }
