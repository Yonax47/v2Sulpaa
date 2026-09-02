"""
Fábrica principal de la aplicación Flask SULPAA V2.

Este archivo se encarga de:

- Crear la aplicación Flask.
- Cargar la configuración general.
- Configurar la seguridad de sesión.
- Registrar los Blueprints del sistema.
- Definir temporalmente la ruta principal.

IMPORTANTE:
Aquí no debe existir lógica específica de negocio.
Cada módulo debe mantener sus propias rutas, servicios
y repositorios.
"""

import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, render_template


# ============================================================
# CARGA DE VARIABLES DE ENTORNO
# ============================================================
#
# IMPORTANTE:
# El archivo .env debe cargarse ANTES de importar módulos
# que puedan necesitar variables de entorno.
#
# Esto permite que servicios como APIsPERU puedan acceder
# correctamente a:
#
# APISPERU_TOKEN
# SECRET_KEY
# DB_HOST
# DB_USER
# etc.
# ============================================================

load_dotenv()


# ============================================================
# BLUEPRINTS DEL SISTEMA
# ============================================================

from app.identidad.routes import identidad_bp
from app.comercio.routes import comercio_bp


# ============================================================
# ELEMENTOS COMPARTIDOS
# ============================================================

from app.shared.decorators import login_required


# ============================================================
# FÁBRICA DE LA APLICACIÓN
# ============================================================

def create_app():
    """
    Crea y configura la aplicación Flask de SULPAA V2.

    Returns:
        Flask:
            Instancia de la aplicación completamente configurada.
    """

    # ========================================================
    # CREACIÓN DE LA APLICACIÓN
    # ========================================================

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )


    # ========================================================
    # CONFIGURACIÓN GENERAL
    # ========================================================

    app.config["SECRET_KEY"] = os.getenv(
        "SECRET_KEY",
        "clave-desarrollo-no-segura",
    )


    # ========================================================
    # CONFIGURACIÓN DE SEGURIDAD DE SESIÓN
    # ========================================================

    # Impide que JavaScript pueda acceder directamente
    # a la cookie de sesión.
    app.config["SESSION_COOKIE_HTTPONLY"] = True


    # En desarrollo usamos:
    #
    # http://127.0.0.1:5000
    #
    # Por eso permanece en False.
    #
    # Cuando el sistema esté en producción con HTTPS,
    # deberá cambiarse a True.
    app.config["SESSION_COOKIE_SECURE"] = False


    # Ayuda a reducir el envío de cookies
    # desde sitios externos.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


    # Duración de una sesión cuando el usuario activa
    # la opción "Recordarme".
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        days=30
    )


    # ========================================================
    # REGISTRO DE BLUEPRINTS
    # ========================================================
    #
    # IDENTIDAD:
    #
    # /identidad/registro
    # /identidad/login
    # /identidad/logout
    #
    # También contiene servicios relacionados con:
    #
    # - Perfil
    # - Direcciones
    # - Ubicación geográfica
    # - Datos de facturación
    # - Verificación DNI/RUC
    #
    #
    # COMERCIO:
    #
    # /tienda
    # /checkout
    #
    # Comercio también administra:
    #
    # - Productos
    # - Packs
    # - Carrito
    # - Suscripciones
    # - Pedidos comerciales
    #
    # ========================================================

    app.register_blueprint(
        identidad_bp
    )

    app.register_blueprint(
        comercio_bp
    )


    # ========================================================
    # RUTA PRINCIPAL DEL CLIENTE
    # ========================================================
    #
    # Por ahora Inicio permanece aquí porque ya está
    # funcionando correctamente.
    #
    # Posteriormente podremos mover las páginas generales
    # del cliente a un módulo propio si la arquitectura
    # lo requiere.
    #
    # ========================================================

    @app.route("/")
    @login_required
    def inicio():
        """
        Página principal del cliente autenticado.

        login_required impide que usuarios sin sesión
        accedan directamente a esta pantalla.
        """

        return render_template(
            "cliente/inicio.html"
        )


    # ========================================================
    # RETORNAR LA APLICACIÓN
    # ========================================================
    #
    # ESTA LÍNEA ES FUNDAMENTAL.
    #
    # run.py ejecuta:
    #
    # app = create_app()
    #
    # Sin este return, Python devolvería None
    # automáticamente.
    # ========================================================

    return app