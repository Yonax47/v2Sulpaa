"""
Servicios del módulo Comercio de SULPAA V2.

Aquí vive la lógica comercial:

- catálogo;
- stock;
- packs;
- packs personalizados;
- validaciones;
- carrito.
"""

from collections import defaultdict

from app.comercio.repositories import (
    obtener_variantes_comerciales_tienda,
    obtener_variantes_330ml_tienda,
    obtener_packs_comerciales_tienda,
    obtener_componentes_packs,
    obtener_reglas_packs,
    obtener_variantes_permitidas_packs,
    obtener_articulo_venta_por_id,
    obtener_detalles_carrito_usuario,
    obtener_composiciones_carrito,
    guardar_item_carrito,
    actualizar_cantidad_detalle_carrito,
    eliminar_detalle_carrito,
    obtener_carrito_activo_usuario,
)

from app.inventario.services import (
    obtener_disponibilidad_variantes,
)

from decimal import Decimal

from app.comercio.repositories import (
    crear_pedido_completo,
    cerrar_carrito_usuario,
    obtener_pedidos_usuario,
    obtener_pedido_usuario,
    obtener_detalles_pedido,
    obtener_composiciones_pedido,
)


# ============================================================
# REGLAS COMERCIALES DE PACK PERSONALIZADO
# ============================================================

# La cantidad total siempre debe coincidir con el tamaño del pack.
# La distribución entre sabores es libre, respetando este máximo.
MAX_SABORES_POR_PACK = {
    6: 3,
    12: 4,
    24: 6,
}


# ============================================================
# UTILIDADES
# ============================================================

def _stock_vacio():

    return {
        "stock_fisico": 0,
        "stock_reservado": 0,
        "stock_disponible": 0,
        "disponible": False,
    }


def _convertir_cantidad(valor):

    try:

        cantidad = int(valor)

    except (TypeError, ValueError):

        return None

    if cantidad <= 0:
        return None

    return cantidad


# ============================================================
# 1. PRODUCTOS INDIVIDUALES
# ============================================================

def obtener_catalogo_tienda():

    productos = obtener_variantes_comerciales_tienda()

    if not productos:
        return []

    variantes_ids = [
        producto["variante_id"]
        for producto in productos
    ]

    disponibilidad = obtener_disponibilidad_variantes(
        variantes_ids
    )

    catalogo = []

    for producto in productos:

        variante_id = producto["variante_id"]

        stock = disponibilidad.get(
            variante_id,
            _stock_vacio(),
        )

        catalogo.append({
            **producto,

            "stock_fisico":
                stock["stock_fisico"],

            "stock_reservado":
                stock["stock_reservado"],

            "stock_disponible":
                stock["stock_disponible"],

            "disponible":
                stock["disponible"],
        })

    return catalogo


# ============================================================
# 2. VARIANTES 330 ML
# ============================================================

def obtener_variantes_330ml_con_stock():

    variantes = obtener_variantes_330ml_tienda()

    if not variantes:
        return []

    variantes_ids = [
        item["variante_id"]
        for item in variantes
    ]

    disponibilidad = obtener_disponibilidad_variantes(
        variantes_ids
    )

    resultado = []

    for variante in variantes:

        stock = disponibilidad.get(
            variante["variante_id"],
            _stock_vacio(),
        )

        resultado.append({
            **variante,
            **stock,
        })

    return resultado


# ============================================================
# 3. PACKS
# ============================================================

