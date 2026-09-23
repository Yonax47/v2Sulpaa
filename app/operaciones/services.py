"""
Servicios del módulo de Operaciones de SULPAA V2.

Aquí vive la lógica de negocio relacionada con:

- recojo local;
- delivery local;
- envíos mediante transportistas;
- cálculo y validación de tarifas.

REGLAS IMPORTANTES DE SEGURIDAD:

El frontend nunca decide:

- peso del carrito;
- subtotal del carrito;
- costo del envío.

El backend vuelve a obtener el carrito actual del
usuario autenticado antes de realizar una cotización.

Las tarifas siempre se calculan utilizando la
configuración almacenada en:

v2sulpaa_operaciones_db
"""

from decimal import (
    Decimal,
    ROUND_HALF_UP,
    InvalidOperation,
)

from app.operaciones.repositories import (
    listar_puntos_recojo_activos,
    listar_transportistas_activos,
    listar_servicios_transportista_activos,
    listar_sucursales_destino_activas,
    obtener_transportista_activo,
    obtener_servicio_transportista_activo,
    obtener_sucursal_destino_activa,
    obtener_tarifa_delivery_activa,
    obtener_tarifario_activo_transportista,
    obtener_regla_tarifa_transportista,
    obtener_rango_tarifa_por_peso,
    listar_metodos_pago_activos,
    crear_pago_pedido,
    cancelar_pago_pedido,
    guardar_entrega_checkout,
    cancelar_entrega_checkout,
)




# ============================================================
# UTILIDADES INTERNAS
# ============================================================

def _decimal(
    valor,
    defecto="0",
):
    """
    Convierte valores provenientes de MySQL
    a Decimal de forma segura.
    """

    if valor is None:

        return Decimal(
            defecto
        )

    return Decimal(
        str(valor)
    )


