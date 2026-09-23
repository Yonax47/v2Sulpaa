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
from app.operaciones.routes import operaciones_bp
from app.admin.routes import admin_bp
from app.admin.pedidos.routes import admin_pedidos_bp
from app.admin.pedidos.commands import registrar_comandos_pedidos
from app.admin.entregas.routes import admin_entregas_bp
from app.admin.inventario.routes import admin_inventario_bp
from app.admin.contenido.routes import admin_contenido_bp
from app.aprende.routes import aprende_bp
from app.repartidor.routes import repartidor_bp


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
    #
    # OPERACIONES:
    #
    # /operaciones/api/entregas/opciones
    # /operaciones/api/entregas/delivery/cotizar
    # /operaciones/api/transportistas
    #
    # Operaciones administra:
    #
    # - Modalidades de entrega
    # - Delivery local
    # - Puntos de recojo
    # - Transportistas
    # - Servicios de transporte
    # - Agencias
    # - Tarifas de envío
    # - Cotizaciones interprovinciales
    #
    # ========================================================

    app.register_blueprint(
        identidad_bp
    )

    app.register_blueprint(
        comercio_bp
    )

    app.register_blueprint(
        operaciones_bp
    )


    # ========================================================
    # ADMINISTRACIÓN (Etapa 1)
    # ========================================================
    #
    # /admin          -> redirige a /admin/dashboard.
    # /admin/dashboard -> panel con los KPI instrumentados.
    #
    # NOTA: se registra SIN url_prefix porque las rutas del
    # blueprint ya traen "/admin" en su propio path (patrón
    # real del resto de dominios: comercio usa /tienda en su
    # route, no en register_blueprint).
    # ========================================================

    app.register_blueprint(
        admin_bp
    )

    app.register_blueprint(
        admin_pedidos_bp
    )

    app.register_blueprint(
        admin_entregas_bp
    )

    app.register_blueprint(
        admin_inventario_bp
    )

    app.register_blueprint(
        admin_contenido_bp
    )

    app.register_blueprint(
        aprende_bp
    )

    app.register_blueprint(
        repartidor_bp
    )

    # El backfill queda disponible como comando Flask repetible y verificable;
    # no se deja SQL manual aislado que pueda ejecutarse sin sus controles.
    registrar_comandos_pedidos(app)


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
