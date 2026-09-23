"""
Decoradores reutilizables de SULPAA V2.

Este archivo contiene decoradores que pueden proteger
rutas del sistema sin repetir lógica.

Decoradores disponibles:

- login_required   -> exige sesión iniciada.
- admin_required   -> exige sesión + rol administrativo
                      (GERENTE o ADMINISTRADOR).
- role_required    -> exige sesión + al menos uno de los
                      códigos de rol indicados.

IMPORTANTE:
Los decoradores deben ser reutilizables y no contener
consultas SQL directas. Los roles ya quedaron cargados
en la sesión durante el login (identidad), así que estos
decoradores SÓLO leen session["roles"]; no tocan la BD.

Códigos de rol REALES (dump de identidad):
- GERENTE
- ADMINISTRADOR
- INVENTARIO
- PEDIDOS_LOGISTICA
- REPARTIDOR
"""

from functools import wraps

from flask import (
    abort,
    flash,
    redirect,
    session,
    url_for,
)


# Roles con acceso total al panel administrativo (dump real):
ROLES_ADMINISTRATIVOS = ("GERENTE", "ADMINISTRADOR")


def login_required(funcion):
    """
    Protege una ruta para permitir acceso únicamente
    a usuarios autenticados.

    Si no existe una sesión válida:
    - muestra un mensaje,
    - redirige al login.

    Uso:

    @app.route("/perfil")
    @login_required
    def perfil():
        ...
    """

    @wraps(funcion)
    def funcion_protegida(*args, **kwargs):

        if not session.get("autenticado"):

            flash(
                "Debes iniciar sesión para acceder a esta sección.",
                "danger",
            )

            return redirect(
                url_for("identidad.login")
            )

        return funcion(*args, **kwargs)

    return funcion_protegida


def admin_required(funcion):
    """
    Protege una ruta para permitir acceso únicamente
    a usuarios autenticados CON rol administrativo
    (GERENTE o ADMINISTRADOR, los únicos 2 que el dump
    de identidad define con acceso al panel).

    Orden de fallo:
    - Sin sesión              -> redirige al login.
    - Sesión sin rol admin    -> responde 403 (Forbidden),
      sin intentar renderizar vistas administrativas.

    Uso:

    @app.route("/admin/dashboard")
    @login_required
    @admin_required
    def dashboard():
        ...
    """

    @wraps(funcion)
    def funcion_protegida(*args, **kwargs):

        if not session.get("autenticado"):

            return redirect(
                url_for("identidad.login")
            )

        roles = session.get("roles", []) or []

        if not (set(ROLES_ADMINISTRATIVOS) & set(roles)):

            abort(403)

        return funcion(*args, **kwargs)

    return funcion_protegida


def role_required(*roles_permitidos):
    """
    Protege una ruta para permitir acceso únicamente
    a usuarios que posean al menos uno de los roles
    indicados.

    Orden de fallo:
    - Sin sesión              -> redirige al login.
    - Sesión sin rol           -> responde 403 (Forbidden).

    Uso:

    @app.route("/panel-logistica")
    @login_required
    @role_required("PEDIDOS_LOGISTICA", "GERENTE")
    def panel():
        ...
    """

    def decorador(funcion):

        @wraps(funcion)
        def funcion_protegida(*args, **kwargs):

            if not session.get("autenticado"):

                return redirect(
                    url_for("identidad.login")
                )

            roles = session.get("roles", []) or []

            if not (set(roles_permitidos) & set(roles)):

                abort(403)

        return funcion(*args, **kwargs)

    return funcion_protegida


# ============================================================
# CODIGOS DE ROL REALES (dump identidad)
# ============================================================
#
# C\u00f3digos EXACTOS que el dump de identidad define.
# NO se inventan c\u00f3digos.
# ============================================================

ROLES_ADMINISTRATIVOS = (
    "GERENTE",
    "ADMINISTRADOR",
)


def admin_required(funcion):
    """
    Protege una ruta para permitir acceso \u00fanicamente
    a usuarios autenticados CON rol administrativo
    (GERENTE o ADMINISTRADOR).

    Order de fallo:
    - Sin sesi\u00f3n              -> redirige al login.
    - Sesi\u00f3n sin rol admin    -> responde 403 (Forbidden).

    Uso:

    @app.route("/admin/dashboard")
    @login_required
    @admin_required
    def dashboard():
        ...
    """

    @wraps(funcion)
    def funcion_protegida(*args, **kwargs):

        if not session.get("autenticado"):

            return redirect(
                url_for("identidad.login")
            )

        roles = session.get("roles", []) or []

        if not (set(ROLES_ADMINISTRATIVOS) & set(roles)):

            abort(403)

        return funcion(*args, **kwargs)

    return funcion_protegida


def role_required(*roles_permitidos):
    """
    Protege una ruta para permitir acceso \u00fanicamente
    a usuarios autenticados que posean al menos UNO de
    los roles permitidos indicados.

    Order de fallo:
    - Sin sesi\u00f3n              -> redirige al login.
    - Sesi\u00f3n sin rol           -> responde 403 (Forbidden).

    Uso:

    @app.route("/panel-logistica")
    @login_required
    @role_required("PEDIDOS_LOGISTICA", "GERENTE")
    def panel():
        ...
    """

    def decorador(funcion):

        @wraps(funcion)
        def funcion_protegida(*args, **kwargs):

            if not session.get("autenticado"):

                return redirect(
                    url_for("identidad.login")
                )

            roles = session.get("roles", []) or []

            if not (set(roles_permitidos) & set(roles)):

                abort(403)

            return funcion(*args, **kwargs)

        return funcion_protegida

    return decorador

    return decorador