def obtener_packs_tienda():

    packs = obtener_packs_comerciales_tienda()

    if not packs:
        return []

    pack_ids = [
        pack["pack_id"]
        for pack in packs
    ]

    componentes = obtener_componentes_packs(
        pack_ids
    )

    componentes_por_pack = defaultdict(list)

    variantes_ids = set()

    for componente in componentes:

        componentes_por_pack[
            componente["pack_id"]
        ].append(componente)

        variantes_ids.add(
            componente["variante_id"]
        )

    disponibilidad = obtener_disponibilidad_variantes(
        list(variantes_ids)
    )

    # Solo los sabores comerciales visibles pueden venderse
    # mediante packs fijos en la tienda.
    variantes_330_visibles = {
        item["variante_id"]
        for item in obtener_variantes_330ml_tienda()
    }

    resultado = []

    for pack in packs:

        pack_id = pack["pack_id"]

        componentes_pack = (
            componentes_por_pack.get(
                pack_id,
                [],
            )
        )

        tipo_pack = str(pack["tipo"]).upper()

        # Un pack fijo no debe quedar disponible por API si contiene
        # variantes de sabores que hoy están ocultos comercialmente.
        if tipo_pack == "FIJO":
            if (
                not componentes_pack
                or any(
                    componente["variante_id"]
                    not in variantes_330_visibles
                    for componente in componentes_pack
                )
            ):
                continue

        limites = []
        detalle_componentes = []

        for componente in componentes_pack:

            variante_id = (
                componente["variante_id"]
            )

            cantidad_requerida = int(
                componente["cantidad"]
            )

            stock = disponibilidad.get(
                variante_id,
                _stock_vacio(),
            )

            disponible = int(
                stock["stock_disponible"]
            )

            if cantidad_requerida > 0:

                maximo = (
                    disponible
                    // cantidad_requerida
                )

            else:

                maximo = 0

            limites.append(maximo)

            detalle_componentes.append({
                "variante_id":
                    variante_id,

                "cantidad_requerida":
                    cantidad_requerida,

                "stock_disponible":
                    disponible,

                "maximo_packs":
                    maximo,
            })

        # Packs FIJOS necesitan componentes.
        # Packs personalizados se validan con su composición.
        if (
            tipo_pack == "FIJO"
            and limites
        ):

            stock_packs = min(limites)

        elif tipo_pack != "FIJO":

            stock_packs = None

        else:

            stock_packs = 0

        resultado.append({
            **pack,

            "componentes":
                detalle_componentes,

            "stock_disponible_packs":
                stock_packs,

            "disponible":
                (
                    stock_packs > 0
                    if stock_packs is not None
                    else True
                ),
        })

    return resultado


# ============================================================
# 4. PACK PERSONALIZADO
# ============================================================

def obtener_configuracion_pack_personalizado():

    packs = obtener_packs_comerciales_tienda()

    personalizados = [
        pack
        for pack in packs
        if str(pack["tipo"]).upper() == "PERSONALIZABLE"
    ]

    if not personalizados:
        return []

    pack_ids = [
        pack["pack_id"]
        for pack in personalizados
    ]

    reglas = obtener_reglas_packs(
        pack_ids
    )

    permitidas = obtener_variantes_permitidas_packs(
        pack_ids
    )

    variantes_330 = obtener_variantes_330ml_tienda()

    variantes_por_id = {
        item["variante_id"]: item
        for item in variantes_330
    }

    variantes_ids = list({
        item["variante_id"]
        for item in permitidas
    })

    disponibilidad = obtener_disponibilidad_variantes(
        variantes_ids
    )

    reglas_por_pack = defaultdict(list)
    permitidas_por_pack = defaultdict(list)

    for regla in reglas:

        reglas_por_pack[
            regla["pack_id"]
        ].append({
            "numero_sabores":
                int(regla["numero_sabores"]),

            "unidades_por_sabor":
                int(regla["unidades_por_sabor"]),
        })

    for relacion in permitidas:

        variante_id = relacion["variante_id"]

        if variante_id not in variantes_por_id:
            continue

        variante = variantes_por_id[variante_id]

        stock = disponibilidad.get(
            variante_id,
            _stock_vacio(),
        )

        permitidas_por_pack[
            relacion["pack_id"]
        ].append({
            **variante,
            **stock,
        })

    resultado = []

    for pack in personalizados:

        resultado.append({
            **pack,

            "reglas":
                reglas_por_pack.get(
                    pack["pack_id"],
                    [],
                ),

            "variantes_permitidas":
                permitidas_por_pack.get(
                    pack["pack_id"],
                    [],
                ),
        })

    return resultado


# ============================================================
# 5. CONSUMO ACTUAL DEL CARRITO
# ============================================================

