"""
Rutas HTTP del módulo Comercio de SULPAA V2.

Las rutas coordinan solicitudes y respuestas.

La lógica comercial permanece en services.py.
"""

from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    session,
)

from app.shared.decorators import (
    login_required,
)

from app.comercio.services import (
    obtener_datos_tienda,
    validar_cantidad_pack,
    validar_cantidad_variante,
    agregar_al_carrito,
    obtener_carrito_usuario,
    actualizar_item_carrito,
    eliminar_item_carrito,
)

from app.identidad.services import (
    obtener_checkout_usuario,
    listar_departamentos,
)



# ============================================================
# BLUEPRINT
# ============================================================

comercio_bp = Blueprint(
    "comercio",
    __name__,
)


# ============================================================
# 1. TIENDA
# ============================================================

@comercio_bp.route(
    "/tienda",
    methods=["GET"],
)
@login_required
def tienda():

    datos = obtener_datos_tienda()

    carrito = obtener_carrito_usuario(
        session["usuario_id"]
    )

    return render_template(
        "cliente/tienda.html",

        catalogo=datos["catalogo"],

        variantes_330=datos[
            "variantes_330"
        ],

        packs=datos["packs"],

        packs_personalizados=datos[
            "packs_personalizados"
        ],

        carrito=carrito,
    )


# ============================================================
# 2. VALIDAR VARIANTE
# ============================================================

@comercio_bp.route(
    "/api/validar-variante",
    methods=["POST"],
)
@login_required
def validar_variante():

    datos = request.get_json(
        silent=True
    ) or {}

    variante_id = datos.get(
        "variante_id"
    )

    cantidad = datos.get(
        "cantidad"
    )

    if not variante_id:

        return jsonify({
            "ok": False,
            "mensaje":
                "No se recibió la variante.",
        }), 400

    resultado = validar_cantidad_variante(
        variante_id,
        cantidad,
        session["usuario_id"],
    )

    return jsonify({
        "ok":
            resultado["valido"],

        "mensaje":
            resultado["mensaje"],

        "stock_disponible":
            resultado[
                "stock_disponible"
            ],
    }), (
        200
        if resultado["valido"]
        else 400
    )


# ============================================================
# 3. VALIDAR PACK FIJO
# ============================================================

@comercio_bp.route(
    "/api/validar-pack",
    methods=["POST"],
)
@login_required
def validar_pack():

    datos = request.get_json(
        silent=True
    ) or {}

    pack_id = datos.get(
        "pack_id"
    )

    cantidad = datos.get(
        "cantidad"
    )

    if not pack_id:

        return jsonify({
            "ok": False,
            "mensaje":
                "No se recibió el pack.",
        }), 400

    resultado = validar_cantidad_pack(
        pack_id,
        cantidad,
        session["usuario_id"],
    )

    return jsonify({
        "ok":
            resultado["valido"],

        "mensaje":
            resultado["mensaje"],

        "packs_disponibles":
            resultado[
                "packs_disponibles"
            ],
    }), (
        200
        if resultado["valido"]
        else 400
    )


# ============================================================
# 4. OBTENER CARRITO
# ============================================================

@comercio_bp.route(
    "/api/carrito",
    methods=["GET"],
)
@login_required
def obtener_carrito():

    carrito = obtener_carrito_usuario(
        session["usuario_id"]
    )

    return jsonify({
        "ok": True,
        "carrito": carrito,
    })


# ============================================================
# 5. AGREGAR AL CARRITO
# ============================================================

