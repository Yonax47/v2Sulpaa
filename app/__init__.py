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
from flask import Flask, render_template, request


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
from app.comercio.imagenes import resolver_imagen_producto
from app.operaciones.routes import operaciones_bp
from app.admin.routes import admin_bp
from app.admin.pedidos.routes import admin_pedidos_bp
from app.admin.pedidos.commands import registrar_comandos_pedidos
from app.admin.entregas.routes import admin_entregas_bp
from app.admin.inventario.routes import admin_inventario_bp
from app.admin.contenido.routes import admin_contenido_bp
from app.admin.caja.commands import registrar_comandos_caja
from app.admin.caja.routes import admin_caja_bp
from app.admin.reportes.routes import admin_reportes_bp
from app.admin.encuestas.routes import admin_encuestas_bp
from app.admin.usuarios.routes import admin_usuarios_bp
from app.admin.auditoria.routes import admin_auditoria_bp
from app.admin.delivery.routes import admin_delivery_bp
from app.aprende.routes import aprende_bp
from app.repartidor.routes import repartidor_bp
from app.encuestas.routes import encuesta_bp


# ============================================================
# ELEMENTOS COMPARTIDOS
# ============================================================

from app.shared.decorators import login_required

from app.config.database import cerrar_conexiones_solicitud


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

    # El entorno se resuelve UNA sola vez aquí y se guarda en
    # la app para no repetir getenv() por todo el sistema.
    entorno = os.getenv(
        "FLASK_ENV", ""
    ).strip().lower()

    app.config["ENTORNO"] = entorno

    es_produccion = entorno == "production"

    app.config["ES_PRODUCCION"] = es_produccion


    # ========================================================
    # CONEXIONES REUTILIZADAS POR SOLICITUD
    # ========================================================
    #
    # Al terminar cada solicitud se cierran de verdad las conexiones
    # que se reutilizaron mientras se atendía al usuario. Se registra
    # en el teardown de la solicitud (antes de liberar el contexto de
    # aplicación) y también en el del contexto, como respaldo: así
    # ninguna conexión sobrevive a su solicitud, ni siquiera cuando
    # varias solicitudes comparten un mismo contexto (pruebas o
    # scripts). La función es idempotente.
    app.teardown_request(cerrar_conexiones_solicitud)
    app.teardown_appcontext(cerrar_conexiones_solicitud)


    # ========================================================
    # CACHÉ DE ARCHIVOS ESTÁTICOS
    # ========================================================
    #
    # Flask responde "no-cache" por defecto, así que el navegador
    # vuelve a preguntar por cada CSS, JS e imagen en cada página.
    #
    # Se permite reutilizarlos un tiempo prudente:
    #
    # - Imágenes: 7 días (cambian poco).
    # - CSS y JS: 1 día (un ajuste llega rápido al usuario).
    #
    # No se usa "immutable" porque las rutas no llevan versión.

    @app.after_request
    def cache_archivos_estaticos(respuesta):

        if not request.path.startswith("/static/"):
            return respuesta

        if respuesta.status_code != 200:
            return respuesta

        extension = os.path.splitext(
            request.path
        )[1].lower()

        if extension in (".css", ".js"):
            segundos = 60 * 60 * 24
        else:
            segundos = 60 * 60 * 24 * 7

        respuesta.headers["Cache-Control"] = (
            "public, max-age=%s" % segundos
        )

        return respuesta


    # ========================================================
    # DETRÁS DE UN PROXY INVERSO (RAILWAY)
    # ========================================================
    #
    # Railway (u otro PaaS) termina el TLS y llega al
    # contenedor por HTTP. Sin este middleware Flask creería
    # que la petición NO es segura y no distinguiría el
    # esquema real usado por el navegador.
    #
    # Se confía UN solo salto (el propio PaaS); los valores
    # reales de estas cabeceras los fija el proxy y no el
    # cliente.
    #
    # IMPORTANTE: el contenedor NUNCA se expone directamente
    # a Internet; sólo el proxy lo hace.
    # ========================================================

    if es_produccion:

        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
        )


    # ========================================================
    # CLAVE SECRETA DE LA APLICACIÓN
    # ========================================================
    #
    # Flask la usa para firmar las cookies de sesión; sin una
    # clave propia, cualquier usuario podría forjar una sesión.
    #
    # Regla de seguridad:
    # - En PRODUCCIÓN es OBLIGATORIO definirla en el entorno.
    #   Si falta, la aplicación NO arranca (mejor un fallo
    #   claro en el despliegue que una clave por defecto).
    # - En desarrollo se usa un respaldo local para no
    #   complicar el arranque del equipo.
    # ========================================================

    clave_secreta = os.getenv("SECRET_KEY", "").strip()

    if not clave_secreta:

        if es_produccion:

            raise RuntimeError(
                "Falta la variable de entorno SECRET_KEY. "
                "En producción es obligatoria; define una clave "
                "aleatoria larga en la configuración de Railway."
            )

        clave_secreta = "clave-desarrollo-no-segura"

    app.config["SECRET_KEY"] = clave_secreta


    # ========================================================
    # FUNCIONES DISPONIBLES EN LAS PLANTILLAS
    # ========================================================
    #
    # imagen_producto(sabor, presentacion, tipo, nombre)
    #
    # Devuelve la ruta de la imagen real de un producto o None.
    # Se usa igual en Tienda, Ficha, Favoritos y carrito para
    # que todos elijan la imagen con las mismas reglas.

    app.jinja_env.globals["imagen_producto"] = (
        resolver_imagen_producto
    )


    # ========================================================
    # CONFIGURACIÓN DE SEGURIDAD DE SESIÓN
    # ========================================================

    # Impide que JavaScript pueda acceder directamente
    # a la cookie de sesión.
    app.config["SESSION_COOKIE_HTTPONLY"] = True


    # La cookie de sesión sólo viaja por HTTPS.
    #
    # En producción (Railway termina TLS) es True.
    #
    # En desarrollo local con http://127.0.0.1:5000 debe ser
    # False, o el navegador descartaría la cookie y el login
    # no funcionaría.
    #
    # Se puede forzar con SESSION_COOKIE_SECURE=0/1 en el
    # entorno sin tocar código.
    valor_secure = os.getenv("SESSION_COOKIE_SECURE")

    if valor_secure is None:
        app.config["SESSION_COOKIE_SECURE"] = es_produccion
    else:
        app.config["SESSION_COOKIE_SECURE"] = (
            valor_secure.strip().lower()
            in ("1", "true", "yes", "on")
        )


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
        admin_caja_bp
    )

    app.register_blueprint(
        admin_reportes_bp
    )

    app.register_blueprint(
        admin_encuestas_bp
    )

    app.register_blueprint(
        admin_usuarios_bp
    )

    app.register_blueprint(
        admin_auditoria_bp
    )

    app.register_blueprint(
        admin_delivery_bp
    )

    app.register_blueprint(
        encuesta_bp
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
    registrar_comandos_caja(app)


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