def _dinero(valor):
    """
    Normaliza un importe monetario
    a exactamente dos decimales.
    """

    return _decimal(
        valor
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _numero_positivo(
    valor,
    nombre,
):
    """
    Convierte un valor a Decimal y exige
    que sea mayor que cero.
    """

    try:

        numero = _decimal(
            valor
        )

    except (
        ValueError,
        TypeError,
        InvalidOperation,
    ):

        raise ValueError(
            f"{nombre} no es válido."
        )

    if not numero.is_finite() or numero <= 0:

        raise ValueError(
            f"{nombre} debe ser mayor que cero."
        )

    return numero


# ============================================================
# OBTENER DATOS SEGUROS DEL CARRITO
# ============================================================

def _obtener_datos_carrito_entrega(
    usuario_id,
):
    """
    Obtiene desde Comercio los datos del carrito
    necesarios para calcular una entrega.

    Esta función evita confiar en valores enviados
    por el navegador.

    Devuelve:

    - carrito;
    - peso en gramos;
    - peso en kilogramos;
    - subtotal.

    También valida que todas las variantes utilizadas
    tengan un peso registrado en la base de datos.
    """

    if not usuario_id:

        return {
            "ok": False,
            "mensaje":
                "No se pudo identificar al usuario.",
        }

    # Import local para evitar dependencia circular
    # entre Comercio y Operaciones durante el arranque.
    from app.comercio.services import (
        obtener_carrito_usuario,
    )

    carrito = obtener_carrito_usuario(
        usuario_id
    )
    
    # --------------------------------------------------------
    # Carrito inexistente o vacío
    # --------------------------------------------------------

    if (
        not carrito
        or not carrito.get("items")
    ):

        return {
            "ok": False,
            "mensaje":
                "El carrito está vacío.",
        }

    # --------------------------------------------------------
    # Verificar que todos los productos tengan peso
    # --------------------------------------------------------

    if not carrito.get(
        "peso_completo",
        False,
    ):

        return {
            "ok": False,
            "mensaje":
                (
                    "No se puede calcular la entrega "
                    "porque existen productos sin peso "
                    "registrado."
                ),
            "variantes_sin_peso":
                carrito.get(
                    "variantes_sin_peso",
                    [],
                ),
        }

    # --------------------------------------------------------
    # Peso total
    # --------------------------------------------------------

    peso_gramos = _decimal(
        carrito.get(
            "peso_total_gramos",
            0,
        )
    )

    peso_kg = _decimal(
        carrito.get(
            "peso_total_kg",
            0,
        )
    )

    if (
        peso_gramos <= 0
        or peso_kg <= 0
    ):

        return {
            "ok": False,
            "mensaje":
                (
                    "No se pudo determinar el peso "
                    "del pedido."
                ),
        }

    # --------------------------------------------------------
    # Subtotal
    # --------------------------------------------------------

    subtotal = _decimal(
        carrito.get(
            "subtotal",
            0,
        )
    )

    if subtotal < 0:

        return {
            "ok": False,
            "mensaje":
                (
                    "El subtotal del carrito "
                    "no es válido."
                ),
        }

    return {
        "ok": True,
        "carrito": carrito,
        "peso_gramos": peso_gramos,
        "peso_kg": peso_kg,
        "subtotal": subtotal,
    }


# ============================================================
# OPCIONES GENERALES DE ENTREGA
# ============================================================

def obtener_opciones_entrega_checkout():
    """
    Devuelve las modalidades de entrega que realmente
    pueden ofrecerse según la configuración actual.

    RECOJO_LOCAL:
        Disponible si existe al menos un punto
        de recojo activo.

    DELIVERY_LOCAL:
        Disponible si existe una tarifa vigente.

    TRANSPORTISTA:
        Disponible si existe al menos un
        transportista activo.

    Esta función no inventa disponibilidad.
    """

    puntos_recojo = (
        listar_puntos_recojo_activos()
    )

    tarifa_delivery = (
        obtener_tarifa_delivery_activa()
    )

    transportistas = (
        listar_transportistas_activos()
    )

    opciones = []

    # --------------------------------------------------------
    # Recojo local
    # --------------------------------------------------------

    if puntos_recojo:

        opciones.append({
            "tipo":
                "RECOJO_LOCAL",

            "nombre":
                "Recojo en local",

            "descripcion":
                (
                    "Recoge tu pedido en un "
                    "punto de atención SULPAA."
                ),

            "costo":
                "0.00",

            "puntos_recojo":
                puntos_recojo,
        })

    # --------------------------------------------------------
    # Delivery local
    # --------------------------------------------------------

    if tarifa_delivery:

        opciones.append({
            "tipo":
                "DELIVERY_LOCAL",

            "nombre":
                "Delivery local",

            "descripcion":
                (
                    "Entrega directa en una dirección "
                    "dentro de la cobertura disponible."
                ),

            "tarifa":
                tarifa_delivery,
        })

    # --------------------------------------------------------
    # Transportista
    # --------------------------------------------------------

    if transportistas:

        opciones.append({
            "tipo":
                "TRANSPORTISTA",

            "nombre":
                "Envío interprovincial",

            "descripcion":
                (
                    "Envío mediante una empresa "
                    "de transporte disponible."
                ),

            "transportistas":
                transportistas,
        })

    return {
        "ok": True,
        "opciones": opciones,
        "origen_delivery": _origen_delivery(puntos_recojo),
    }


# ============================================================
# DELIVERY LOCAL
# ============================================================

def cotizar_delivery_local(
    usuario_id,
    distancia_km,
):
    """
    Calcula el costo del delivery local.

    El frontend proporciona únicamente la distancia
    obtenida por el sistema de mapas.

    El backend vuelve a obtener:

    - peso real del carrito;
    - subtotal real;
    - tarifa activa.

    Fórmula:

        tarifa base
        + kilómetros adicionales
        + peso adicional

    Los recargos por hora pico, feriado, espera
    o cancelación NO se agregan automáticamente.

    Esos conceptos corresponden a eventos
    operativos posteriores.
    """

    # --------------------------------------------------------
    # 1. Obtener datos seguros del carrito
    # --------------------------------------------------------

    datos_carrito = (
        _obtener_datos_carrito_entrega(
            usuario_id
        )
    )

    if not datos_carrito["ok"]:

        return datos_carrito

    peso = datos_carrito[
        "peso_kg"
    ]

    subtotal = datos_carrito[
        "subtotal"
    ]

    # --------------------------------------------------------
    # 2. Tarifa activa
    # --------------------------------------------------------

    tarifa = (
        obtener_tarifa_delivery_activa()
    )

    if not tarifa:

        return {
            "ok": False,
            "mensaje":
                (
                    "No existe una tarifa "
                    "de delivery activa."
                ),
        }

    # --------------------------------------------------------
    # 3. Validar distancia
    # --------------------------------------------------------

    try:

        distancia = _numero_positivo(
            distancia_km,
            "La distancia",
        )

    except ValueError as error:

        return {
            "ok": False,
            "mensaje":
                str(error),
        }

    # --------------------------------------------------------
    # 4. Validar cobertura máxima
    # --------------------------------------------------------

    distancia_maxima = _decimal(
        tarifa.get(
            "distancia_maxima_km"
        )
    )

    if (
        distancia_maxima > 0
        and distancia > distancia_maxima
    ):

        return {
            "ok": False,
            "tipo":
                "DELIVERY_LOCAL",

            "mensaje":
                (
                    "La dirección está fuera "
                    "de la cobertura del "
                    "delivery local."
                ),

            "distancia_km":
                float(distancia),

            "distancia_maxima_km":
                float(
                    distancia_maxima
                ),
        }

    # --------------------------------------------------------
    # 5. Validar peso máximo
    # --------------------------------------------------------
    peso_maximo = _decimal(tarifa.get("peso_maximo_kg"))
    if peso_maximo > 0 and peso > peso_maximo:
        return {"ok": False, "mensaje": "El pedido supera el peso máximo del delivery local."}
   

    # --------------------------------------------------------
    # 6. Envío gratis
    # --------------------------------------------------------

    monto_envio_gratis = (
        tarifa.get(
            "monto_envio_gratis"
        )
    )

    if monto_envio_gratis is not None:

        minimo_gratis = _decimal(
            monto_envio_gratis
        )

        if (
            minimo_gratis > 0
            and subtotal >= minimo_gratis
        ):

            return {
                "ok": True,
                "tipo":
                    "DELIVERY_LOCAL",

                "tarifa_delivery_id":
                    tarifa["id"],
                "tarifa_snapshot": tarifa,

                "distancia_km":
                    float(distancia),

                "peso_kg":
                    float(peso),

                "subtotal_productos":
                    float(subtotal),

                "costo_entrega":
                    0.0,

                "envio_gratis":
                    True,
            }

    # --------------------------------------------------------
    # 7. Tarifa base
    # --------------------------------------------------------

    costo = _decimal(
        tarifa["tarifa_base"]
    )

    # --------------------------------------------------------
    # 8. Kilómetros adicionales
    # --------------------------------------------------------

    km_incluidos = _decimal(
        tarifa["km_incluidos"]
    )

    precio_km_adicional = _decimal(
        tarifa[
            "precio_km_adicional"
        ]
    )

    if distancia > km_incluidos:

        km_adicionales = (
            distancia
            - km_incluidos
        )

        costo += (
            km_adicionales
            * precio_km_adicional
        )

    # --------------------------------------------------------
    # 9. Peso adicional
    # --------------------------------------------------------

    peso_incluido = _decimal(
        tarifa["peso_incluido_kg"]
    )

    precio_kg_adicional = _decimal(
        tarifa[
            "precio_kg_adicional"
        ]
    )

    if peso > peso_incluido:

        kg_adicionales = (
            peso
            - peso_incluido
        )

        costo += (
            kg_adicionales
            * precio_kg_adicional
        )

    # --------------------------------------------------------
    # 10. Normalizar costo
    # --------------------------------------------------------

    costo = _dinero(
        costo
    )

    # --------------------------------------------------------
    # 11. Resultado
    # --------------------------------------------------------

    return {
        "ok": True,

        "tipo":
            "DELIVERY_LOCAL",

        "tarifa_delivery_id":
            tarifa["id"],
        "tarifa_snapshot": tarifa,

        "distancia_km":
            float(distancia),

        "peso_kg":
            float(peso),

        "subtotal_productos":
            float(subtotal),

        "costo_entrega":
            float(costo),

        "envio_gratis":
            False,
    }


# ============================================================
# TRANSPORTISTAS
# ============================================================

def obtener_transportistas_checkout():
    """
    Lista los transportistas activos
    disponibles para checkout.
    """

    transportistas = (
        listar_transportistas_activos()
    )

    return {
        "ok": True,
        "transportistas":
            transportistas,
    }


# ============================================================
# SERVICIOS DE TRANSPORTISTA
# ============================================================

def obtener_servicios_checkout(
    transportista_id,
):
    """
    Devuelve únicamente servicios activos
    pertenecientes al transportista indicado.
    """

    if not transportista_id:

        return {
            "ok": False,
            "mensaje":
                (
                    "Debe seleccionar "
                    "un transportista."
                ),
        }

    transportista = (
        obtener_transportista_activo(
            transportista_id
        )
    )

    if not transportista:

        return {
            "ok": False,
            "mensaje":
                (
                    "El transportista seleccionado "
                    "no está disponible."
                ),
        }

    servicios = (
        listar_servicios_transportista_activos(
            transportista_id
        )
    )

    return {
        "ok": True,

        "transportista":
            transportista,

        "servicios":
            servicios,
    }


# ============================================================
# AGENCIAS DE DESTINO
# ============================================================

def obtener_agencias_destino_checkout(
    transportista_id,
    distrito_id=None,
):
    """
    Obtiene agencias habilitadas como destino.

    Si se indica distrito_id devuelve únicamente
    las agencias pertenecientes a dicho distrito.
    """

    if not transportista_id:

        return {
            "ok": False,
            "mensaje":
                (
                    "Debe seleccionar "
                    "un transportista."
                ),
        }

    transportista = (
        obtener_transportista_activo(
            transportista_id
        )
    )

    if not transportista:

        return {
            "ok": False,
            "mensaje":
                (
                    "El transportista seleccionado "
                    "no está disponible."
                ),
        }

    sucursales = (
        listar_sucursales_destino_activas(
            transportista_id,
            distrito_id,
        )
    )

    return {
        "ok": True,

        "transportista":
            transportista,

        "sucursales":
            sucursales,
    }


# ============================================================
# COTIZACIÓN INTERPROVINCIAL
# ============================================================

def cotizar_envio_transportista(
    usuario_id,
    transportista_id,
    servicio_transportista_id,
    distrito_destino_id,
    sucursal_destino_id=None,
):
    """
    Calcula una cotización interprovincial.

    Flujo:

        carrito real del usuario
                ↓
        peso real en backend
                ↓
        transportista
                ↓
        tarifario vigente
                ↓
        servicio
                ↓
        distrito destino
                ↓
        regla tarifaria
                ↓
        rango de peso
                ↓
        costo

    IMPORTANTE:

    El peso NO se recibe desde JavaScript.

    Si el peso no coincide con ningún rango
    configurado, la cotización se rechaza.

    Nunca se inventa una tarifa.

    Los métodos que necesiten peso volumétrico
    se completarán cuando existan dimensiones
    físicas reales del paquete.
    """

    # --------------------------------------------------------
    # 1. Datos seguros del carrito
    # --------------------------------------------------------

    datos_carrito = (
        _obtener_datos_carrito_entrega(
            usuario_id
        )
    )

    if not datos_carrito["ok"]:

        return datos_carrito

    peso = datos_carrito[
        "peso_gramos"
    ]

    # --------------------------------------------------------
    # 2. Validaciones iniciales
    # --------------------------------------------------------

    if not transportista_id:

        return {
            "ok": False,
            "mensaje":
                (
                    "Debe seleccionar "
                    "un transportista."
                ),
        }

    if not servicio_transportista_id:

        return {
            "ok": False,
            "mensaje":
                (
                    "Debe seleccionar "
                    "un servicio de envío."
                ),
        }

    if not distrito_destino_id:

        return {
            "ok": False,
            "mensaje":
                (
                    "Debe indicar el "
                    "distrito de destino."
                ),
        }

    # --------------------------------------------------------
    # 3. Transportista
    # --------------------------------------------------------

    transportista = (
        obtener_transportista_activo(
            transportista_id
        )
    )

    if not transportista:

        return {
            "ok": False,
            "mensaje":
                (
                    "El transportista seleccionado "
                    "no está disponible."
                ),
        }

    # --------------------------------------------------------
    # 4. Servicio
    # --------------------------------------------------------

    servicio = (
        obtener_servicio_transportista_activo(
            servicio_transportista_id,
            transportista_id,
        )
    )

    if not servicio:

        return {
            "ok": False,
            "mensaje":
                (
                    "El servicio seleccionado "
                    "no pertenece al transportista "
                    "o no está disponible."
                ),
        }

    # --------------------------------------------------------
    # 5. Agencia destino
    # --------------------------------------------------------

    sucursal = None

    if sucursal_destino_id:

        sucursal = (
            obtener_sucursal_destino_activa(
                sucursal_destino_id,
                transportista_id,
            )
        )

        if not sucursal:

            return {
                "ok": False,
                "mensaje":
                    (
                        "La agencia de destino "
                        "no está disponible."
                    ),
            }

        if (
            sucursal.get(
                "distrito_id"
            )
            and sucursal[
                "distrito_id"
            ] != distrito_destino_id
        ):

            return {
                "ok": False,
                "mensaje":
                    (
                        "La agencia seleccionada "
                        "no corresponde al "
                        "distrito de destino."
                    ),
            }

    # --------------------------------------------------------
    # 6. Tarifario vigente
    # --------------------------------------------------------

    tarifario = (
        obtener_tarifario_activo_transportista(
            transportista_id
        )
    )

    if not tarifario:

        return {
            "ok": False,
            "mensaje":
                (
                    "El transportista no tiene "
                    "un tarifario vigente disponible."
                ),
        }

    # --------------------------------------------------------
    # 7. Regla tarifaria
    # --------------------------------------------------------

    regla = (
        obtener_regla_tarifa_transportista(
            tarifario["id"],
            servicio_transportista_id,
            distrito_destino_id,
        )
    )

    if not regla:

        return {
            "ok": False,
            "mensaje":
                (
                    "No existe una tarifa configurada "
                    "para el destino y servicio "
                    "seleccionados."
                ),
        }

    # --------------------------------------------------------
    # 8. Peso máximo
    # --------------------------------------------------------

    peso_maximo = _decimal(
        regla.get(
            "peso_maximo_gramos"
        )
    )

    if (
        peso_maximo > 0
        and peso > peso_maximo
    ):

        return {
            "ok": False,

            "mensaje":
                (
                    "El pedido supera el peso "
                    "máximo configurado "
                    "para este servicio."
                ),

            "peso_gramos":
                int(peso),

            "peso_maximo_gramos":
                int(peso_maximo),
        }

    # --------------------------------------------------------
    # 9. Rango tarifario
    # --------------------------------------------------------

    rango = (
        obtener_rango_tarifa_por_peso(
            regla["id"],
            peso,
        )
    )

    if not rango:

        return {
            "ok": False,

            "mensaje":
                (
                    "No existe un rango tarifario "
                    "válido para el peso del pedido."
                ),

            "peso_gramos":
                int(peso),
        }

    # --------------------------------------------------------
    # 10. Precio del rango
    # --------------------------------------------------------

    costo = _decimal(
        rango["precio"]
    )

    # --------------------------------------------------------
    # 11. Recargo fijo configurado
    # --------------------------------------------------------

    costo += _decimal(
        regla.get(
            "recargo_fijo"
        )
    )

    costo = _dinero(
        costo
    )

    # --------------------------------------------------------
    # 12. Resultado
    # --------------------------------------------------------

    return {
        "ok": True,

        "tipo":
            "TRANSPORTISTA",

        "transportista": {
            "id":
                transportista["id"],

            "codigo":
                transportista["codigo"],

            "nombre":
                transportista["nombre"],

            "url_seguimiento":
                transportista.get(
                    "url_seguimiento"
                ),
        },

        "servicio": {
            "id":
                servicio["id"],

            "codigo":
                servicio["codigo"],

            "nombre":
                servicio["nombre"],

            "modalidad":
                servicio["modalidad"],
        },

        "sucursal_destino": (
            {
                "id":
                    sucursal["id"],

                "nombre":
                    sucursal["nombre"],

                "direccion":
                    sucursal["direccion"],

                "distrito_id":
                    sucursal["distrito_id"],
            }

            if sucursal

            else None
        ),

        "tarifario_id":
            tarifario["id"],

        "regla_tarifa_id":
            regla["id"],

        "rango_tarifa_id":
            rango["id"],

        "metodo_calculo":
            regla["metodo_calculo"],

        "peso_estimado_gramos":
            int(peso),

        "costo_entrega":
            float(costo),
    }

# ============================================================
# MÉTODOS DE PAGO DEL CHECKOUT
# ============================================================

def obtener_metodos_pago_checkout(
    tipo_entrega,
):
    """
    Devuelve los métodos de pago disponibles para
    la modalidad de entrega seleccionada.

    Reglas actuales:

    RECOJO_LOCAL
        - Efectivo -> PAGO_EN_LOCAL
        - Yape -> ANTICIPADO
        - Plin -> ANTICIPADO
        - Transferencia -> ANTICIPADO

    DELIVERY_LOCAL
        - Efectivo -> CONTRA_ENTREGA
        - Yape -> ANTICIPADO
        - Plin -> ANTICIPADO
        - Transferencia -> ANTICIPADO

    TRANSPORTISTA
        - No permite efectivo.
        - Yape -> ANTICIPADO
        - Plin -> ANTICIPADO
        - Transferencia -> ANTICIPADO

    IMPORTANTE:

    El frontend no determina la modalidad de pago.
    El backend la asigna según el método y el
    tipo de entrega seleccionado.
    """

    tipos_entrega_validos = {
        "RECOJO_LOCAL",
        "DELIVERY_LOCAL",
        "TRANSPORTISTA",
    }

    tipo_entrega = (
        str(tipo_entrega or "")
        .strip()
        .upper()
    )

    if tipo_entrega not in tipos_entrega_validos:
        return {
            "ok": False,
            "mensaje":
                "Debe seleccionar una modalidad de entrega válida.",
        }

    metodos_bd = (
        listar_metodos_pago_activos()
    )

    metodos = []

    for metodo in metodos_bd:

        codigo = (
            str(
                metodo.get(
                    "codigo",
                    ""
                )
            )
            .strip()
            .upper()
        )

        # ----------------------------------------------------
        # EFECTIVO
        # ----------------------------------------------------

        if codigo == "EFECTIVO":

            if tipo_entrega == "TRANSPORTISTA":
                continue

            if tipo_entrega == "RECOJO_LOCAL":
                modalidad = (
                    "PAGO_EN_LOCAL"
                )

                descripcion = (
                    "Paga en efectivo cuando recojas "
                    "tu pedido en el local."
                )

            else:
                modalidad = (
                    "CONTRA_ENTREGA"
                )

                descripcion = (
                    "Paga en efectivo al momento "
                    "de recibir tu pedido."
                )

        # ----------------------------------------------------
        # PAGOS ANTICIPADOS
        # ----------------------------------------------------

        elif codigo in {
            "YAPE",
            "PLIN",
            "TRANSFERENCIA",
        }:

            modalidad = "ANTICIPADO"

            if codigo == "YAPE":
                descripcion = (
                    "Realiza el pago mediante Yape. "
                    "La operación será verificada "
                    "antes de confirmar el pago."
                )

            elif codigo == "PLIN":
                descripcion = (
                    "Realiza el pago mediante Plin. "
                    "La operación será verificada "
                    "antes de confirmar el pago."
                )

            else:
                descripcion = (
                    "Realiza una transferencia bancaria. "
                    "La operación será verificada "
                    "antes de confirmar el pago."
                )

        # ----------------------------------------------------
        # MÉTODO TODAVÍA NO IMPLEMENTADO
        # ----------------------------------------------------

        else:
            continue

        metodos.append({
            "id":
                metodo["id"],

            "codigo":
                codigo,

            "nombre":
                metodo["nombre"],

            "tipo_confirmacion":
                metodo[
                    "tipo_confirmacion"
                ],

            "modalidad":
                modalidad,

            "descripcion":
                descripcion,
        })

    if not metodos:
        return {
            "ok": False,
            "mensaje":
                (
                    "No existen métodos de pago "
                    "disponibles para esta entrega."
                ),
        }

    return {
        "ok": True,
        "tipo_entrega":
            tipo_entrega,
        "metodos_pago":
            metodos,
    }

# ============================================================
# CREAR PAGO INICIAL DEL CHECKOUT
# ============================================================

def crear_pago_checkout(
    pago_id,
    pedido_id,
    usuario_id,
    tipo_entrega,
    metodo_pago_id,
    monto,
    moneda="PEN",
):
    """
    Crea el pago inicial de un pedido.

    La modalidad nunca se acepta directamente desde frontend.
    Se obtiene nuevamente utilizando las reglas de métodos de
    pago del backend.
    """

    resultado_metodos = (
        obtener_metodos_pago_checkout(
            tipo_entrega
        )
    )

    if not resultado_metodos.get("ok"):

        return resultado_metodos

    try:

        metodo_pago_id = int(
            metodo_pago_id
        )

    except (
        TypeError,
        ValueError,
    ):

        return {
            "ok": False,
            "mensaje":
                "El método de pago seleccionado no es válido.",
        }

    metodo = next(
        (
            item
            for item
            in resultado_metodos[
                "metodos_pago"
            ]
            if int(
                item["id"]
            ) == metodo_pago_id
        ),
        None,
    )

    if not metodo:

        return {
            "ok": False,
            "mensaje":
                (
                    "El método de pago no está permitido "
                    "para la entrega seleccionada."
                ),
        }

    try:

        pago = crear_pago_pedido(
            pago_id=pago_id,
            pedido_id=pedido_id,
            metodo_pago_id=metodo["id"],
            modalidad=metodo["modalidad"],
            monto=monto,
            moneda=moneda,
            usuario_id=usuario_id,
        )

    except ValueError as error:

        return {
            "ok": False,
            "mensaje":
                str(error),
        }

    return {
        "ok": True,

        "pago":
            pago,
    }


# ============================================================
# COMPENSAR PAGO DEL CHECKOUT
# ============================================================

def cancelar_pago_checkout(
    pedido_id,
    usuario_id=None,
    observacion=None,
):
    """
    Revierte el pago cuando una operación posterior del
    checkout impide finalizar correctamente el pedido.
    """

    return cancelar_pago_pedido(
        pedido_id=pedido_id,
        usuario_id=usuario_id,
        observacion=observacion,
    )


# ============================================================
# DESTINOS Y COTIZACIONES VERIFICABLES DEL CHECKOUT
# ============================================================

def _origen_delivery(puntos=None):
    """Usa el local de BD; conserva el origen ya utilizado por el mapa.

    El fallback solo corresponde a SULPAA-EL-TAMBO y permite trabajar
    con el dump inicial, cuyas coordenadas todavía son NULL.
    """
    if puntos is None:
        puntos = listar_puntos_recojo_activos()
    punto = next((p for p in puntos if p['codigo'] == 'SULPAA-EL-TAMBO'), None)
    if not punto:
        return None
    return {
        'latitude': float(punto['latitud']) if punto.get('latitud') is not None else -12.049141052234061,
        'longitude': float(punto['longitud']) if punto.get('longitud') is not None else -75.22147546622413,
    }


def _texto_destino(valor, nombre, minimo=0, maximo=255):
    if valor is None:
        valor = ''
    if not isinstance(valor, str) or not minimo <= len(valor.strip()) <= maximo:
        raise ValueError(f'{nombre} no es válido.')
    return valor.strip()


def _normalizar_ubicacion(texto):
    import unicodedata
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().upper()


def _resolver_distrito_checkout(origen):
    """Resuelve el distrito de un destino de entrega.

    Si el formulario ya trajo un distrito válido, lo conserva.
    Si viene vacío (destino marcado en el mapa), lo deduce de la
    dirección geocodificada contra el catálogo oficial de ubigeo.
    """
    from app.identidad.repositories import buscar_distrito_activo, buscar_distritos_activos
    try:
        distrito = _texto_destino(origen.get('distrito_id'), 'El distrito', 6, 6)
    except ValueError:
        distrito = ''
    if distrito.isascii() and distrito.isdigit() and buscar_distrito_activo(distrito):
        return distrito
    if origen.get('distrito_id'):
        raise ValueError('Selecciona un distrito válido.')
    texto = _normalizar_ubicacion(origen.get("direccion"))
    if len(texto) < 5:
        raise ValueError('Selecciona un distrito válido.')
    mejor, mejor_puntaje = None, -1
    for d in buscar_distritos_activos():
        nombre = _normalizar_ubicacion(d["nombre"])
        if not nombre or nombre not in texto:
            continue
        puntaje = 100
        if _normalizar_ubicacion(d["provincia_nombre"]) in texto:
            puntaje += 40
        if _normalizar_ubicacion(d["departamento_nombre"]) in texto:
            puntaje += 20
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = d, puntaje
    if mejor is None:
        raise ValueError('Selecciona un distrito válido.')
    return mejor['id']


def _destino_checkout(usuario_id, datos, coordenadas=True):
    from app.identidad.repositories import listar_direcciones_usuario, buscar_distrito_activo
    from app.identidad.services import validar_coordenadas_direccion
    direccion_id = datos.get('direccion_id')
    origen = datos
    if direccion_id:
        guardada = next((d for d in listar_direcciones_usuario(usuario_id)
                         if d['id'] == direccion_id), None)
        if not guardada:
            raise ValueError('La dirección no pertenece a tu cuenta o está inactiva.')
        # Una dirección antigua puede completarse en el mapa sin perder su titularidad.
        origen = {**datos, **guardada}
        if guardada.get('latitud') is None or guardada.get('longitud') is None:
            origen.update(latitud=datos.get('latitud'), longitud=datos.get('longitud'))
    distrito = _resolver_distrito_checkout(origen)
    lat, lon = validar_coordenadas_direccion(
        origen.get('latitud'), origen.get('longitud'), obligatorias=coordenadas)
    return {
        'distrito_id': distrito,
        'direccion': _texto_destino(origen.get('direccion'), 'La dirección', 5),
        'referencia': _texto_destino(origen.get('referencia'), 'La referencia') or None,
        'latitud': str(lat) if lat is not None else None,
        'longitud': str(lon) if lon is not None else None,
    }


def _destino_checkout_opcional(usuario_id, datos):
    """Devuelve el destino normalizado si el cliente ya lo completó.

    La cotización de delivery NO requiere el destino: solo la distancia.
    El destino se exige recién al guardar la entrega en la confirmación.
    """
    try:
        return _destino_checkout(usuario_id, datos)
    except ValueError:
        return None


def _preparar_entrega_checkout(usuario_id, datos):
    """Normaliza la selección y vuelve a consultar todos los catálogos relevantes."""
    from app.identidad.repositories import obtener_datos_checkout_usuario
    tipo = datos.get('tipo_entrega')
    if tipo == 'RECOJO_LOCAL':
        punto = next((p for p in listar_puntos_recojo_activos()
                      if p['id'] == datos.get('punto_recojo_id')), None)
        if not punto:
            raise ValueError('Selecciona un punto de recojo activo.')
        return {'ok': True, 'tipo': tipo, 'costo_entrega': 0,
                'punto_recojo': punto, 'direccion_entrega': punto['direccion']}

    if tipo == 'DELIVERY_LOCAL':
        # La cotización depende únicamente de la distancia calculada
        # por el mapa. El destino completo solo se exige al guardar
        # la entrega durante la confirmación del pedido.
        resultado = cotizar_delivery_local(usuario_id, datos.get('distancia_km'))
        if not resultado.get('ok'):
            raise ValueError(resultado['mensaje'])
        cliente = (obtener_datos_checkout_usuario(usuario_id) or {}).get('cliente') or {}
        nombre = ' '.join(str(cliente.get(k) or '').strip()
                          for k in ('nombres', 'apellido_paterno', 'apellido_materno')).strip()
        resultado.update(nombre_receptor=_texto_destino(nombre, 'El nombre del receptor', 2, 150),
                         telefono_receptor=_texto_destino(cliente.get('telefono'), 'El teléfono', 6, 20))
        destino = _destino_checkout_opcional(usuario_id, datos)
        if destino is not None:
            resultado['destino'] = destino
            resultado['direccion_entrega'] = destino['direccion']
        return resultado

    if tipo == 'TRANSPORTISTA':
        servicio = obtener_servicio_transportista_activo(
            datos.get('servicio_transportista_id'), datos.get('transportista_id'))
        if not servicio:
            raise ValueError('Selecciona un servicio activo del transportista.')
        agencia = servicio['modalidad'].endswith('_AGENCIA')
        destino = None if agencia else _destino_checkout(usuario_id, datos, coordenadas=False)
        sucursal_id = datos.get('sucursal_destino_id') if agencia else None
        if agencia and not sucursal_id:
            raise ValueError('Selecciona la agencia de destino.')
        distrito = datos.get('distrito_destino_id') if agencia else destino['distrito_id']
        resultado = cotizar_envio_transportista(
            usuario_id, datos.get('transportista_id'), datos.get('servicio_transportista_id'),
            distrito, sucursal_id)
        if not resultado.get('ok'):
            raise ValueError(resultado['mensaje'])
        resultado['distrito_destino_id'] = distrito
        resultado['direccion_entrega'] = (resultado['sucursal_destino']['direccion'] if agencia
                                         else destino['direccion'])
        if destino:
            resultado['destino'] = destino
            # El esquema de envíos conserva el destino en un snapshot de 255 caracteres.
            if destino['referencia']:
                resultado['direccion_entrega'] = _texto_destino(
                    destino['direccion'] + ' | Ref: ' + destino['referencia'], 'La dirección con referencia', 5)
        return resultado
    raise ValueError('Selecciona una modalidad de entrega válida.')


def _huella_checkout(valor):
    import hashlib
    import json
    return hashlib.sha256(json.dumps(valor, sort_keys=True, default=str,
                                     separators=(',', ':')).encode()).hexdigest()


def _huella_carrito_entrega(usuario_id):
    from app.comercio.services import obtener_carrito_usuario
    carrito = obtener_carrito_usuario(usuario_id)
    if not carrito.get('items'):
        raise ValueError('El carrito está vacío.')
    return _huella_checkout(carrito)


def _firma_cotizacion():
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='checkout-entrega-v1')


