"""
Rutas HTTP del módulo Identidad de SULPAA V2.

Este módulo se encarga de:

- Registro de clientes.
- Inicio de sesión.
- Cierre de sesión.
- Gestión de la sesión del usuario.

IMPORTANTE:
Las rutas solamente coordinan solicitudes y respuestas.

No deben contener:
- SQL directo.
- Hash de contraseñas.
- Reglas complejas de negocio.

Esas responsabilidades pertenecen a services.py
y repositories.py.
"""

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    jsonify,
    make_response,
    current_app,
    abort,
)

from app.shared.decorators import (
    login_required,
    revalidar_sesion_actual,
)
from app.shared.network import obtener_agente_cliente, obtener_ip_cliente

from app.identidad.services import (
    autenticar_usuario,
    registrar_usuario,
    listar_departamentos,
    listar_provincias,
    listar_distritos,
    registrar_direccion_usuario,
    validar_dni_con_perfil,
    validar_ruc_facturacion,
    registrar_facturacion_checkout,
    obtener_roles_usuario,
    verificar_dni_registro,
)
from app.shared.rate_limit import consumir_limite
from app.identidad.email_verification import (
    confirmar as confirmar_correo,
    estado_cuenta,
    solicitar_reenvio,
)


# ============================================================
# BLUEPRINT DEL MÓDULO IDENTIDAD
# ============================================================

identidad_bp = Blueprint(
    "identidad",
    __name__,
    url_prefix="/identidad",
)


def _estado_http_consulta_externa(resultado, predeterminado=400):
    """Proyecta límites/indisponibilidad sin revelar detalles internos."""

    if resultado.get("tipo_error") == "LIMITE" \
            or resultado.get("estado") == "LIMITE":
        return 429
    if resultado.get("tipo_error") == "CONTADOR_NO_DISPONIBLE":
        return 503
    return predeterminado


# ============================================================
# REGISTRO
# ============================================================

@identidad_bp.route(
    "/registro",
    methods=["GET", "POST"],
)
def registro():
    """
    Muestra y procesa el registro de clientes.

    GET:
        Muestra el formulario.

    POST:
        Envía los datos a la capa de servicios.

    Si ocurre un error, conservamos los datos no sensibles
    para evitar que el usuario tenga que escribirlos nuevamente.

    La contraseña nunca se conserva.
    """

    datos_formulario = {}

    if request.method == "POST":

        permitido, _ = consumir_limite(
            f"registro:{obtener_ip_cliente(request)}",
            maximo=5,
            ventana_segundos=600,
        )
        if not permitido:
            flash(
                "Se realizaron demasiados intentos. "
                "Espera unos minutos antes de volver a intentarlo.",
                "danger",
            )
            return render_template(
                "auth/registro.html", datos_formulario={}
            ), 429

        # ----------------------------------------------------
        # Datos no sensibles que podemos volver a mostrar
        # si ocurre un error.
        # ----------------------------------------------------

        # Los nombres y apellidos NO se conservan desde el navegador: solo
        # pueden provenir de la consulta backend al reenviar el formulario.
        # Así un intento manipulado no reaparece como si fuera válido.
        datos_formulario = {
            "dni": request.form.get(
                "dni",
                "",
            ),
            "telefono": request.form.get(
                "telefono",
                "",
            ),
            "correo": request.form.get(
                "correo",
                "",
            ),
        }

        # ----------------------------------------------------
        # Capa de servicio
        # ----------------------------------------------------

        resultado = registrar_usuario(
            correo=datos_formulario["correo"],
            password=request.form.get(
                "password",
                "",
            ),
            # Se envían por compatibilidad de firma, pero el servicio los
            # ignora y vuelve a obtener la identidad desde APIsPERU.
            nombres=request.form.get("nombres", ""),
            apellido_paterno=request.form.get(
                "apellido_paterno",
                "",
            ),
            apellido_materno=request.form.get(
                "apellido_materno",
                "",
            ),
            dni=datos_formulario["dni"],
            telefono=datos_formulario["telefono"],
        )

        # ----------------------------------------------------
        # Registro correcto
        # ----------------------------------------------------

        if resultado["ok"]:
            if not current_app.config.get("EMAIL_VERIFICATION_REQUIRED", True):
                flash("Cuenta creada correctamente. Ahora puedes iniciar sesión.", "success")
                return redirect(url_for("identidad.login"))
            session["registro_correo_pendiente"] = True
            return redirect(
                url_for("identidad.verificacion_pendiente")
            )

        # ----------------------------------------------------
        # Error
        # ----------------------------------------------------

        flash(
            resultado["mensaje"],
            "danger",
        )

    return render_template(
        "auth/registro.html",
        datos_formulario=datos_formulario,
    )


