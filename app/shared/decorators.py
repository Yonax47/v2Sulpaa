"""Decoradores que comprueban la sesión y los permisos de SULPAA V2.

Los roles guardados en la cookie sirven para mostrar la interfaz, pero no son
la autoridad final. Antes de atender una ruta protegida se consulta Identidad
para comprobar que la cuenta siga activa y para cargar sus roles vigentes.
El resultado se guarda en ``g`` solamente durante la petición actual, así dos
decoradores apilados no repiten la misma consulta.
"""

import logging
from functools import wraps

from flask import abort, current_app, flash, g, redirect, session, url_for

from app.config.testing import seguridad_puede_omitirse


logger = logging.getLogger(__name__)

# Estos son los dos roles existentes con acceso completo al panel. Se conserva
# la misma regla que usaban las rutas antes de unificar los decoradores.
ROLES_ADMINISTRATIVOS = frozenset({"GERENTE", "ADMINISTRADOR"})


def _cerrar_sesion_invalida():
    """Elimina una sesión que ya no corresponde a una cuenta activa."""

    session.clear()
    flash(
        "Tu sesión ya no está disponible. Inicia sesión nuevamente.",
        "danger",
    )


def revalidar_sesion_actual():
    """Comprueba una vez por petición el usuario y sus roles actuales.

    Devuelve ``True`` cuando la sesión pertenece a un usuario activo. Si la
    cuenta fue desactivada, eliminada o no puede comprobarse de forma segura,
    se cierra la sesión. Ante una falla de base de datos se niega el acceso en
    lugar de conservar permisos antiguos; esta decisión evita que un problema
    técnico se convierta en una forma de saltar la seguridad.
    """

    if not session.get("autenticado") or not session.get("usuario_id"):
        return False

    # Las pruebas de negocio con sesiones ficticias deben pedir esta excepción
    # expresamente. La política central nunca la permite fuera de TESTING.
    if seguridad_puede_omitirse(current_app):
        roles_prueba = list(session.get("roles") or [])
        g.roles_vigentes = roles_prueba
        g.sesion_revalidada = True
        return True

    # Flask crea un objeto g nuevo para cada petición. Esta marca evita que
    # @login_required y @role_required consulten dos veces al mismo usuario.
    if hasattr(g, "sesion_revalidada"):
        return bool(g.sesion_revalidada)

    try:
        # La importación local evita un ciclo al iniciar Flask: las rutas de
        # Identidad también importan estos decoradores.
        from app.identidad.services import obtener_contexto_sesion

        contexto = obtener_contexto_sesion(session.get("usuario_id"))
    except Exception:
        logger.exception("No se pudo revalidar la sesión del usuario")
        g.sesion_revalidada = False
        _cerrar_sesion_invalida()
        return False

    if not contexto or contexto.get("estado") != "ACTIVO":
        g.sesion_revalidada = False
        _cerrar_sesion_invalida()
        return False

    # Actualizar la sesión hace que la navegación y los servicios reciban los
    # mismos roles que acaba de confirmar la base de datos. Si un rol fue
    # retirado, deja de servir desde esta misma petición.
    roles = list(contexto.get("roles") or [])
    if session.get("roles") != roles:
        session["roles"] = roles
    correo_actual = contexto.get("correo") or session.get("correo", "")
    if session.get("correo") != correo_actual:
        session["correo"] = correo_actual
    g.roles_vigentes = roles
    g.sesion_revalidada = True
    return True


def _redirigir_login():
    """Lleva al login cuando no existe una sesión válida."""

    return redirect(url_for("identidad.login"))


def login_required(funcion):
    """Permite entrar únicamente con una cuenta autenticada y activa."""

    @wraps(funcion)
    def funcion_protegida(*args, **kwargs):
        if not session.get("autenticado"):
            flash(
                "Debes iniciar sesión para acceder a esta sección.",
                "danger",
            )
            return _redirigir_login()
        if not revalidar_sesion_actual():
            return _redirigir_login()
        return funcion(*args, **kwargs)

    return funcion_protegida


def admin_required(funcion):
    """Exige una cuenta activa con rol GERENTE o ADMINISTRADOR."""

    @wraps(funcion)
    def funcion_protegida(*args, **kwargs):
        if not session.get("autenticado") or not revalidar_sesion_actual():
            return _redirigir_login()
        roles = set(g.get("roles_vigentes", session.get("roles") or []))
        if not ROLES_ADMINISTRATIVOS.intersection(roles):
            abort(403)
        return funcion(*args, **kwargs)

    return funcion_protegida


def role_required(*roles_permitidos):
    """Crea un decorador que exige al menos uno de los roles indicados."""

    roles_necesarios = frozenset(roles_permitidos)

    def decorador(funcion):
        @wraps(funcion)
        def funcion_protegida(*args, **kwargs):
            if not session.get("autenticado") or not revalidar_sesion_actual():
                return _redirigir_login()
            roles = set(g.get("roles_vigentes", session.get("roles") or []))
            if not roles_necesarios.intersection(roles):
                abort(403)
            return funcion(*args, **kwargs)

        return funcion_protegida

    return decorador