def _huella_entrega(entrega):
    # La geometría no afecta a la tarifa. La distancia se compara a precisión de BD.
    contenido = {k: v for k, v in entrega.items() if k not in ('geometria', 'cotizacion_token')}
    if entrega.get('tipo') == 'DELIVERY_LOCAL':
        # El destino puede completarse después de cotizar: se protegen
        # únicamente los datos de costo. La dirección se valida al guardar.
        contenido = {k: contenido[k] for k in (
            'tipo', 'tarifa_delivery_id', 'distancia_km', 'peso_kg',
            'subtotal_productos', 'costo_entrega', 'envio_gratis') if k in contenido}
    if 'distancia_km' in contenido:
        contenido['distancia_km'] = str(_dinero(contenido['distancia_km']))
    return _huella_checkout(contenido)


def cotizar_entrega_checkout(usuario_id, datos):
    """Cotización de 15 minutos vinculada al usuario, carrito y destino."""
    try:
        huella = _huella_carrito_entrega(usuario_id)
        entrega = _preparar_entrega_checkout(usuario_id, datos)
        if huella != _huella_carrito_entrega(usuario_id):
            raise ValueError('El carrito cambió. Vuelve a cotizar.')
        entrega['cotizacion_token'] = _firma_cotizacion().dumps({
            'usuario': usuario_id, 'carrito': huella, 'entrega': _huella_entrega(entrega)})
        return entrega
    except (ValueError, TypeError, InvalidOperation) as error:
        return {'ok': False, 'mensaje': str(error)}