@identidad_bp.route(
    "/api/registro/verificar-dni",
    methods=["POST"],
)
def verificar_dni_para_registro():
    """Consulta APIsPERU sin exponer credenciales ni afirmar titularidad."""
    permitido, reintentar_en = consumir_limite(
        f"dni-registro:{obtener_ip_cliente(request)}",
        maximo=5,
        ventana_segundos=600,
    )
    if not permitido:
        return jsonify({
            "ok": False,
            "estado": "ERROR",
            "mensaje": "Demasiadas consultas. Intenta nuevamente más tarde.",
            "reintentar_en": reintentar_en,
        }), 429

    datos = request.get_json(silent=True) or {}
    if not isinstance(datos, dict):
        return jsonify({
            "ok": False,
            "estado": "INVALIDO",
            "mensaje": "La solicitud de verificación no es válida.",
        }), 400

    resultado = verificar_dni_registro(datos.get("dni"))
    respuesta = jsonify(resultado)
    # La respuesta contiene nombres asociados a un documento: no debe quedar
    # almacenada en cachés de navegador ni en proxies intermedios.
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta, (
        200 if resultado.get("ok")
        else _estado_http_consulta_externa(resultado)
    )


# ============================================================
# LOGIN
# ============================================================

@identidad_bp.route(
    "/login",
    methods=["GET", "POST"],
)
def login():
    """
    Muestra y procesa el inicio de sesión.

    Cuando las credenciales son correctas:

    1. Eliminamos cualquier sesión anterior.
    2. Guardamos únicamente información necesaria.
    3. Redirigimos al usuario.

    Nunca guardamos:
    - contraseña
    - password_hash
    - datos sensibles innecesarios
    """

    # --------------------------------------------------------
    # Si el usuario ya inició sesión, evitamos mostrar
    # nuevamente el formulario de login.
    # --------------------------------------------------------

    if session.get("autenticado"):

        # Una cookie antigua no basta para continuar. Antes de usar sus roles
        # comprobamos que la cuenta siga activa y actualizamos los permisos.
        # Si ya no es válida, se limpia y se muestra el formulario de login.
        if not revalidar_sesion_actual():
            return redirect(url_for("identidad.login"))

        # Ya hay una sesión válida: el formulario no se vuelve a
        # mostrar y el usuario continua en su panel según sus roles
        # ACTIVOS (misma prioridad que el POST de autenticación).
        roles_actuales = session.get("roles", []) or []
        if {"GERENTE", "ADMINISTRADOR"}.intersection(roles_actuales):
            return redirect(url_for("admin.dashboard"))
        if "REPARTIDOR" in roles_actuales:
            return redirect(url_for("repartidor.repartos"))
        return redirect(url_for("inicio"))

    correo = ""

    if request.method == "POST":

        # ----------------------------------------------------
        # Conservamos únicamente el correo si existe un error.
        # La contraseña jamás se devuelve al formulario.
        # ----------------------------------------------------

        correo = request.form.get(
            "correo",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        # --------------------------------------------------------
        # Recordarme
        # --------------------------------------------------------
        #
        # Si el checkbox fue seleccionado llegará el valor "1".
        # Si no fue seleccionado, request.form.get() devuelve None.
        # --------------------------------------------------------

        recordarme = (
            request.form.get("recordarme") == "1"
        )



        # ----------------------------------------------------
        # Capa de servicio
        # ----------------------------------------------------

        resultado = autenticar_usuario(
            correo=correo,
            password=password,
            direccion_ip=obtener_ip_cliente(request),
            user_agent=obtener_agente_cliente(request),
        )

        # ----------------------------------------------------
        # Autenticación correcta
        # ----------------------------------------------------

        if resultado["ok"]:

            usuario = resultado["usuario"]

            # Eliminamos cualquier información que pudiera
            # existir de una sesión anterior.
            session.clear()


            # ------------------------------------------------
            # Datos mínimos de sesión
            # ------------------------------------------------

            session["autenticado"] = True
            session["usuario_id"] = usuario["id"]
            session["correo"] = usuario["correo"]
            session["correo_verificado"] = bool(
                usuario.get("correo_verificado")
            )
            session["requiere_verificacion_correo"] = bool(
                usuario.get("requiere_verificacion_correo")
            )


            # ------------------------------------------------
            # Roles administrativos (Etapa 1)
            # ------------------------------------------------
            #
            # Tras autenticar, consultamos los roles ACTIVOS
            # REALES del usuario (usuario_roles JOIN roles,
            # dominio identidad) y los guardamos en sesión.
            #
            # El decorador @admin_required lee session["roles"]
            # para permitir sólo GERENTE/ADMINISTRADOR.
            #
            # NO inventamos roles ni asignamos GERENTE de forma
            # automática: esto sale de la BD en SOLO LECTURA.
            # ------------------------------------------------

            session["roles"] = obtener_roles_usuario(
                usuario["id"]
            )


            # ------------------------------------------------
            # Duración de sesión
            # ------------------------------------------------
            #
            # Si "Recordarme" está activo:
            # la sesión puede sobrevivir al cierre del navegador.
            #
            # Si no está activo:
            # la cookie se comporta como una sesión normal.
            # ------------------------------------------------

            session.permanent = recordarme

            estado_correo = estado_cuenta(
                usuario.get("correo_verificado"),
                usuario.get("requiere_verificacion_correo"),
                session["roles"],
            )
            if estado_correo == "PENDIENTE_OBLIGATORIO":
                flash(
                    "Iniciaste sesión. Verifica tu correo antes de comprar.",
                    "warning",
                )
                return redirect(url_for("identidad.verificacion_pendiente"))
            if estado_correo == "PENDIENTE_TRANSICION":
                flash(
                    "Tu cuenta histórica sigue activa. Te recomendamos "
                    "verificar tu correo.",
                    "warning",
                )

            # ------------------------------------------------
            # Redirección temporal
            # ------------------------------------------------
            #
            # Más adelante enviaremos al cliente a su
            # dashboard o tienda personalizada.
            # ------------------------------------------------

            flash(
                "Bienvenido a SULPAA.",
                "success",
            )

# ------------------------------------------------
            # Destino posterior al inicio de sesión
            # ------------------------------------------------
            #
            # Prioridad de redirección (roles ACTIVOS reales):
            #
            #  1. GERENTE/ADMINISTRADOR  -> panel administrativo.
            #  2. REPARTIDOR (sin rol    -> su panel de repartos.
            #     administrativo)
            #  3. Resto de usuarios      -> Inicio (cliente).
            #
            # La decisión usa los códigos ACTIVOS recuperados de
            # la BD; no asigna privilegios ni hardcodea una URL.
            # Si el usuario tiene varios roles, gana el panel de
            # mayor jerarquía (admin > repartidor > cliente).
            # ------------------------------------------------

            roles_administrativos = {
                "GERENTE",
                "ADMINISTRADOR",
            }

            if roles_administrativos.intersection(
                session["roles"]
            ):
                return redirect(
                    url_for("admin.dashboard")
                )

            if "REPARTIDOR" in session["roles"]:
                return redirect(
                    url_for("repartidor.repartos")
                )

            return redirect(
                url_for("inicio")
            )

        # ----------------------------------------------------
        # Credenciales incorrectas
        # ----------------------------------------------------

        flash(
            resultado["mensaje"],
            "danger",
        )

    return render_template(
        "auth/login.html",
        correo=correo,
    )


# ============================================================
# VERIFICACIÓN DE CORREO
# ============================================================

@identidad_bp.route("/verificacion/pendiente", methods=["GET"])
def verificacion_pendiente():
    if not current_app.config.get("EMAIL_VERIFICATION_REQUIRED", True):
        abort(404)
    respuesta = make_response(render_template(
        "auth/verificacion_pendiente.html",
        autenticado=bool(session.get("autenticado")),
        correo=session.get("correo", "") if session.get("autenticado") else "",
    ))
    respuesta.headers["Cache-Control"] = "no-store"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    return respuesta


@identidad_bp.route("/verificacion/reenviar", methods=["POST"])
def reenviar_verificacion():
    if not current_app.config.get("EMAIL_VERIFICATION_REQUIRED", True):
        abort(404)
    correo = (
        session.get("correo")
        if session.get("autenticado")
        else request.form.get("correo")
    )
    resultado = solicitar_reenvio(correo, obtener_ip_cliente(request))
    flash(resultado["mensaje"], "info")
    return redirect(url_for("identidad.verificacion_pendiente"))


@identidad_bp.route("/verificacion", methods=["GET", "POST"])
def verificar_correo():
    if not current_app.config.get("EMAIL_VERIFICATION_REQUIRED", True):
        abort(404)
    if request.method == "POST":
        token = request.form.get("token", "")
        resultado = confirmar_correo(token)
        if resultado.get("estado") == "VERIFICADO":
            if session.get("usuario_id") == resultado.get("usuario_id"):
                session["correo_verificado"] = True
            plantilla = "auth/verificacion_exitosa.html"
            codigo = 200
        else:
            plantilla = "auth/verificacion_resultado.html"
            codigo = 400
    else:
        # El token llega en el fragmento #token=..., que nunca se envía en la
        # petición GET ni aparece en access logs. La visita no consulta ni
        # consume el token; el usuario confirma después mediante POST+CSRF.
        resultado = {"estado": "PENDIENTE_CONFIRMACION"}
        plantilla = "auth/verificacion_confirmar.html"
        codigo = 200

    respuesta = make_response(
        render_template(plantilla, estado=resultado.get("estado")),
        codigo,
    )
    respuesta.headers["Cache-Control"] = "no-store"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    respuesta.headers["X-Robots-Tag"] = "noindex, nofollow"
    return respuesta


# ============================================================
# LOGOUT
# ============================================================

@identidad_bp.route(
    "/logout",
    methods=["POST"],
)
def logout():
    """
    Cierra la sesión actual.

    Utilizamos POST en lugar de GET porque cerrar sesión
    modifica el estado de autenticación del usuario.

    La protección CSRF global comprueba el token antes de llegar aquí. Así
    otro sitio no puede cerrar la sesión del usuario sin su autorización.
    """

    # Eliminamos completamente los datos de sesión.
    session.clear()

    flash(
        "Tu sesión se cerró correctamente.",
        "success",
    )

    return redirect(
        url_for("identidad.login")
    )

# ============================================================
# UBICACIÓN GEOGRÁFICA
# ============================================================

@identidad_bp.route(
    "/api/ubicacion/departamentos",
    methods=["GET"],
)
@login_required
def obtener_departamentos():
    """
    Devuelve los departamentos activos.
    """

    departamentos = listar_departamentos()

    return jsonify({
        "ok": True,
        "departamentos": departamentos,
    })


@identidad_bp.route(
    "/api/ubicacion/provincias/<departamento_id>",
    methods=["GET"],
)
@login_required
def obtener_provincias(
    departamento_id,
):
    """
    Devuelve las provincias pertenecientes
    al departamento solicitado.
    """

    provincias = listar_provincias(
        departamento_id
    )

    return jsonify({
        "ok": True,
        "provincias": provincias,
    })


@identidad_bp.route(
    "/api/ubicacion/distritos/<provincia_id>",
    methods=["GET"],
)
@login_required
def obtener_distritos(
    provincia_id,
):
    """
    Devuelve los distritos pertenecientes
    a la provincia solicitada.
    """

    distritos = listar_distritos(
        provincia_id
    )

    return jsonify({
        "ok": True,
        "distritos": distritos,
    })

# ============================================================
# GUARDAR DIRECCIÓN DEL CLIENTE
# ============================================================

@identidad_bp.route(
    "/api/direcciones",
    methods=["POST"],
)
@login_required
def guardar_direccion():
    """
    Registra una nueva dirección principal
    para el usuario autenticado.
    """

    datos = request.get_json(
        silent=True
    ) or {}

    if not isinstance(datos, dict):
        return jsonify({"ok": False, "mensaje": "Dirección inválida."}), 400

    resultado = registrar_direccion_usuario(
        usuario_id=session["usuario_id"],
        distrito_id=datos.get("distrito_id"),
        direccion=datos.get("direccion"),
        referencia=datos.get("referencia"),
        alias=datos.get("alias"),
        latitud=datos.get("latitud"),
        longitud=datos.get("longitud"),
    )

    if not resultado["ok"]:
        return jsonify(resultado), 400

    return jsonify(resultado), 201

# ============================================================
# VERIFICACIÓN DE DNI
# ============================================================

@identidad_bp.route(
    "/api/facturacion/verificar-dni",
    methods=["POST"],
)
@login_required
def verificar_dni_facturacion():
    """
    Verifica un DNI mediante APIsPERU y comprueba
    que corresponda al usuario autenticado.
    """

    datos = request.get_json(
        silent=True
    ) or {}

    resultado = validar_dni_con_perfil(
        usuario_id=session["usuario_id"],
        dni=datos.get("dni"),
    )

    if not resultado["ok"]:

        return jsonify(resultado), _estado_http_consulta_externa(resultado)

    return jsonify(
        resultado
    ), 200

# ============================================================
# VERIFICACIÓN DE RUC
# ============================================================

@identidad_bp.route(
    "/api/facturacion/verificar-ruc",
    methods=["POST"],
)
@login_required
def verificar_ruc_facturacion():
    """
    Verifica un RUC mediante APIsPERU.

    La consulta se realiza únicamente desde el backend.
    El token de APIsPERU nunca se expone al navegador.
    """

    datos = request.get_json(
        silent=True
    ) or {}

    resultado = validar_ruc_facturacion(
        ruc=datos.get("ruc"),
    )

    if not resultado["ok"]:
        return jsonify(resultado), _estado_http_consulta_externa(resultado)

    return jsonify(
        resultado
    ), 200

# ============================================================
# GUARDAR FACTURACIÓN DEL CHECKOUT
# Implementación rama: serna
# ============================================================

@identidad_bp.route(
    "/api/facturacion/guardar",
    methods=["POST"],
)
@login_required
def guardar_facturacion_checkout():
    """
    Guarda los datos de facturación del usuario autenticado.

    El documento se vuelve a verificar desde el backend
    antes de persistir la información.
    """

    datos = request.get_json(
        silent=True
    ) or {}

    resultado = registrar_facturacion_checkout(
        usuario_id=session["usuario_id"],
        tipo_comprobante=(
            datos.get("tipo_comprobante") or datos.get("tipo")
        ),
        documento=datos.get("documento"),
    )

    if not resultado["ok"]:
        return jsonify(resultado), _estado_http_consulta_externa(resultado)

    return jsonify(
        resultado
    ), 200