def _obtener_consumo_carrito(usuario_id):
    """
    Calcula cuánto stock ya está comprometido
    visualmente dentro del carrito del usuario.

    El carrito todavía NO reserva inventario,
    pero esto evita que el mismo usuario agregue
    cantidades superiores al stock disponible.
    """

    detalles = obtener_detalles_carrito_usuario(
        usuario_id
    )

    consumo = defaultdict(int)

    if not detalles:
        return consumo

    detalle_ids = [
        item["carrito_detalle_id"]
        for item in detalles
    ]

    composiciones = obtener_composiciones_carrito(
        detalle_ids
    )

    composicion_por_detalle = defaultdict(list)

    for item in composiciones:

        composicion_por_detalle[
            item["carrito_detalle_id"]
        ].append(item)

    pack_ids_fijos = list({
        item["pack_id"]
        for item in detalles
        if (
            item["tipo"] == "PACK"
            and item["pack_id"]
            and str(item["pack_tipo"]).upper()
            == "FIJO"
        )
    })

    componentes = obtener_componentes_packs(
        pack_ids_fijos
    )

    componentes_por_pack = defaultdict(list)

    for componente in componentes:

        componentes_por_pack[
            componente["pack_id"]
        ].append(componente)

    for detalle in detalles:

        cantidad_detalle = int(
            detalle["cantidad"]
        )

        # -----------------------------------------------
        # Variante individual
        # -----------------------------------------------

        if (
            detalle["tipo"] == "VARIANTE"
            and detalle["variante_id"]
        ):

            consumo[
                detalle["variante_id"]
            ] += cantidad_detalle

        # -----------------------------------------------
        # Pack fijo
        # -----------------------------------------------

        elif (
            detalle["tipo"] == "PACK"
            and str(
                detalle["pack_tipo"]
            ).upper() == "FIJO"
        ):

            for componente in (
                componentes_por_pack.get(
                    detalle["pack_id"],
                    [],
                )
            ):

                consumo[
                    componente["variante_id"]
                ] += (
                    int(componente["cantidad"])
                    * cantidad_detalle
                )

        # -----------------------------------------------
        # Pack personalizado
        # -----------------------------------------------

        elif detalle["tipo"] == "PACK":

            for componente in (
                composicion_por_detalle.get(
                    detalle["carrito_detalle_id"],
                    [],
                )
            ):

                consumo[
                    componente["variante_id"]
                ] += (
                    int(componente["cantidad"])
                    * cantidad_detalle
                )

    return consumo


# ============================================================
# 6. VALIDAR VARIANTE INDIVIDUAL
# ============================================================

def validar_cantidad_variante(
    variante_id,
    cantidad_solicitada,
    usuario_id=None,
):

    cantidad = _convertir_cantidad(
        cantidad_solicitada
    )

    if cantidad is None:

        return {
            "valido": False,
            "mensaje": "Cantidad inválida.",
            "stock_disponible": 0,
        }

    # Solo permitimos las variantes comerciales
    # individuales de la tienda.

    catalogo = obtener_variantes_comerciales_tienda()

    variante = next(
        (
            item
            for item in catalogo
            if item["variante_id"] == variante_id
        ),
        None,
    )

    if not variante:

        return {
            "valido": False,
            "mensaje":
                "El producto solicitado no está disponible.",
            "stock_disponible": 0,
        }

    disponibilidad = obtener_disponibilidad_variantes(
        [variante_id]
    )

    stock_real = int(
        disponibilidad.get(
            variante_id,
            _stock_vacio(),
        )["stock_disponible"]
    )

    consumo_carrito = 0

    if usuario_id:

        consumo = _obtener_consumo_carrito(
            usuario_id
        )

        consumo_carrito = int(
            consumo.get(
                variante_id,
                0,
            )
        )

    restante = max(
        stock_real - consumo_carrito,
        0,
    )

    if cantidad > restante:

        return {
            "valido": False,
            "mensaje":
                "La cantidad supera el stock disponible.",
            "stock_disponible": restante,
        }

    return {
        "valido": True,
        "mensaje": "Stock disponible.",
        "stock_disponible": restante,
    }


# ============================================================
# 7. VALIDAR PACK FIJO
# ============================================================

def validar_cantidad_pack(
    pack_id,
    cantidad_solicitada,
    usuario_id=None,
):

    cantidad = _convertir_cantidad(
        cantidad_solicitada
    )

    if cantidad is None:

        return {
            "valido": False,
            "mensaje": "Cantidad inválida.",
            "packs_disponibles": 0,
        }

    packs = obtener_packs_tienda()

    pack = next(
        (
            item
            for item in packs
            if (
                item["pack_id"] == pack_id
                and str(
                    item["tipo"]
                ).upper() == "FIJO"
            )
        ),
        None,
    )

    if not pack:

        return {
            "valido": False,
            "mensaje":
                "El pack solicitado no está disponible.",
            "packs_disponibles": 0,
        }

    consumo = defaultdict(int)

    if usuario_id:

        consumo = _obtener_consumo_carrito(
            usuario_id
        )

    limites = []

    for componente in pack["componentes"]:

        variante_id = componente["variante_id"]

        requerido = int(
            componente["cantidad_requerida"]
        )

        disponibilidad = (
            obtener_disponibilidad_variantes(
                [variante_id]
            )
        )

        stock_real = int(
            disponibilidad.get(
                variante_id,
                _stock_vacio(),
            )["stock_disponible"]
        )

        ya_en_carrito = int(
            consumo.get(
                variante_id,
                0,
            )
        )

        restante = max(
            stock_real - ya_en_carrito,
            0,
        )

        if requerido <= 0:

            limites.append(0)

        else:

            limites.append(
                restante // requerido
            )

    disponibles = (
        min(limites)
        if limites
        else 0
    )

    if cantidad > disponibles:

        return {
            "valido": False,
            "mensaje":
                "La cantidad supera el stock disponible.",
            "packs_disponibles": disponibles,
        }

    return {
        "valido": True,
        "mensaje": "Stock disponible.",
        "packs_disponibles": disponibles,
    }