def validar_entrega_confirmacion(usuario_id, datos):
    from itsdangerous import BadSignature
    try:
        if datos.get('tipo_entrega') == 'RECOJO_LOCAL':
            return _preparar_entrega_checkout(usuario_id, datos)
        token = datos.get('cotizacion_token')
        if not isinstance(token, str) or not token:
            raise ValueError('Primero debes cotizar la entrega.')
        firma = _firma_cotizacion().loads(token, max_age=900)
        if firma.get('usuario') != usuario_id or firma.get('carrito') != _huella_carrito_entrega(usuario_id):
            raise ValueError('La cotización no corresponde a tu carrito actual.')
        entrega = _preparar_entrega_checkout(usuario_id, datos)
        if firma.get('entrega') != _huella_entrega(entrega):
            raise ValueError('El destino o la tarifa cambió. Vuelve a cotizar.')
        if firma.get('carrito') != _huella_carrito_entrega(usuario_id):
            raise ValueError('El carrito cambió. Vuelve a cotizar.')
        if datos.get('tipo_entrega') == 'DELIVERY_LOCAL' and not entrega.get('destino'):
            raise ValueError('Confirma tu dirección de entrega antes de continuar.')
        return entrega
    except BadSignature:
        return {'ok': False, 'mensaje': 'La cotización venció o no es válida. Vuelve a cotizar.'}
    except (ValueError, TypeError, InvalidOperation) as error:
        return {'ok': False, 'mensaje': str(error)}


def crear_entrega_pedido(pedido_id, usuario_id, entrega):
    return guardar_entrega_checkout(pedido_id, usuario_id, entrega)


def compensar_entrega_pedido(pedido_id, usuario_id):
    return cancelar_entrega_checkout(pedido_id, usuario_id)


# ============================================================
# BLOQUE 2 — OPERACIÓN DE ENTREGAS Y FINALIZACIÓN DE PEDIDOS
# ============================================================
#
# El frontend nunca decide estados: las rutas representan ACCIONES
# (listo, programar, asignar, iniciar, confirmar, incidencia) y este
# Service valida rol, modalidad, secuencia y coherencia antes de
# coordinar escrituras con UN solo commit entre Comercio y Operaciones.
#
# COMPLETADO es el único estado terminal comercial: se alcanza de forma
# automática cuando entrega, pago y trazabilidad quedan confirmados.
# ============================================================

import uuid as _uuid

import bcrypt as _bcrypt

from app.operaciones import repositories as _repos
from app.operaciones.codigos_cliente import (
    cifrar_codigo as _cifrar_codigo_cliente,
    descifrar_codigo as _descifrar_codigo_cliente,
    generar_codigo as _generar_codigo_cliente,
    verificar_codigo as _verificar_codigo_cliente,
)
from app.comercio.pedido_states import ESTADO_COMPLETADO
from app.shared.unit_of_work import UnidadTrabajo
from app.shared.validators import (
    validar_correo,
    validar_password,
    validar_nombre,
    validar_telefono_peru,
    normalizar_telefono,
)

ROLES_OPERACION_ENTREGAS = frozenset({
    "GERENTE",
    "ADMINISTRADOR",
    "PEDIDOS_LOGISTICA",
})

ROLES_CONFIRMACION_ENTREGA = frozenset({
    "GERENTE",
    "ADMINISTRADOR",
    "PEDIDOS_LOGISTICA",
    "REPARTIDOR",
})

