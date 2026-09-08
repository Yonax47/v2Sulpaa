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
    """
    Muestra la tienda principal.

    Carga:
    - catálogo;
    - variantes;
    - packs;
    - packs personalizados;
    - carrito actual del usuario.
    """

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
    """
    Valida desde backend si una variante individual
    puede agregarse al carrito según el stock disponible.
    """

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
    """
    Valida la cantidad solicitada de un pack fijo
    utilizando la disponibilidad real de sus componentes.
    """

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
    """
    Devuelve el carrito actual del usuario autenticado.

    El carrito se construye completamente desde backend.

    Además de los productos y subtotal, services.py
    puede incluir información física como:

    - peso_total_gramos;
    - peso_total_kg;
    - peso_completo;
    - variantes_sin_peso.

    Esta información será utilizada posteriormente
    para calcular las opciones de entrega.
    """

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
    """
    Agrega un artículo al carrito del usuario.

    La validación comercial y de inventario
    se realiza dentro de services.py.
    """

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
    """
    Actualiza la cantidad de un detalle del carrito.

    La nueva cantidad vuelve a pasar por las
    validaciones comerciales y de inventario.
    """

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
    """
    Elimina un detalle perteneciente al carrito
    activo del usuario autenticado.
    """

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

    IMPORTANTE:

    Entrar a esta página:

    - NO crea un pedido;
    - NO reserva inventario;
    - NO modifica existencias;
    - NO confirma una compra.

    El checkout únicamente reúne la información
    necesaria para preparar el pedido.

    El carrito recibido desde services.py incluye
    también el peso calculado desde los datos
    registrados en la base de datos.
    """

    usuario_id = session[
        "usuario_id"
    ]

    # --------------------------------------------------------
    # 1. Obtener carrito actual
    # --------------------------------------------------------
    #
    # No utilizamos información enviada por JavaScript
    # para reconstruir precios, cantidades o pesos.
    #
    # El backend vuelve a consultar el carrito.
    # --------------------------------------------------------

    carrito = obtener_carrito_usuario(
        usuario_id
    )

    # --------------------------------------------------------
    # 2. Obtener departamentos disponibles
    # --------------------------------------------------------
    #
    # Se cargan incluso antes de consultar los datos
    # completos del checkout porque también pueden
    # utilizarse para formularios de dirección.
    # --------------------------------------------------------

    departamentos = listar_departamentos()

    # --------------------------------------------------------
    # 3. Carrito vacío
    # --------------------------------------------------------
    #
    # No tiene sentido preparar datos de checkout
    # si el usuario no tiene productos.
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
    # 4. Datos del cliente
    # --------------------------------------------------------
    #
    # Aquí se obtienen los datos necesarios para
    # identificación, dirección y facturación.
    # --------------------------------------------------------

    datos_checkout = obtener_checkout_usuario(
        usuario_id
    )

    # --------------------------------------------------------
    # 5. Información física del carrito
    # --------------------------------------------------------
    #
    # services.py incorpora al carrito:
    #
    # peso_total_gramos
    # peso_total_kg
    # peso_completo
    # variantes_sin_peso
    #
    # El cálculo se realiza en backend utilizando
    # las variantes reales que componen el carrito.
    #
    # Esto es especialmente importante porque un
    # artículo puede ser:
    #
    # - una variante individual;
    # - un pack fijo;
    # - un pack personalizado.
    #
    # El navegador NO debe decidir cuánto pesa
    # un pedido.
    # --------------------------------------------------------

    # --------------------------------------------------------
    # 6. Renderizar checkout
    # --------------------------------------------------------

    return render_template(
        "cliente/checkout.html",

        carrito=carrito,

        checkout=datos_checkout,

        carrito_vacio=False,

        departamentos=departamentos,
    )