# ============================================================
# 8. VALIDAR PACK PERSONALIZADO
# ============================================================

def validar_pack_personalizado(
    pack_id,
    composicion,
    cantidad_packs,
    usuario_id=None,
):

    cantidad_packs = _convertir_cantidad(
        cantidad_packs
    )

    if cantidad_packs is None:

        return {
            "valido": False,
            "mensaje": "Cantidad de packs inválida.",
        }

    configuraciones = (
        obtener_configuracion_pack_personalizado()
    )

    pack = next(
        (
            item
            for item in configuraciones
            if item["pack_id"] == pack_id
        ),
        None,
    )

    if not pack:

        return {
            "valido": False,
            "mensaje":
                "El pack personalizado no está disponible.",
        }

    if not isinstance(composicion, list):

        return {
            "valido": False,
            "mensaje":
                "La composición del pack es inválida.",
        }

    normalizada = defaultdict(int)

    for item in composicion:

        variante_id = item.get(
            "variante_id"
        )

        cantidad = _convertir_cantidad(
            item.get("cantidad")
        )

        if not variante_id or cantidad is None:

            return {
                "valido": False,
                "mensaje":
                    "La composición contiene datos inválidos.",
            }

        normalizada[variante_id] += cantidad

    permitidas = {
        item["variante_id"]: item
        for item
        in pack["variantes_permitidas"]
    }

    for variante_id in normalizada:

        if variante_id not in permitidas:

            return {
                "valido": False,
                "mensaje":
                    "Uno de los sabores no está permitido.",
            }

    total_botellas = sum(
        normalizada.values()
    )

    cantidad_pack = int(
        pack["cantidad_unidades"]
    )

    if total_botellas != cantidad_pack:

        return {
            "valido": False,
            "mensaje":
                (
                    f"Debes seleccionar exactamente "
                    f"{cantidad_pack} botellas."
                ),
        }

    numero_sabores = len(normalizada)

    max_sabores = MAX_SABORES_POR_PACK.get(
        cantidad_pack
    )

    if max_sabores is None:

        return {
            "valido": False,
            "mensaje":
                "El tamaño del pack no tiene una regla comercial válida.",
        }

    if not (
        1 <= numero_sabores <= max_sabores
    ):

        return {
            "valido": False,
            "mensaje":
                (
                    f"Este pack permite como máximo "
                    f"{max_sabores} sabores."
                ),
        }

    # La distribución entre sabores es libre.
    # Ejemplo para pack 6:
    # 3 Café + 2 Limón + 1 Jamaica.
    # La única condición adicional es respetar
    # el stock disponible de cada variante.

    consumo = defaultdict(int)

    if usuario_id:

        consumo = _obtener_consumo_carrito(
            usuario_id
        )

    variantes_ids = list(
        normalizada.keys()
    )

    disponibilidad = obtener_disponibilidad_variantes(
        variantes_ids
    )

    for variante_id, cantidad in normalizada.items():

        stock_real = int(
            disponibilidad.get(
                variante_id,
                _stock_vacio(),
            )["stock_disponible"]
        )

        ya_en_carrito = int(
            consumo.get(
                variante_id,
                0,
            )
        )

        requerido = (
            cantidad
            * cantidad_packs
        )

        restante = max(
            stock_real - ya_en_carrito,
            0,
        )

        if requerido > restante:

            sabor = permitidas[
                variante_id
            ]["sabor"]

            return {
                "valido": False,
                "mensaje":
                    (
                        f"No hay suficiente stock "
                        f"de {sabor}."
                    ),
            }

    composicion_normalizada = [
        {
            "variante_id": variante_id,
            "cantidad": cantidad,
        }
        for variante_id, cantidad
        in normalizada.items()
    ]

    return {
        "valido": True,
        "mensaje": "Pack válido.",
        "composicion":
            composicion_normalizada,
    }