TRANSICIONES_ENTREGA = {
    "EN_PREPARACION": {"LISTO", "LISTO_PARA_RECOJO", "CANCELADO", "INCIDENCIA"},
    "LISTO": {"PROGRAMADO", "CANCELADO", "INCIDENCIA"},
    "LISTO_PARA_RECOJO": {"ENTREGADO", "CANCELADO", "INCIDENCIA"},
    "PROGRAMADO": {"EN_TRANSITO", "ENTREGADO", "CANCELADO", "INCIDENCIA"},
    "EN_TRANSITO": {"ENTREGADO", "CANCELADO", "INCIDENCIA"},
    "INCIDENCIA": {"CANCELADO"},
}

ESTADOS_ENTREGA_PENDIENTES_CODIGO = {
    "LISTO", "LISTO_PARA_RECOJO", "PROGRAMADO", "EN_TRANSITO",
}

ETIQUETAS_ASIGNACION = {
    "ASIGNADA": "Asignada",
    "ACEPTADA": "Aceptada",
    "REASIGNADA": "Reasignada",
    "FINALIZADA": "Finalizada",
    "CANCELADA": "Cancelada",
}

ETIQUETAS_ENVIO = {
    "PENDIENTE_DESPACHO": "Pendiente de despacho",
    "ENTREGADO_TRANSPORTISTA": "Entregado al transportista",
    "DESPACHADO": "Despachado",
    "EN_TRANSITO": "En tránsito",
    "EN_AGENCIA_DESTINO": "En agencia destino",
    "EN_REPARTO": "En reparto",
    "ENTREGADO": "Entregado",
    "INCIDENCIA": "Incidencia",
    "CANCELADO": "Cancelado",
}

TRANSICIONES_ENVIO = {
    "PENDIENTE_DESPACHO": {"ENTREGADO_TRANSPORTISTA", "INCIDENCIA", "CANCELADO"},
    "ENTREGADO_TRANSPORTISTA": {"DESPACHADO", "INCIDENCIA", "CANCELADO"},
    "DESPACHADO": {"EN_TRANSITO", "INCIDENCIA", "CANCELADO"},
    "EN_TRANSITO": {"EN_AGENCIA_DESTINO", "EN_REPARTO", "INCIDENCIA", "CANCELADO"},
    "EN_AGENCIA_DESTINO": {"EN_REPARTO", "INCIDENCIA", "CANCELADO"},
    "EN_REPARTO": {"ENTREGADO", "INCIDENCIA", "CANCELADO"},
    "INCIDENCIA": {"DESPACHADO", "EN_TRANSITO", "EN_REPARTO", "ENTREGADO", "CANCELADO"},
}

ESTADOS_ENVIO_DESCRIPCION = {
    "ENTREGADO_TRANSPORTISTA": "El pedido fue recibido por el transportista.",
    "DESPACHADO": "El envío fue despachado hacia el destino.",
    "EN_TRANSITO": "El envío se encuentra en tránsito.",
    "EN_AGENCIA_DESTINO": "El envío llegó a la agencia de destino.",
    "EN_REPARTO": "El envío está en reparto dentro del destino.",
    "ENTREGADO": "El envío fue entregado al destinatario.",
}


class ReglaOperativaError(Exception):
    """Error de negocio seguro para mostrar en la operativa real."""


def _roles_normalizados(roles):
    return {str(rol).strip().upper() for rol in (roles or [])}


def _puede_operar_entregas(roles):
    return bool(_roles_normalizados(roles) & ROLES_OPERACION_ENTREGAS)


def _puede_confirmar_entrega(roles):
    return bool(_roles_normalizados(roles) & ROLES_CONFIRMACION_ENTREGA)


def _transicion_habilitada(anterior, nuevo):
    return nuevo in TRANSICIONES_ENTREGA.get(
        str(anterior or "").upper(), set()
    )


def _transicion_envio_habilitada(anterior, nuevo):
    return nuevo in TRANSICIONES_ENVIO.get(
        str(anterior or "").upper(), set()
    )


def _valores_entrega_bloqueo(contexto, roles, accion):
    """Valida identidad del contexto bloqueado y permisos del actor.

    `accion == "confirmar_repartidor"` exige que el actor tenga asignada
    y ACEPTADA la entrega, además de las validaciones comunes de contexto.
    """
    if not contexto:
        raise ReglaOperativaError("La entrega solicitada no existe.")
    if not contexto["entrega"] or not contexto["pedido"]:
        raise ReglaOperativaError("No se encontró la entrega o su pedido.")
    if contexto["incidencias_activas"] and accion not in ("resolver", "cancelar"):
        raise ReglaOperativaError(
            "La entrega tiene una incidencia abierta; resuélvela primero."
        )
    if accion == "confirmar_repartidor":
        return
    if not _puede_operar_entregas(roles):
        raise ReglaOperativaError("No tienes permisos para esta operación.")


def marcar_entrega_listo(actor_id, roles, entrega_id):
    """Marca la entrega preparada (LISTO) y emite el código de delivery."""
    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(contexto, roles, "listo")
        entrega = contexto["entrega"]
        destino = "LISTO"
        if not _transicion_habilitada(entrega["estado"], destino):
            raise ReglaOperativaError(
                "La entrega ya no se encuentra en un estado que permita marcarla lista."
            )
        if entrega["tipo_entrega"] == "RECOJO_LOCAL":
            raise ReglaOperativaError(
                "El recojo en local usa 'confirmar recojo disponible'."
            )

        _repos.actualizar_estado_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], destino,
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], destino, actor_id,
            "Pedido preparado; entrega lista para continuar.",
        )
        codigo = None
        if entrega["tipo_entrega"] == "DELIVERY_LOCAL":
            codigo = _generar_codigo_cliente()
            _repos.actualizar_codigo_cliente_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                _cifrar_codigo_cliente(codigo),
            )
        unidad.confirmar()

    return {"ok": True, "estado": destino, "codigo_cliente": codigo}


def confirmar_recojo_disponible(actor_id, roles, entrega_id):
    """Activa el recojo: LISTO_PARA_RECOJO, notificación y código."""
    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(contexto, roles, "recojo")
        entrega = contexto["entrega"]
        if entrega["tipo_entrega"] != "RECOJO_LOCAL":
            raise ReglaOperativaError(
                "Solo las entregas de recojo local usan esta acción."
            )
        destino = "LISTO_PARA_RECOJO"
        if not _transicion_habilitada(entrega["estado"], destino):
            raise ReglaOperativaError(
                "El recojo ya no se encuentra en un estado que permita activarlo."
            )
        _repos.actualizar_estado_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], destino,
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], destino, actor_id,
            "Recojo notificado y disponible en el punto seleccionado.",
        )
        _repos.actualizar_notificado_recojo(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        codigo = _generar_codigo_cliente()
        _repos.actualizar_codigo_cliente_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            _cifrar_codigo_cliente(codigo),
        )
        unidad.confirmar()

    return {"ok": True, "estado": destino, "codigo_cliente": codigo}


def programar_entrega(actor_id, roles, entrega_id, fecha_programada):
    """Programa la fecha de la entrega para delivery o transportista."""
    if isinstance(fecha_programada, str):
        fecha_programada = _fecha_iso_operativa(fecha_programada)
    if not fecha_programada:
        raise ReglaOperativaError("Selecciona una fecha de programación.")

    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(contexto, roles, "programar")
        entrega = contexto["entrega"]
        if entrega["tipo_entrega"] == "RECOJO_LOCAL":
            raise ReglaOperativaError(
                "El recojo en local no requiere programación de reparto."
            )
        destino = "PROGRAMADO"
        if not _transicion_habilitada(entrega["estado"], destino):
            raise ReglaOperativaError(
                "La entrega debe estar lista antes de programarse."
            )
        _repos.actualizar_estado_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], destino, fecha_programada=fecha_programada,
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], destino, actor_id,
            f"Entrega programada para el {fecha_programada.strftime('%d/%m/%Y %H:%M')}.",
        )
        unidad.confirmar()

    return {"ok": True, "estado": destino, "fecha_programada": fecha_programada}


def _fecha_iso_operativa(valor):
    from datetime import datetime as _datetime
    try:
        return _datetime.strptime(str(valor).strip(), "%Y-%m-%dT%H:%M")
    except ValueError:
        pass
    try:
        return _datetime.strptime(str(valor).strip(), "%Y-%m-%d %H:%M")
    except ValueError as error:
        raise ReglaOperativaError(
            "La fecha de programación no es válida."
        ) from error


def asignar_repartidor(actor_id, roles, entrega_id, repartidor_id):
    """Asigna el reparto a un repartidor ACTIVO y con disponibilidad real."""
    if not repartidor_id:
        raise ReglaOperativaError("Selecciona un repartidor.")
    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(contexto, roles, "asignar")
        entrega = contexto["entrega"]
        if entrega["tipo_entrega"] != "DELIVERY_LOCAL":
            raise ReglaOperativaError(
                "Solo los deliveries locales se asignan a repartidores."
            )
        if entrega["estado"] not in {"PROGRAMADO", "EN_TRANSITO"}:
            raise ReglaOperativaError(
                "La entrega debe estar programada antes de asignar reparto."
            )
        repartidor = _repos.obtener_repartidor_activo(
            unidad.conexion, unidad.esquemas, repartidor_id
        )
        if not repartidor:
            raise ReglaOperativaError(
                "El repartidor no existe o no está activo."
            )
        # Evita la doble asignación operativa del mismo repartidor.
        asignaciones = _repos.obtener_asignaciones_activas_repartidor(
            unidad.conexion, unidad.esquemas, repartidor_id
        )
        for asignacion in asignaciones:
            if asignacion["entrega_id"] == entrega_id:
                raise ReglaOperativaError(
                    "Este repartidor ya tiene asignada la entrega."
                )
        if repartidor["disponible"] == 0 and asignaciones:
            raise ReglaOperativaError(
                "El repartidor se encuentra ocupado con otro reparto."
            )

        _repos.crear_asignacion_repartidor(
            unidad.conexion, unidad.esquemas, str(_uuid.uuid4()),
            entrega_id, repartidor_id, actor_id,
        )
        _repos.actualizar_disponibilidad_repartidor(
            unidad.conexion, unidad.esquemas, repartidor_id, False
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], entrega["estado"], actor_id,
            "Repartidor asignado al reparto.",
        )
        unidad.confirmar()

    return {"ok": True, "accion": "ASIGNADA"}


