"""
Rutas HTTP del módulo de Operaciones de SULPAA V2.

Estas rutas permiten al checkout consultar:

- modalidades de entrega disponibles;
- transportistas;
- servicios de cada transportista;
- agencias disponibles;
- cotizaciones de delivery local;
- cotizaciones de envíos interprovinciales.

REGLA DE SEGURIDAD:

El frontend nunca decide:

- el peso del carrito;
- el subtotal del carrito;
- el costo final de entrega.

Toda esa información se obtiene y se recalcula
nuevamente desde backend.
"""

from flask import (
    Blueprint,
    jsonify,
    request,
    session,
)

from app.shared.decorators import (
    login_required,
)

from app.operaciones.services import (
    obtener_opciones_entrega_checkout,
    obtener_transportistas_checkout,
    obtener_servicios_checkout,
    obtener_agencias_destino_checkout,
    cotizar_delivery_local,
    cotizar_envio_transportista,
    obtener_metodos_pago_checkout,
)


# ============================================================
# BLUEPRINT
# ============================================================

operaciones_bp = Blueprint(
    "operaciones",
    __name__,
    url_prefix="/operaciones",
)


# ============================================================
# UTILIDADES INTERNAS
# ============================================================

def _json_body():
    """
    Obtiene de forma segura el JSON enviado por el cliente.

    Si el cuerpo no contiene un objeto JSON válido,
    devuelve un diccionario vacío.
    """

    datos = request.get_json(
        silent=True
    )

    if not isinstance(
        datos,
        dict,
    ):
        return {}

    return datos


def _respuesta(
    resultado,
    estado_error=400,
):
    """
    Convierte la respuesta de un servicio
    al formato HTTP utilizado por las APIs.
    """

    if resultado.get("ok"):

        return jsonify(
            resultado
        ), 200

    return jsonify(
        resultado
    ), estado_error


# ============================================================
# 1. OPCIONES DE ENTREGA
# ============================================================

@operaciones_bp.route(
    "/api/entregas/opciones",
    methods=["GET"],
)
@login_required
def api_opciones_entrega():
    """
    Devuelve únicamente las modalidades que realmente
    están disponibles según la configuración actual.
    """

    resultado = (
        obtener_opciones_entrega_checkout()
    )

    return _respuesta(
        resultado
    )


# ============================================================
# 2. DELIVERY LOCAL
# ============================================================

@operaciones_bp.route(
    "/api/entregas/delivery/cotizar",
    methods=["POST"],
)
@login_required
def api_cotizar_delivery_local():
    """
    Cotiza un delivery local.

    El navegador únicamente proporciona la distancia
    determinada por el sistema de mapas.

    El backend obtiene por su cuenta:

    - peso real del carrito;
    - subtotal real del carrito;
    - tarifa vigente.

    Por seguridad NO se acepta peso ni subtotal
    enviados desde JavaScript.
    """

    datos = _json_body()

    resultado = cotizar_delivery_local(
        usuario_id=session[
            "usuario_id"
        ],
        distancia_km=datos.get(
            "distancia_km"
        ),
    )

    return _respuesta(
        resultado
    )


# ============================================================
# 3. TRANSPORTISTAS
# ============================================================

@operaciones_bp.route(
    "/api/transportistas",
    methods=["GET"],
)
@login_required
def api_transportistas():
    """
    Lista las empresas de transporte activas.
    """

    resultado = (
        obtener_transportistas_checkout()
    )

    return _respuesta(
        resultado
    )


# ============================================================
# 4. SERVICIOS DE TRANSPORTISTA
# ============================================================

@operaciones_bp.route(
    "/api/transportistas/<transportista_id>/servicios",
    methods=["GET"],
)
@login_required
def api_servicios_transportista(
    transportista_id,
):
    """
    Lista los servicios activos de un
    transportista concreto.
    """

    resultado = obtener_servicios_checkout(
        transportista_id
    )

    return _respuesta(
        resultado
    )


# ============================================================
# 5. AGENCIAS DE TRANSPORTISTA
# ============================================================

@operaciones_bp.route(
    "/api/transportistas/<transportista_id>/agencias",
    methods=["GET"],
)
@login_required
def api_agencias_transportista(
    transportista_id,
):
    """
    Lista las agencias que pueden utilizarse
    como destino.

    Puede filtrarse opcionalmente por distrito:

        ?distrito_id=150101
    """

    distrito_id = (
        request.args.get(
            "distrito_id",
            "",
        ).strip()
    )

    resultado = (
        obtener_agencias_destino_checkout(
            transportista_id=(
                transportista_id
            ),
            distrito_id=(
                distrito_id
                or None
            ),
        )
    )

    return _respuesta(
        resultado
    )


# ============================================================
# 6. ENVÍO INTERPROVINCIAL
# ============================================================

@operaciones_bp.route(
    "/api/entregas/transportista/cotizar",
    methods=["POST"],
)
@login_required
def api_cotizar_transportista():
    """
    Calcula una cotización mediante transportista.

    El usuario puede seleccionar:

    - transportista;
    - servicio;
    - distrito destino;
    - agencia destino.

    El peso del pedido NO se acepta desde frontend.

    El backend obtiene nuevamente el carrito del
    usuario autenticado y calcula su peso real.
    """

    datos = _json_body()

    resultado = cotizar_envio_transportista(
        usuario_id=session[
            "usuario_id"
        ],

        transportista_id=datos.get(
            "transportista_id"
        ),

        servicio_transportista_id=(
            datos.get(
                "servicio_transportista_id"
            )
        ),

        distrito_destino_id=datos.get(
            "distrito_destino_id"
        ),

        sucursal_destino_id=datos.get(
            "sucursal_destino_id"
        ),
    )

    return _respuesta(
        resultado
    )

# ============================================================
# 7. MÉTODOS DE PAGO
# ============================================================

@operaciones_bp.route(
    "/api/metodos-pago",
    methods=["GET"],
)
@login_required
def api_metodos_pago():
    """
    Obtiene los métodos de pago permitidos para
    la modalidad de entrega seleccionada.

    Ejemplos:

        /operaciones/api/metodos-pago
            ?tipo_entrega=RECOJO_LOCAL

        /operaciones/api/metodos-pago
            ?tipo_entrega=DELIVERY_LOCAL

        /operaciones/api/metodos-pago
            ?tipo_entrega=TRANSPORTISTA

    La modalidad de pago se determina en backend
    y nunca se confía en una modalidad enviada
    directamente desde JavaScript.
    """

    tipo_entrega = (
        request.args.get(
            "tipo_entrega",
            "",
        ).strip()
    )

    resultado = (
        obtener_metodos_pago_checkout(
            tipo_entrega
        )
    )

    return _respuesta(
        resultado
    )