# ============================================================
# 9. AGREGAR AL CARRITO
# ============================================================

def agregar_al_carrito(
    usuario_id,
    articulo_venta_id,
    cantidad,
    composicion=None,
):

    cantidad = _convertir_cantidad(
        cantidad
    )

    if cantidad is None:

        return {
            "ok": False,
            "mensaje": "Cantidad inválida.",
        }

    articulo = obtener_articulo_venta_por_id(
        articulo_venta_id
    )

    if not articulo:

        return {
            "ok": False,
            "mensaje":
                "El artículo solicitado no está disponible.",
        }

    # ========================================================
    # VARIANTE INDIVIDUAL
    # ========================================================

    if articulo["tipo"] == "VARIANTE":

        validacion = validar_cantidad_variante(
            articulo["variante_id"],
            cantidad,
            usuario_id,
        )

        if not validacion["valido"]:

            return {
                "ok": False,
                "mensaje":
                    validacion["mensaje"],
            }

        guardar_item_carrito(
            usuario_id=usuario_id,
            articulo_venta_id=articulo_venta_id,
            cantidad=cantidad,
            acumular=True,
        )

    # ========================================================
    # PACK
    # ========================================================

    elif articulo["tipo"] == "PACK":

        tipo_pack = str(
            articulo["pack_tipo"]
        ).upper()

        # ----------------------------------------------------
        # PACK FIJO
        # ----------------------------------------------------

        if tipo_pack == "FIJO":

            validacion = validar_cantidad_pack(
                articulo["pack_id"],
                cantidad,
                usuario_id,
            )

            if not validacion["valido"]:

                return {
                    "ok": False,
                    "mensaje":
                        validacion["mensaje"],
                }

            guardar_item_carrito(
                usuario_id=usuario_id,
                articulo_venta_id=articulo_venta_id,
                cantidad=cantidad,
                acumular=True,
            )

        # ----------------------------------------------------
        # PACK PERSONALIZADO
        # ----------------------------------------------------

        else:

            validacion = validar_pack_personalizado(
                articulo["pack_id"],
                composicion,
                cantidad,
                usuario_id,
            )

            if not validacion["valido"]:

                return {
                    "ok": False,
                    "mensaje":
                        validacion["mensaje"],
                }

            guardar_item_carrito(
                usuario_id=usuario_id,
                articulo_venta_id=articulo_venta_id,
                cantidad=cantidad,
                composicion=(
                    validacion["composicion"]
                ),
                acumular=False,
            )

    else:

        return {
            "ok": False,
            "mensaje":
                "Tipo de artículo no permitido.",
        }

    carrito = obtener_carrito_usuario(
        usuario_id
    )

    return {
        "ok": True,
        "mensaje":
            "Producto agregado al carrito.",
        "carrito": carrito,
    }


# ============================================================
# 10. OBTENER CARRITO
# ============================================================

def obtener_carrito_usuario(usuario_id):

    detalles = obtener_detalles_carrito_usuario(
        usuario_id
    )

    if not detalles:

        return {
            "items": [],
            "cantidad_items": 0,
            "subtotal": 0.0,
        }

    detalle_ids = [
        item["carrito_detalle_id"]
        for item in detalles
    ]

    composiciones = obtener_composiciones_carrito(
        detalle_ids
    )

    composicion_por_detalle = defaultdict(list)

    for item in composiciones:

        composicion_por_detalle[
            item["carrito_detalle_id"]
        ].append({
            "variante_id":
                item["variante_id"],

            "cantidad":
                int(item["cantidad"]),
        })

    items = []
    subtotal = 0.0
    cantidad_items = 0

    for detalle in detalles:

        cantidad = int(
            detalle["cantidad"]
        )

        precio = float(
            detalle["precio"] or 0
        )

        total = precio * cantidad

        subtotal += total
        cantidad_items += cantidad

        if detalle["tipo"] == "VARIANTE":

            nombre = (
                detalle["nombre_comercial"]
            )

        else:

            nombre = detalle["pack_nombre"]

        items.append({
            "carrito_detalle_id":
                detalle["carrito_detalle_id"],

            "articulo_venta_id":
                detalle["articulo_venta_id"],

            "tipo":
                detalle["tipo"],

            "nombre":
                nombre,

            "cantidad":
                cantidad,

            "precio":
                precio,

            "subtotal":
                total,

            "moneda":
                detalle["moneda"],

            "composicion":
                composicion_por_detalle.get(
                    detalle["carrito_detalle_id"],
                    [],
                ),
        })

    return {
        "items": items,
        "cantidad_items":
            cantidad_items,

        "subtotal":
            round(subtotal, 2),
    }


