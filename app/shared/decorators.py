"""
Decoradores reutilizables de SULPAA V2.

Este archivo contiene decoradores que pueden proteger
rutas del sistema sin repetir lógica.

Ejemplos de uso futuro:

@login_required
@admin_required
@gerente_required

IMPORTANTE:
Los decoradores deben ser reutilizables y no contener
consultas SQL directas.
"""

from functools import wraps

from flask import flash, redirect, session, url_for


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