@comercio_bp.route(
    "/api/carrito/agregar",
    methods=["POST"],
)
@login_required
def agregar_carrito():

    datos = request.get_json(
        silent=True
    ) or {}

    articulo_venta_id = datos.get(
        "articulo_venta_id"
    )

    cantidad = datos.get(
        "cantidad",
        1,
    )

    composicion = datos.get(
        "composicion"
    )

    if not articulo_venta_id:

        return jsonify({
            "ok": False,
            "mensaje":
                "No se recibió el artículo.",
        }), 400

    resultado = agregar_al_carrito(
        usuario_id=session[
            "usuario_id"
        ],
        articulo_venta_id=(
            articulo_venta_id
        ),
        cantidad=cantidad,
        composicion=composicion,
    )

    if not resultado["ok"]:

        return jsonify(
            resultado
        ), 400

    return jsonify(
        resultado
    ), 200


# ============================================================
# 6. ACTUALIZAR CANTIDAD DEL CARRITO
# ============================================================

@comercio_bp.route(
    "/api/carrito/actualizar",
    methods=["POST"],
)
@login_required
def actualizar_carrito():

    datos = request.get_json(
        silent=True
    ) or {}

    carrito_detalle_id = datos.get(
        "carrito_detalle_id"
    )

    cantidad = datos.get(
        "cantidad"
    )

    if not carrito_detalle_id:

        return jsonify({
            "ok": False,
            "mensaje":
                "No se recibió el producto del carrito.",
        }), 400

    resultado = actualizar_item_carrito(
        usuario_id=session[
            "usuario_id"
        ],
        carrito_detalle_id=(
            carrito_detalle_id
        ),
        nueva_cantidad=cantidad,
    )

    if not resultado["ok"]:

        return jsonify(
            resultado
        ), 400

    return jsonify(
        resultado
    ), 200


# ============================================================
# 7. ELIMINAR DEL CARRITO
# ============================================================

@comercio_bp.route(
    "/api/carrito/eliminar",
    methods=["POST"],
)
@login_required
def eliminar_carrito():

    datos = request.get_json(
        silent=True
    ) or {}

    carrito_detalle_id = datos.get(
        "carrito_detalle_id"
    )

    if not carrito_detalle_id:

        return jsonify({
            "ok": False,
            "mensaje":
                "No se recibió el producto del carrito.",
        }), 400

    resultado = eliminar_item_carrito(
        usuario_id=session[
            "usuario_id"
        ],
        carrito_detalle_id=(
            carrito_detalle_id
        ),
    )

    if not resultado["ok"]:

        return jsonify(
            resultado
        ), 400

    return jsonify(
        resultado
    ), 200

# ============================================================
# 8. CHECKOUT
# ============================================================

@comercio_bp.route(
    "/checkout",
    methods=["GET"],
)
@login_required
def checkout():
    """
    Muestra el checkout del cliente.

    Entrar a esta página NO crea el pedido
    y NO reserva inventario.
    """

    usuario_id = session[
        "usuario_id"
    ]

    # --------------------------------------------------------
    # Carrito actual
    # --------------------------------------------------------

    carrito = obtener_carrito_usuario(
        usuario_id
    )

    # --------------------------------------------------------
    # Departamentos disponibles
    # --------------------------------------------------------

    departamentos = listar_departamentos()

    # --------------------------------------------------------
    # Carrito vacío
    # --------------------------------------------------------

    if not carrito["items"]:

        return render_template(
            "cliente/checkout.html",
            carrito=carrito,
            checkout=None,
            carrito_vacio=True,
            departamentos=departamentos,
        )

    # --------------------------------------------------------
    # Datos del cliente
    # --------------------------------------------------------

    datos_checkout = obtener_checkout_usuario(
        usuario_id
    )

    return render_template(
        "cliente/checkout.html",
        carrito=carrito,
        checkout=datos_checkout,
        carrito_vacio=False,
        departamentos=departamentos,
    )

    # --------------------------------------------------------
    # Datos del cliente
    # --------------------------------------------------------

    datos_checkout = obtener_checkout_usuario(
        usuario_id
    )

    return render_template(
        "cliente/checkout.html",

        carrito=carrito,

        checkout=datos_checkout,

        carrito_vacio=False,
    )