# ============================================================
# 11. DATOS COMPLETOS DE TIENDA
# ============================================================

def obtener_datos_tienda():

    return {
        "catalogo":
            obtener_catalogo_tienda(),

        "variantes_330":
            obtener_variantes_330ml_con_stock(),

        "packs":
            obtener_packs_tienda(),

        "packs_personalizados":
            obtener_configuracion_pack_personalizado(),
    }

# ============================================================
# 12. BUSCAR DETALLE DEL CARRITO DEL USUARIO
# ============================================================

def _obtener_detalle_carrito(
    usuario_id,
    carrito_detalle_id,
):
    """
    Busca un detalle exclusivamente dentro
    del carrito ACTIVO del usuario autenticado.
    """

    detalles = obtener_detalles_carrito_usuario(
        usuario_id
    )

    return next(
        (
            detalle
            for detalle in detalles
            if detalle["carrito_detalle_id"]
            == carrito_detalle_id
        ),
        None,
    )


# ============================================================
# 13. ACTUALIZAR CANTIDAD DEL CARRITO
# ============================================================

def actualizar_item_carrito(
    usuario_id,
    carrito_detalle_id,
    nueva_cantidad,
):
    """
    Cambia la cantidad de un producto del carrito.

    Si la cantidad aumenta, únicamente validamos
    el incremento adicional contra el stock restante.

    Esto evita contar dos veces las unidades
    que el usuario ya posee dentro del carrito.
    """

    try:

        nueva_cantidad = int(
            nueva_cantidad
        )

    except (TypeError, ValueError):

        return {
            "ok": False,
            "mensaje":
                "La cantidad indicada no es válida.",
        }

    if nueva_cantidad <= 0:

        return {
            "ok": False,
            "mensaje":
                "La cantidad debe ser mayor a cero.",
        }

    detalle = _obtener_detalle_carrito(
        usuario_id,
        carrito_detalle_id,
    )

    if not detalle:

        return {
            "ok": False,
            "mensaje":
                "El producto no pertenece a tu carrito.",
        }

    cantidad_actual = int(
        detalle["cantidad"]
    )

    # --------------------------------------------------------
    # La cantidad no cambió.
    # --------------------------------------------------------

    if nueva_cantidad == cantidad_actual:

        return {
            "ok": True,
            "mensaje":
                "La cantidad no cambió.",
            "carrito":
                obtener_carrito_usuario(
                    usuario_id
                ),
        }

    # --------------------------------------------------------
    # Si aumentamos cantidad necesitamos validar
    # únicamente las nuevas unidades.
    # --------------------------------------------------------

    if nueva_cantidad > cantidad_actual:

        incremento = (
            nueva_cantidad
            - cantidad_actual
        )

        # ====================================================
        # VARIANTE INDIVIDUAL
        # ====================================================

        if (
            detalle["tipo"] == "VARIANTE"
            and detalle["variante_id"]
        ):

            validacion = (
                validar_cantidad_variante(
                    detalle["variante_id"],
                    incremento,
                    usuario_id,
                )
            )

        # ====================================================
        # PACK
        # ====================================================

        elif (
            detalle["tipo"] == "PACK"
            and detalle["pack_id"]
        ):

            tipo_pack = str(
                detalle["pack_tipo"]
                or ""
            ).upper()

            # ------------------------------------------------
            # PACK FIJO
            # ------------------------------------------------

            if tipo_pack == "FIJO":

                validacion = (
                    validar_cantidad_pack(
                        detalle["pack_id"],
                        incremento,
                        usuario_id,
                    )
                )

            # ------------------------------------------------
            # PACK PERSONALIZABLE
            # ------------------------------------------------

            elif tipo_pack == "PERSONALIZABLE":

                composiciones = (
                    obtener_composiciones_carrito(
                        [carrito_detalle_id]
                    )
                )

                composicion = [
                    {
                        "variante_id":
                            item["variante_id"],

                        "cantidad":
                            int(
                                item["cantidad"]
                            ),
                    }
                    for item in composiciones
                ]

                if not composicion:

                    return {
                        "ok": False,
                        "mensaje":
                            (
                                "El pack personalizado "
                                "no tiene una composición válida."
                            ),
                    }

                validacion = (
                    validar_pack_personalizado(
                        detalle["pack_id"],
                        composicion,
                        incremento,
                        usuario_id,
                    )
                )

            else:

                return {
                    "ok": False,
                    "mensaje":
                        "El tipo de pack no es válido.",
                }

        else:

            return {
                "ok": False,
                "mensaje":
                    "El artículo del carrito no es válido.",
            }

        if not validacion["valido"]:

            return {
                "ok": False,
                "mensaje":
                    validacion["mensaje"],
            }

    # --------------------------------------------------------
    # Guardar nueva cantidad.
    # Al disminuir no necesitamos stock adicional.
    # --------------------------------------------------------

    actualizado = (
        actualizar_cantidad_detalle_carrito(
            usuario_id,
            carrito_detalle_id,
            nueva_cantidad,
        )
    )

    if not actualizado:

        return {
            "ok": False,
            "mensaje":
                "No se pudo actualizar el producto.",
        }

    return {
        "ok": True,
        "mensaje":
            "Cantidad actualizada.",
        "carrito":
            obtener_carrito_usuario(
                usuario_id
            ),
    }