def aceptar_asignacion(actor_id, entrega_id):
    """El repartidor autenticado acepta ÚNICAMENTE su propia asignación."""
    if not actor_id:
        raise ReglaOperativaError("Tu sesión de repartidor no es válida.")
    with UnidadTrabajo() as unidad:
        repartidor = _repos.obtener_repartidor_por_usuario(
            unidad.conexion, unidad.esquemas, actor_id
        )
        if not repartidor:
            raise ReglaOperativaError("Tu usuario no es un repartidor activo.")
        asignacion = _repos.obtener_asignacion_repartidor_entrega(
            unidad.conexion, unidad.esquemas, repartidor["id"], entrega_id
        )
        if not asignacion:
            raise ReglaOperativaError(
                "La entrega no te está asignada o ya fue procesada."
            )
        if asignacion["estado"] == "ACEPTADA":
            raise ReglaOperativaError("Ya aceptaste esta asignación.")
        if asignacion["estado"] != "ASIGNADA":
            raise ReglaOperativaError(
                "La asignación no se encuentra en estado ASIGNADA."
            )
        _repos.actualizar_asignacion_estado(
            unidad.conexion, unidad.esquemas, asignacion["id"],
            "ACEPTADA", aceptar=True,
        )
        unidad.confirmar()
    return {"ok": True, "accion": "ACEPTADA"}


def iniciar_reparto(actor_id, roles, entrega_id):
    """Pone la entrega EN_TRANSITO con evidencia de asignación aceptada."""
    roles_ok = _roles_normalizados(roles)
    es_repartidor = "REPARTIDOR" in roles_ok
    if not es_repartidor and not _puede_operar_entregas(roles_ok):
        raise ReglaOperativaError("No tienes permisos para iniciar el reparto.")

    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(
            contexto, roles_ok,
            "confirmar_repartidor" if es_repartidor else "iniciar",
        )
        entrega = contexto["entrega"]
        if entrega["tipo_entrega"] != "DELIVERY_LOCAL":
            raise ReglaOperativaError(
                "Solo los deliveries locales inician reparto presencial."
            )
        destino = "EN_TRANSITO"
        if not _transicion_habilitada(entrega["estado"], destino):
            raise ReglaOperativaError(
                "La entrega debe estar programada para iniciar el reparto."
            )

        asignacion_activa = None
        if es_repartidor:
            repartidor = _repos.obtener_repartidor_por_usuario(
                unidad.conexion, unidad.esquemas, actor_id
            )
            if not repartidor:
                raise ReglaOperativaError("Tu usuario no es repartidor activo.")
            asignacion_activa = _repos.obtener_asignacion_repartidor_entrega(
                unidad.conexion, unidad.esquemas, repartidor["id"], entrega_id
            )
            if not asignacion_activa:
                raise ReglaOperativaError(
                    "La entrega no te está asignada y no puedes iniciarla."
                )
            if asignacion_activa["estado"] != "ACEPTADA":
                raise ReglaOperativaError(
                    "Acepta primero la asignación para iniciar el reparto."
                )
        else:
            asignacion_activa = _repos.obtener_asignacion_activa_entrega(
                unidad.conexion, unidad.esquemas, entrega_id
            )
            if not asignacion_activa:
                raise ReglaOperativaError(
                    "La entrega requiere una asignación activa para iniciarse."
                )

        _repos.actualizar_estado_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], destino,
        )
        _repos.actualizar_iniciado_delivery(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], destino, actor_id,
            "Reparto en curso hacia el destino.",
        )
        unidad.confirmar()

    return {"ok": True, "estado": destino}


def confirmar_entrega(actor_id, roles, entrega_id, codigo_cliente=None):
    """Confirma la entrega, cobra si corresponde y evalúa COMPLETADO."""
    roles_ok = _roles_normalizados(roles)
    es_repartidor = "REPARTIDOR" in roles_ok
    if not es_repartidor and not _puede_confirmar_entrega(roles_ok):
        raise ReglaOperativaError("No tienes permisos para confirmar la entrega.")

    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        if not contexto:
            raise ReglaOperativaError("La entrega solicitada no existe.")
        if es_repartidor and not _puede_operar_entregas(roles_ok):
            repartidor = _repos.obtener_repartidor_por_usuario(
                unidad.conexion, unidad.esquemas, actor_id
            )
            if not repartidor:
                raise ReglaOperativaError("Tu usuario no es repartidor activo.")
            asignacion = _repos.obtener_asignacion_repartidor_entrega(
                unidad.conexion, unidad.esquemas,
                repartidor["id"], entrega_id,
            )
            if not asignacion or asignacion["estado"] != "ACEPTADA":
                raise ReglaOperativaError(
                    "La entrega no te está asignada y aceptada."
                )
        _valores_entrega_bloqueo(
            contexto, roles_ok,
            "confirmar_repartidor" if es_repartidor else "confirmar",
        )
        entrega = contexto["entrega"]
        if entrega["tipo_entrega"] != "DELIVERY_LOCAL":
            raise ReglaOperativaError(
                "Este flujo confirma deliveries locales; usa la acción de recojo o transportista."
            )
        if entrega["estado"] != "EN_TRANSITO":
            raise ReglaOperativaError(
                "La entrega debe estar en tránsito para confirmarse."
            )
        if not _verificar_codigo_cliente(
            entrega["codigo_cliente_token"], codigo_cliente
        ):
            raise ReglaOperativaError("El código de entrega no es válido.")

        pago = contexto["pago"]
        _gestionar_cobro(
            unidad, pago, "CONTRA_ENTREGA", entrega["tipo_entrega"],
            actor_id, "Cobrado contra entrega al recibir el pedido.",
        )

        _repos.actualizar_estado_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], "ENTREGADO", completar=True,
        )
        _repos.actualizar_entregado_delivery(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        repartidores_finalizados = _repos.finalizar_asignaciones_entrega(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        for repartidor_id in repartidores_finalizados:
            _repos.actualizar_disponibilidad_repartidor(
                unidad.conexion, unidad.esquemas, repartidor_id, True
            )
        _repos.limpiar_codigo_cliente_entrega(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            "EN_TRANSITO", "ENTREGADO", actor_id,
            "Entrega confirmada en el destino.",
        )
        _evaluar_finalizacion_pedido(
            unidad, contexto["pedido"]["id"], actor_id,
            motivo="Entrega confirmada.",
        )
        unidad.confirmar()

    return {"ok": True, "estado": "ENTREGADO"}


def confirmar_recojo(actor_id, roles, entrega_id, codigo_cliente=None):
    """Confirma el recojo en el punto, cobra si corresponde y evalúa."""
    if not _puede_operar_entregas(_roles_normalizados(roles)):
        raise ReglaOperativaError("Solo el equipo operativo confirma un recojo.")

    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(contexto, roles, "confirmar")
        entrega = contexto["entrega"]
        if entrega["tipo_entrega"] != "RECOJO_LOCAL":
            raise ReglaOperativaError(
                "Este flujo confirma entregas de recojo en local."
            )
        if entrega["estado"] != "LISTO_PARA_RECOJO":
            raise ReglaOperativaError(
                "El recojo debe estar listo en el punto antes de confirmarse."
            )
        if not _verificar_codigo_cliente(
            entrega["codigo_cliente_token"], codigo_cliente
        ):
            raise ReglaOperativaError("El código de recojo no es válido.")

        pago = contexto["pago"]
        _gestionar_cobro(
            unidad, pago, "PAGO_EN_LOCAL", entrega["tipo_entrega"],
            actor_id, "Pago efectuado en el punto de recojo.",
        )

        _repos.actualizar_estado_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], "ENTREGADO", completar=True,
        )
        _repos.actualizar_recogido_recojo(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _repos.limpiar_codigo_cliente_entrega(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            "LISTO_PARA_RECOJO", "ENTREGADO", actor_id,
            "Recojo confirmado en el punto de recojo.",
        )
        _evaluar_finalizacion_pedido(
            unidad, contexto["pedido"]["id"], actor_id,
            motivo="Recojo confirmado.",
        )
        unidad.confirmar()

    return {"ok": True, "estado": "ENTREGADO"}


def _gestionar_cobro(unidad, pago, modalidad_esperada, tipo_entrega,
                     actor_id, observacion):
    """Marca el pago del flujo presencial dentro de la misma transacción."""
    if not pago:
        raise ReglaOperativaError("El pedido no tiene un pago registrado.")
    modalidad = str(pago.get("modalidad") or "").upper()
    estado = str(pago.get("estado") or "").upper()

    if modalidad == "ANTICIPADO":
        if estado != "PAGADO":
            raise ReglaOperativaError(
                "El pago anticipado debe estar pagado antes de cerrar la entrega."
            )
        _repos.insertar_ingreso_caja_desde_pago(
            unidad.conexion, unidad.esquemas, pago
        )
        return
    if modalidad == modalidad_esperada:
        if estado == "PAGADO":
            _repos.insertar_ingreso_caja_desde_pago(
                unidad.conexion, unidad.esquemas, pago
            )
            return
        if estado != "PENDIENTE":
            raise ReglaOperativaError(
                "El estado actual del pago no permite concluir la operación."
            )
        if not _repos.confirmar_pago_operativo(
            unidad.conexion, unidad.esquemas, pago["id"], estado,
            actor_id, observacion,
        ):
            raise ReglaOperativaError(
                "El pago cambió mientras se confirmaba la entrega."
            )
        _repos.insertar_ingreso_caja_desde_pago(
            unidad.conexion, unidad.esquemas, pago
        )
        return
    raise ReglaOperativaError(
        "La modalidad de pago no es aplicable a esta forma de entrega."
    )


def _evaluar_finalizacion_pedido(unidad, pedido_id, actor_id, motivo):
    """Cierra el pedido a COMPLETADO cuando la operación queda íntegra.

    Requiere (evidencia real):
    - pedido aún no terminal;
    - entrega ENTREGADO con completado_en;
    - pago PAGADO con pagado_en;
    - sin incidencias ABIERTA/EN_REVISION.
    """
    comercio = unidad.esquemas["comercio"]
    operaciones = unidad.esquemas["operaciones"]

    def _total(sql):
        with unidad.conexion.cursor() as cursor:
            cursor.execute(sql)
            return int(cursor.fetchone()["total"])

    pedido = cursor_pedido_estado(unidad, pedido_id)
    if not pedido:
        return False
    if pedido["estado"] in {"COMPLETADO", "CANCELADO"}:
        return True

    with unidad.conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT estado, completado_en
            FROM {operaciones}.entregas
            WHERE pedido_id = %s AND estado = 'ENTREGADO'
            AND completado_en IS NOT NULL LIMIT 1
            """,
            (pedido_id,),
        )
        entrega = _repos.fetchone_safe(cursor)
        cursor.execute(
            f"""
            SELECT estado, pagado_en
            FROM {operaciones}.pagos
            WHERE pedido_id = %s AND estado = 'PAGADO'
            AND pagado_en IS NOT NULL
            ORDER BY creado_en DESC LIMIT 1
            """,
            (pedido_id,),
        )
        pago = _repos.fetchone_safe(cursor)
        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM {operaciones}.incidencias_entrega AS i
            INNER JOIN {operaciones}.entregas AS e ON e.id = i.entrega_id
            WHERE e.pedido_id = %s AND i.estado IN ('ABIERTA', 'EN_REVISION')
            """,
            (pedido_id,),
        )
        incidencias = int(cursor.fetchone()["total"])

    if not entrega or not pago or incidencias:
        return False

    if not _repos.actualizar_pedido_completado(
        unidad.conexion, unidad.esquemas, pedido_id,
        pedido["estado"], actor_id, motivo,
    ):
        raise ReglaOperativaError(
            "El pedido cambió mientras se finalizaba; reintenta la operación."
        )

    # Bloque 4: al cerrar el pedido se crea la encuesta de satisfacción
    # PENDIENTE (idempotente). El enlace solo cuenta como invitación
    # efectiva cuando el cliente abre su pedido (service de Comercio).
    from app.encuestas.services import crear_encuesta_tras_completar
    crear_encuesta_tras_completar(unidad, pedido_id)

    return True


