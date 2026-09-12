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