# ============================================================
# 14. ELIMINAR ITEM DEL CARRITO
# ============================================================

def eliminar_item_carrito(
    usuario_id,
    carrito_detalle_id,
):
    """
    Elimina de forma segura un detalle del
    carrito ACTIVO del usuario.
    """

    detalle = _obtener_detalle_carrito(
        usuario_id,
        carrito_detalle_id,
    )

    if not detalle:

        return {
            "ok": False,
            "mensaje":
                "El producto no pertenece a tu carrito.",
        }

    eliminado = eliminar_detalle_carrito(
        usuario_id,
        carrito_detalle_id,
    )

    if not eliminado:

        return {
            "ok": False,
            "mensaje":
                "No se pudo eliminar el producto.",
        }

    return {
        "ok": True,
        "mensaje":
            "Producto eliminado del carrito.",
        "carrito":
            obtener_carrito_usuario(
                usuario_id
            ),
    }

def validar_stock_carrito_pedido(usuario_id):

    detalles = obtener_detalles_carrito_usuario(
        usuario_id
    )

    consumo = {}

    for detalle in detalles:

        articulo = obtener_articulo_venta_por_id(
            detalle["articulo_venta_id"]
        )

        if not articulo:
            continue

        cantidad_item = int(
            detalle["cantidad"]
        )

        # --------------------------------------------
        # VARIANTE
        # --------------------------------------------

        if articulo["tipo"] == "VARIANTE":

            variante_id = articulo["variante_id"]

            consumo[variante_id] = (
                consumo.get(variante_id, 0)
                + cantidad_item
            )

        # --------------------------------------------
        # PACK
        # --------------------------------------------

        elif articulo["tipo"] == "PACK":

            # PACK FIJO
            if articulo.get("tipo_pack") == "FIJO":

                componentes = obtener_componentes_packs(
                    [articulo["pack_id"]]
                )

                for componente in componentes:

                    variante_id = componente["variante_id"]

                    cantidad = (
                        int(componente["cantidad"])
                        * cantidad_item
                    )

                    consumo[variante_id] = (
                        consumo.get(variante_id, 0)
                        + cantidad
                    )

            # PACK PERSONALIZABLE
            else:

                composiciones = obtener_composiciones_carrito(
                    [detalle["id"]]
                )

                for composicion in composiciones:

                    variante_id = composicion["variante_id"]

                    cantidad = (
                        int(composicion["cantidad"])
                        * cantidad_item
                    )

                    consumo[variante_id] = (
                        consumo.get(variante_id, 0)
                        + cantidad
                    )

    if not consumo:

        return {
            "valido": True,
            "errores": []
        }

    disponibilidad = obtener_disponibilidad_variantes(
        list(consumo.keys())
    )

    errores = []

    for variante_id, cantidad_solicitada in consumo.items():

        stock = disponibilidad.get(
            variante_id,
            {}
        )

        stock_disponible = int(
            stock.get(
                "stock_disponible",
                0
            )
        )

        if cantidad_solicitada > stock_disponible:

            errores.append({
                "variante_id": variante_id,
                "solicitado": cantidad_solicitada,
                "disponible": stock_disponible
            })

    return {
        "valido": len(errores) == 0,
        "errores": errores
    }