def cursor_pedido_estado(unidad, pedido_id):
    """Lee el estado del pedido dentro de la transacción en curso."""
    comercio = unidad.esquemas["comercio"]
    with unidad.conexion.cursor() as cursor:
        cursor.execute(
            f"SELECT id, estado FROM {comercio}.pedidos WHERE id = %s LIMIT 1",
            (pedido_id,),
        )
        return _repos.fetchone_safe(cursor)


def confirmar_pago_anticipado(actor_id, roles, pedido_id):
    """Confirma administrativamente un pago anticipado pendiente."""
    if not _puede_operar_entregas(_roles_normalizados(roles)):
        raise ReglaOperativaError("Solo el equipo operativo confirma pagos.")
    with UnidadTrabajo() as unidad:
        operaciones = unidad.esquemas["operaciones"]
        with unidad.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, pedido_id, modalidad, estado, monto, moneda,
                       metodo_pago_id, pagado_en
                FROM {operaciones}.pagos
                WHERE pedido_id = %s
                ORDER BY creado_en DESC LIMIT 1 FOR UPDATE
                """,
                (pedido_id,),
            )
            pago = _repos.fetchone_safe(cursor)
        if not pago:
            raise ReglaOperativaError("El pedido no tiene un pago registrado.")
        if pago["modalidad"] != "ANTICIPADO":
            raise ReglaOperativaError(
                "Solo los pagos anticipados se confirman con esta acción."
            )
        if pago["estado"] == "PAGADO":
            _repos.insertar_ingreso_caja_desde_pago(
                unidad.conexion, unidad.esquemas, pago
            )
            unidad.confirmar()
            return {"ok": True, "estado": "PAGADO"}
        if pago["estado"] != "PENDIENTE":
            raise ReglaOperativaError(
                "El estado actual del pago no permite confirmarlo."
            )
        if not _repos.confirmar_pago_operativo(
            unidad.conexion, unidad.esquemas, pago["id"], pago["estado"],
            actor_id, "Pago anticipado verificado por el equipo operativo.",
        ):
            raise ReglaOperativaError(
                "El pago cambió mientras se confirmaba."
            )
        _repos.insertar_ingreso_caja_desde_pago(
            unidad.conexion, unidad.esquemas, pago
        )
        unidad.confirmar()
    return {"ok": True, "estado": "PAGADO"}


def registrar_incidencia(actor_id, roles, entrega_id, tipo, descripcion):
    """Registra una incidencia y pone la entrega en INCIDENCIA."""
    if not _puede_operar_entregas(_roles_normalizados(roles)):
        raise ReglaOperativaError("No tienes permisos para registrar incidencias.")
    tipo = str(tipo or "").strip()[:80]
    descripcion = str(descripcion or "").strip()[:500]
    if not tipo:
        raise ReglaOperativaError("Indica el tipo de incidencia.")
    if len(descripcion) < 5:
        raise ReglaOperativaError("Describe la incidencia con detalle.")

    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(contexto, roles, "incidencia")
        entrega = contexto["entrega"]
        if entrega["estado"] in {"ENTREGADO", "CANCELADO"}:
            raise ReglaOperativaError(
                "No se puede abrir una incidencia sobre una entrega cerrada."
            )
        _repos.crear_incidencia_entrega(
            unidad.conexion, unidad.esquemas, str(_uuid.uuid4()),
            entrega_id, tipo, descripcion, actor_id,
        )
        if entrega["estado"] != "INCIDENCIA":
            _repos.actualizar_estado_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                entrega["estado"], "INCIDENCIA",
            )
            _repos.insertar_historial_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                entrega["estado"], "INCIDENCIA", actor_id,
                f"Incidencia registrada: {tipo}.",
            )
        unidad.confirmar()
    return {"ok": True, "accion": "INCIDENCIA"}


def resolver_incidencia(actor_id, roles, incidencia_id):
    """Resuelve la incidencia y restaura el estado previo de la entrega."""
    if not _puede_operar_entregas(_roles_normalizados(roles)):
        raise ReglaOperativaError("No tienes permisos para resolver incidencias.")
    with UnidadTrabajo() as unidad:
        incidencia = _repos.obtener_incidencia(
            unidad.conexion, unidad.esquemas, incidencia_id
        )
        if not incidencia:
            raise ReglaOperativaError("La incidencia no existe.")
        estado_anterior = _repos.obtener_estado_anterior_incidencia(
            unidad.conexion, unidad.esquemas, incidencia["entrega_id"]
        )
        if not _repos.resolver_incidencia_entrega(
            unidad.conexion, unidad.esquemas, incidencia_id, actor_id,
            estado_anterior, incidencia["entrega_id"],
        ):
            raise ReglaOperativaError(
                "La incidencia ya fue resuelta o cambió mientras se procesaba."
            )
        if estado_anterior:
            _repos.insertar_historial_entrega(
                unidad.conexion, unidad.esquemas, incidencia["entrega_id"],
                "INCIDENCIA", estado_anterior, actor_id,
                "Incidencia resuelta; la entrega continúa su operativa.",
            )
        unidad.confirmar()
    return {"ok": True, "accion": "RESUELTA"}


def cancelar_entrega(actor_id, roles, entrega_id, motivo):
    """Cancela la entrega, libera repartidores y registra la evidencia."""
    if not _puede_operar_entregas(_roles_normalizados(roles)):
        raise ReglaOperativaError("No tienes permisos para cancelar la entrega.")
    motivo = str(motivo or "").strip()[:500]
    if len(motivo) < 5:
        raise ReglaOperativaError("Indica el motivo de la cancelación.")

    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(contexto, roles, "cancelar")
        entrega = contexto["entrega"]
        if entrega["estado"] in {"ENTREGADO", "CANCELADO"}:
            raise ReglaOperativaError(
                "La entrega ya se encuentra cerrada."
            )
        repartidores_cancelados = _repos.cancelar_asignaciones_activas(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        for repartidor_id in repartidores_cancelados:
            _repos.actualizar_disponibilidad_repartidor(
                unidad.conexion, unidad.esquemas, repartidor_id, True
            )
        _repos.actualizar_estado_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], "CANCELADO",
        )
        _repos.limpiar_codigo_cliente_entrega(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], "CANCELADO", actor_id,
            f"Entrega cancelada: {motivo}.",
        )
        unidad.confirmar()
    return {"ok": True, "estado": "CANCELADO"}


def actualizar_estado_envio(actor_id, roles, entrega_id, estado_nuevo,
                            codigo_seguimiento=None, url_seguimiento=None,
                            ubicacion_texto=None):
    """Avanza el envío trasportista y sincroniza la entrega al finalizar."""
    if not _puede_operar_entregas(_roles_normalizados(roles)):
        raise ReglaOperativaError("No tienes permisos para operar el envío.")
    estado_nuevo = str(estado_nuevo or "").strip().upper()
    if estado_nuevo not in TRANSICIONES_ENVIO:
        raise ReglaOperativaError("El estado del envío no es válido.")

    with UnidadTrabajo() as unidad:
        contexto = _repos.bloquear_entrega_operativa(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        _valores_entrega_bloqueo(contexto, roles, "envio")
        entrega = contexto["entrega"]
        if entrega["tipo_entrega"] != "TRANSPORTISTA_ASOCIADO":
            raise ReglaOperativaError(
                "Solo los envíos con transportista asociado usan seguimiento."
            )
        envio = _repos.obtener_envio_por_entrega(
            unidad.conexion, unidad.esquemas, entrega_id
        )
        if not envio:
            raise ReglaOperativaError(
                "La entrega no tiene envío trasportista registrado."
            )
        if not _transicion_envio_habilitada(envio["estado"], estado_nuevo):
            raise ReglaOperativaError(
                "La transición del envío no está habilitada."
            )

        _repos.actualizar_envio_estado(
            unidad.conexion, unidad.esquemas, envio["id"], envio["estado"],
            estado_nuevo, codigo_seguimiento=codigo_seguimiento,
            url_seguimiento=url_seguimiento,
            despachar=(estado_nuevo == "DESPACHADO"),
            entregar=(estado_nuevo == "ENTREGADO"),
        )
        _repos.registrar_evento_seguimiento(
            unidad.conexion, unidad.esquemas, envio["id"], estado_nuevo,
            ESTADOS_ENVIO_DESCRIPCION.get(estado_nuevo, ""),
            ubicacion_texto=ubicacion_texto,
        )
        _repos.insertar_historial_entrega(
            unidad.conexion, unidad.esquemas, entrega_id,
            entrega["estado"], entrega["estado"], actor_id,
            f"Envío trasportista: {ETIQUETAS_ENVIO.get(estado_nuevo, estado_nuevo)}.",
        )

        if estado_nuevo == "ENTREGADO":
            _repos.actualizar_estado_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                entrega["estado"], "ENTREGADO", completar=True,
            )
            _repos.insertar_historial_entrega(
                unidad.conexion, unidad.esquemas, entrega_id,
                entrega["estado"], "ENTREGADO", actor_id,
                "Envío entregado por el transportista.",
            )
            _evaluar_finalizacion_pedido(
                unidad, contexto["pedido"]["id"], actor_id,
                motivo="Envío trasportista entregado.",
            )
        unidad.confirmar()
    return {"ok": True, "estado_envio": estado_nuevo}


def registrar_repartidor(actor_id, roles, correo, password, nombres,
                         apellido_paterno, apellido_materno,
                         telefono, dni=None):
    """Registra un repartidor real (usuario + rol + planilla) atómicamente."""
    if not _puede_operar_entregas(_roles_normalizados(roles)):
        raise ReglaOperativaError("No tienes permisos para registrar repartidores.")

    correo = (correo or "").strip().lower()
    nombres = (nombres or "").strip()
    apellido_paterno = (apellido_paterno or "").strip()
    apellido_materno = (apellido_materno or "").strip() or None
    telefono = normalizar_telefono(telefono)
    dni = (dni or "").strip() or None

    valido, mensaje = validar_correo(correo)
    if not valido:
        raise ReglaOperativaError(mensaje)
    valido, mensaje = validar_password(password)
    if not valido:
        raise ReglaOperativaError(mensaje)
    valido, mensaje = validar_nombre(nombres, "Los nombres", obligatorio=True)
    if not valido:
        raise ReglaOperativaError(mensaje)
    valido, mensaje = validar_nombre(
        apellido_paterno, "El apellido paterno", obligatorio=True
    )
    if not valido:
        raise ReglaOperativaError(mensaje)
    valido, mensaje = validar_nombre(
        apellido_materno, "El apellido materno", obligatorio=False
    )
    if not valido:
        raise ReglaOperativaError(mensaje)
    valido, mensaje = validar_telefono_peru(telefono, obligatorio=True)
    if not valido:
        raise ReglaOperativaError(mensaje)

    with UnidadTrabajo() as unidad:
        if _repos.buscar_usuario_por_correo_transaccion(
            unidad.conexion, unidad.esquemas, correo
        ):
            raise ReglaOperativaError(
                "Ya existe una cuenta registrada con ese correo."
            )
        rol = _repos.obtener_rol_por_codigo(
            unidad.conexion, unidad.esquemas, "REPARTIDOR"
        )
        if not rol:
            raise ReglaOperativaError(
                "El rol REPARTIDOR no está configurado en identidad."
            )
        usuario_id = str(_uuid.uuid4())
        perfil_id = str(_uuid.uuid4())
        repartidor_id = str(_uuid.uuid4())
        password_hash = _bcrypt.hashpw(
            password.encode("utf-8"), _bcrypt.gensalt()
        ).decode("utf-8")
        _repos.crear_usuario_perfil(
            unidad.conexion, unidad.esquemas, usuario_id, perfil_id,
            correo, password_hash, nombres, apellido_paterno,
            apellido_materno, dni, telefono,
        )
        _repos.asignar_rol_usuario(
            unidad.conexion, unidad.esquemas, usuario_id, rol["id"], actor_id
        )
        _repos.crear_repartidor(
            unidad.conexion, unidad.esquemas, repartidor_id, usuario_id
        )
        unidad.confirmar()

    return {
        "ok": True,
        "mensaje": "Repartidor registrado correctamente.",
        "repartidor_id": repartidor_id,
        "usuario_id": usuario_id,
    }


def listar_entregas_operativa(estado=None, tipo=None, busqueda=None):
    """Listado operativo real de entregas (solo lectura, sin commit)."""
    estado = str(estado or "").strip().upper() or None
    tipo = str(tipo or "").strip().upper() or None
    busqueda = str(busqueda or "").strip()[:100] or None
    if estado and estado not in ESTADOS_ENTREGA_PENDIENTES_CODIGO | {
        "PENDIENTE", "EN_PREPARACION", "ENTREGADO", "CANCELADO", "INCIDENCIA",
    }:
        raise ReglaOperativaError("El filtro de estado no es válido.")
    if tipo and tipo not in {
        "RECOJO_LOCAL", "DELIVERY_LOCAL", "TRANSPORTISTA_ASOCIADO",
    }:
        raise ReglaOperativaError("El filtro de tipo no es válido.")

    with UnidadTrabajo() as unidad:
        entregas = _repos.listar_entregas_admin(
            unidad.conexion, unidad.esquemas,
            estado=estado, tipo=tipo, busqueda=busqueda,
        )
    for entrega in entregas:
        entrega["estado_label"] = _etiqueta_estado_entrega(
            entrega["estado"]
        )
        entrega["tipo_label"] = _etiqueta_tipo_entrega(
            entrega["tipo_entrega"]
        )
        entrega["pago_estado_label"] = _etiqueta_pago(
            entrega["pago_estado"]
        )
    return entregas


def obtener_detalle_entrega_operativa(entrega_id):
    """Detalle operativo completo de una entrega (solo lectura)."""
    if not entrega_id:
        return None
    with UnidadTrabajo() as unidad:
        return _repos.obtener_entrega_admin(
            unidad.conexion, unidad.esquemas, entrega_id
        )


def listar_repartidores_operativa():
    """Lista la planilla real de repartidores registrados."""
    with UnidadTrabajo() as unidad:
        repartidores = _repos.listar_repartidores(
            unidad.conexion, unidad.esquemas
        )
    return repartidores


def _etiqueta_estado_entrega(estado):
    return {
        "PENDIENTE": "Pendiente",
        "EN_PREPARACION": "En preparación",
        "LISTO": "Listo",
        "PROGRAMADO": "Programado",
        "EN_TRANSITO": "En tránsito",
        "LISTO_PARA_RECOJO": "Listo para recojo",
        "ENTREGADO": "Entregado",
        "CANCELADO": "Cancelado",
        "INCIDENCIA": "Incidencia",
    }.get(str(estado or "").upper(), str(estado or "—") or "—")


def _etiqueta_tipo_entrega(tipo):
    return {
        "RECOJO_LOCAL": "Recojo en local",
        "DELIVERY_LOCAL": "Delivery local",
        "TRANSPORTISTA_ASOCIADO": "Transportista asociado",
    }.get(str(tipo or "").upper(), str(tipo or "—") or "—")


def _etiqueta_pago(estado):
    return {
        "PENDIENTE": "Pendiente",
        "EN_REVISION": "En revisión",
        "PAGADO": "Pagado",
        "RECHAZADO": "Rechazado",
        "CANCELADO": "Cancelado",
        "REEMBOLSADO": "Reembolsado",
    }.get(str(estado or "").upper(), str(estado or "—") or "—")


# ============================================================
# REPARTIDOR: solo sus propias asignaciones
# ============================================================

def _repartidor_de_sesion(unidad, usuario_id):
    repartidor = _repos.obtener_repartidor_por_usuario(
        unidad.conexion, unidad.esquemas, usuario_id
    )
    if not repartidor:
        raise ReglaOperativaError("Tu usuario no es un repartidor activo.")
    return repartidor


def listar_repartos_repartidor(usuario_id):
    """Asignaciones actives del repartidor autenticado."""
    with UnidadTrabajo() as unidad:
        repartidor = _repartidor_de_sesion(unidad, usuario_id)
        asignaciones = _repos.listar_asignaciones_repartidor(
            unidad.conexion, unidad.esquemas, repartidor["id"]
        )
        historial = _repos.listar_asignaciones_repartidor_historial(
            unidad.conexion, unidad.esquemas, repartidor["id"]
        )
    for item in asignaciones:
        item["entrega_estado_label"] = _etiqueta_estado_entrega(
            item["entrega_estado"]
        )
        item["asignacion_estado_label"] = ETIQUETAS_ASIGNACION.get(
            item["asignacion_estado"], item["asignacion_estado"]
        )
    return {"activas": asignaciones, "historial": historial}


def obtener_detalle_reparto_repartidor(usuario_id, entrega_id):
    """Detalle de UNA entrega asignada al repartidor autenticado."""
    with UnidadTrabajo() as unidad:
        repartidor = _repartidor_de_sesion(unidad, usuario_id)
        detalle = _repos.obtener_detalle_asignacion(
            unidad.conexion, unidad.esquemas, repartidor["id"], entrega_id
        )
        if not detalle:
            return None
        detalle["entrega_estado_label"] = _etiqueta_estado_entrega(
            detalle["entrega_estado"]
        )
        detalle["asignacion_estado_label"] = ETIQUETAS_ASIGNACION.get(
            detalle["asignacion_estado"], detalle["asignacion_estado"]
        )
        return detalle
