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
)

from app.shared.decorators import (
    login_required,
)

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
)


# ============================================================
# BLUEPRINT DEL MÓDULO IDENTIDAD
# ============================================================

identidad_bp = Blueprint(
    "identidad",
    __name__,
    url_prefix="/identidad",
)


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

        # ----------------------------------------------------
        # Datos no sensibles que podemos volver a mostrar
        # si ocurre un error.
        # ----------------------------------------------------

        datos_formulario = {
            "nombres": request.form.get(
                "nombres",
                "",
            ),
            "apellido_paterno": request.form.get(
                "apellido_paterno",
                "",
            ),
            "apellido_materno": request.form.get(
                "apellido_materno",
                "",
            ),
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
            nombres=datos_formulario["nombres"],
            apellido_paterno=datos_formulario[
                "apellido_paterno"
            ],
            apellido_materno=datos_formulario[
                "apellido_materno"
            ],
            dni=datos_formulario["dni"],
            telefono=datos_formulario["telefono"],
        )

        # ----------------------------------------------------
        # Registro correcto
        # ----------------------------------------------------

        if resultado["ok"]:

            flash(
                "Cuenta creada correctamente. "
                "Ahora puedes iniciar sesión.",
                "success",
            )

            # Ahora que Login existe, ya no regresamos
            # al formulario de registro.
            return redirect(
                url_for("identidad.login")
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

        return redirect(
            url_for("inicio")
        )

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

    Más adelante, cuando incorporemos protección CSRF,
    esta acción también quedará protegida mediante token.
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

        return jsonify(
            resultado
        ), 400

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
        return jsonify(
            resultado
        ), 400

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
        tipo=datos.get("tipo"),
        documento=datos.get("documento"),
    )

    if not resultado["ok"]:
        return jsonify(
            resultado
        ), 400

    return jsonify(
        resultado
    ), 200