def confirmar_pedido(
    usuario_id,
    datos_cliente,
    datos_facturacion,
    costo_entrega=Decimal("0.00")
):

    # ==================================================
    # 1. COMPROBAR CARRITO
    # ==================================================

    carrito = obtener_carrito_activo_usuario(
        usuario_id
    )

    if not carrito:

        return {
            "ok": False,
            "mensaje": "No tienes un carrito activo."
        }

    detalles_carrito = obtener_detalles_carrito_usuario(
        usuario_id
    )

    if not detalles_carrito:

        return {
            "ok": False,
            "mensaje": "El carrito está vacío."
        }

    # ==================================================
    # 2. VALIDAR STOCK NUEVAMENTE
    # ==================================================

    validacion = validar_stock_carrito_pedido(
        usuario_id
    )

    if not validacion["valido"]:

        return {
            "ok": False,
            "mensaje": (
                "Algunos productos ya no tienen "
                "stock suficiente."
            ),
            "errores": validacion["errores"]
        }

    # ==================================================
    # 3. CALCULAR TOTALES
    # ==================================================

    subtotal = Decimal("0.00")
    descuento_total = Decimal("0.00")

    detalles_pedido = []

    for detalle in detalles_carrito:

        cantidad = int(
            detalle["cantidad"]
        )

        precio_unitario = Decimal(
            str(
                detalle.get(
                    "precio",
                    0
                )
            )
        )

        descuento_unitario = Decimal(
            str(
                detalle.get(
                    "descuento_unitario",
                    0
                )
            )
        )

        subtotal_linea = (
            precio_unitario
            * cantidad
        )

        descuento_linea = (
            descuento_unitario
            * cantidad
        )

        subtotal += subtotal_linea

        descuento_total += descuento_linea

        # ----------------------------------------------
        # COMPOSICIONES DEL CARRITO
        # ----------------------------------------------

        composiciones_carrito = (
            obtener_composiciones_carrito(
                [detalle["id"]]
            )
        )

        composiciones_pedido = []

        for composicion in composiciones_carrito:

            composiciones_pedido.append({
                "variante_id": composicion["variante_id"],
                "nombre_variante": composicion.get(
                    "nombre_variante",
                    ""
                ),
                "cantidad": composicion["cantidad"]
            })

        detalles_pedido.append({

            "articulo_venta_id": (
                detalle["articulo_venta_id"]
            ),

            "nombre_articulo": (
                detalle.get(
                    "nombre_articulo",
                    "Producto"
                )
            ),

            "cantidad": cantidad,

            "precio_unitario": (
                precio_unitario
            ),

            "descuento_unitario": (
                descuento_unitario
            ),

            "subtotal_linea": (
                subtotal_linea
            ),

            "composiciones": (
                composiciones_pedido
            )
        })

    # ==================================================
    # 4. TOTAL
    # ==================================================

    costo_entrega = Decimal(
        str(costo_entrega)
    )

    total = (
        subtotal
        - descuento_total
        + costo_entrega
    )

    if total < 0:

        return {
            "ok": False,
            "mensaje": "El total del pedido no puede ser negativo."
        }

    # ==================================================
    # 5. CREAR PEDIDO
    # ==================================================

    pedido = crear_pedido_completo(

        usuario_id=usuario_id,

        origen="WEB",

        subtotal=subtotal,

        descuento_total=descuento_total,

        costo_entrega=costo_entrega,

        total=total,

        moneda="PEN",

        detalles=detalles_pedido,

        datos_cliente=datos_cliente,

        datos_facturacion=datos_facturacion
    )

    # ==================================================
    # 6. CERRAR CARRITO
    # ==================================================

    cerrar_carrito_usuario(
        usuario_id
    )

    # ==================================================
    # 7. RESPUESTA
    # ==================================================

    return {

        "ok": True,

        "pedido_id": pedido["id"],

        "numero_pedido": (
            pedido["numero_pedido"]
        ),

        "subtotal": subtotal,

        "descuento_total": (
            descuento_total
        ),

        "costo_entrega": (
            costo_entrega
        ),

        "total": total
    }

def obtener_mis_pedidos(usuario_id):

    return obtener_pedidos_usuario(
        usuario_id
    )

def obtener_mi_pedido(
    pedido_id,
    usuario_id
):

    pedido = obtener_pedido_usuario(
        pedido_id,
        usuario_id
    )

    if not pedido:
        return None

    detalles = obtener_detalles_pedido(
        pedido_id
    )

    for detalle in detalles:

        detalle["composiciones"] = (
            obtener_composiciones_pedido(
                detalle["id"]
            )
        )

    pedido["detalles"] = detalles

    return pedido

