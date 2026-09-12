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
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.inventario.services import (
    reservar_stock_pedido,
    liberar_stock_pedido,
    confirmar_stock_pedido,
)

from app.operaciones.services import (
    crear_pago_checkout,
    cancelar_pago_checkout,
    cotizar_delivery_local,
    cotizar_envio_transportista,
    validar_entrega_confirmacion,
    crear_entrega_pedido,
    compensar_entrega_pedido,
)

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
    obtener_pesos_variantes,
    crear_pedido,
    actualizar_estado_pedido,
    cerrar_carrito_usuario,
    obtener_variantes_snapshot,
    reabrir_carrito_usuario,
)

from app.inventario.services import (
    obtener_disponibilidad_variantes,
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
# 6. PESO TOTAL DEL CARRITO
# ============================================================

def _calcular_peso_carrito(usuario_id):
    """
    Calcula el peso físico total del contenido del carrito.

    La función reutiliza el consumo real de variantes calculado por
    _obtener_consumo_carrito(), por lo que contempla correctamente:

    - productos individuales;
    - packs fijos;
    - packs personalizados.

    El peso unitario de cada variante se obtiene desde la base de datos
    mediante obtener_pesos_variantes(). Si una variante no tiene un peso
    registrado, no se inventa ningún valor: se informa como incompleta.
    """

    consumo = _obtener_consumo_carrito(
        usuario_id
    )

    if not consumo:
        return {
            "peso_total_gramos": 0,
            "peso_total_kg": 0.0,
            "peso_completo": True,
            "variantes_sin_peso": [],
        }

    variantes_ids = list(
        consumo.keys()
    )

    pesos = obtener_pesos_variantes(
        variantes_ids
    )

    peso_total_gramos = 0.0
    variantes_sin_peso = []

    for variante_id, cantidad in consumo.items():

        peso_unitario = pesos.get(
            variante_id
        )

        # No se inventa un peso cuando falta información física.
        # Esto evita cotizaciones de envío incorrectas.
        if peso_unitario is None:

            variantes_sin_peso.append(
                variante_id
            )

            continue

        peso_total_gramos += (
            float(peso_unitario)
            * int(cantidad)
        )

    return {
        "peso_total_gramos":
            int(round(peso_total_gramos)),

        "peso_total_kg":
            round(
                peso_total_gramos / 1000,
                3,
            ),

        "peso_completo":
            len(variantes_sin_peso) == 0,

        "variantes_sin_peso":
            variantes_sin_peso,
    }


# ============================================================
# 7. VALIDAR VARIANTE INDIVIDUAL
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
# 8. VALIDAR PACK FIJO
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
# 9. VALIDAR PACK PERSONALIZADO
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
# 10. AGREGAR AL CARRITO
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
# 11. OBTENER CARRITO
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
            "peso_total_gramos": 0,
            "peso_total_kg": 0.0,
            "peso_completo": True,
            "variantes_sin_peso": [],
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

    # --------------------------------------------------------
    # Peso físico total del carrito.
    # --------------------------------------------------------
    # Se calcula desde las variantes realmente contenidas en el carrito.
    # Nunca se confía en un peso enviado desde el frontend.
    peso = _calcular_peso_carrito(
        usuario_id
    )

    return {
        "items": items,

        "cantidad_items":
            cantidad_items,

        "subtotal":
            round(subtotal, 2),

        "peso_total_gramos":
            peso["peso_total_gramos"],

        "peso_total_kg":
            peso["peso_total_kg"],

        "peso_completo":
            peso["peso_completo"],

        "variantes_sin_peso":
            peso["variantes_sin_peso"],
    }


# ============================================================
# 12. DATOS COMPLETOS DE TIENDA
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
# 13. BUSCAR DETALLE DEL CARRITO DEL USUARIO
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
# 14. ACTUALIZAR CANTIDAD DEL CARRITO
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
# 15. ELIMINAR ITEM DEL CARRITO
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

# ============================================================
# 16. CONSUMO REAL PARA CONFIRMAR PEDIDO
# ============================================================

def obtener_consumos_carrito_pedido(
    usuario_id,
):
    """
    Expone de forma controlada el consumo físico de variantes
    requerido para convertir el carrito en un pedido.

    Se reutiliza exactamente la misma lógica que ya contempla:

    - variantes individuales;
    - packs fijos;
    - packs personalizados.
    """

    consumo = _obtener_consumo_carrito(
        usuario_id
    )

    return {
        variante_id:
            int(cantidad)

        for variante_id, cantidad
        in consumo.items()

        if int(cantidad) > 0
    }

# ============================================================
# 17. PREPARAR SNAPSHOT COMPLETO DEL PEDIDO
# ============================================================

def preparar_snapshot_pedido(
    usuario_id,
):
    """
    Reconstruye desde backend toda la información comercial
    que debe almacenarse definitivamente en el pedido.

    Incluye:
    - artículo;
    - nombre;
    - cantidad;
    - precio vigente;
    - composición física de variantes.

    La composición se reconstruye también para packs fijos.
    No se acepta ninguna composición enviada desde JavaScript.
    """

    detalles = obtener_detalles_carrito_usuario(
        usuario_id
    )

    if not detalles:

        return {
            "ok": False,
            "mensaje":
                "El carrito está vacío.",
        }

    detalle_ids = [
        detalle["carrito_detalle_id"]
        for detalle in detalles
    ]

    composiciones_carrito = (
        obtener_composiciones_carrito(
            detalle_ids
        )
    )

    composicion_personalizada = (
        defaultdict(list)
    )

    for componente in composiciones_carrito:

        composicion_personalizada[
            componente[
                "carrito_detalle_id"
            ]
        ].append(
            componente
        )

    # --------------------------------------------------------
    # Packs fijos utilizados actualmente en el carrito
    # --------------------------------------------------------

    pack_ids_fijos = list({
        detalle["pack_id"]

        for detalle in detalles

        if (
            detalle["tipo"] == "PACK"
            and detalle["pack_id"]
            and str(
                detalle["pack_tipo"]
            ).upper() == "FIJO"
        )
    })

    componentes_fijos = (
        obtener_componentes_packs(
            pack_ids_fijos
        )
    )

    componentes_por_pack = (
        defaultdict(list)
    )

    for componente in componentes_fijos:

        componentes_por_pack[
            componente["pack_id"]
        ].append(
            componente
        )

    # --------------------------------------------------------
    # Identificar todas las variantes utilizadas
    # --------------------------------------------------------

    variante_ids = set()

    for detalle in detalles:

        if (
            detalle["tipo"] == "VARIANTE"
            and detalle["variante_id"]
        ):

            variante_ids.add(
                detalle["variante_id"]
            )

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

                variante_ids.add(
                    componente[
                        "variante_id"
                    ]
                )

        elif detalle["tipo"] == "PACK":

            for componente in (
                composicion_personalizada.get(
                    detalle[
                        "carrito_detalle_id"
                    ],
                    [],
                )
            ):

                variante_ids.add(
                    componente[
                        "variante_id"
                    ]
                )

    variantes = obtener_variantes_snapshot(
        list(variante_ids)
    )

    # --------------------------------------------------------
    # Construir snapshot de cada línea
    # --------------------------------------------------------

    items = []

    for detalle in detalles:

        cantidad = int(
            detalle["cantidad"]
        )

        precio = float(
            detalle["precio"]
            or 0
        )

        if precio < 0:

            return {
                "ok": False,
                "mensaje":
                    (
                        "Uno de los productos no tiene "
                        "un precio válido."
                    ),
            }

        if detalle["tipo"] == "VARIANTE":

            nombre = str(
                detalle[
                    "nombre_comercial"
                ]
                or ""
            ).strip()

            variante_id = (
                detalle["variante_id"]
            )

            variante = variantes.get(
                variante_id
            )

            if not variante:

                return {
                    "ok": False,
                    "mensaje":
                        (
                            "Una de las variantes del pedido "
                            "ya no está disponible."
                        ),
                }

            # Para una variante individual no necesitamos
            # insertar pedido_composiciones, porque su identidad
            # ya queda asociada mediante articulo_venta_id.
            composicion = []

        elif detalle["tipo"] == "PACK":

            nombre = str(
                detalle[
                    "pack_nombre"
                ]
                or ""
            ).strip()

            composicion = []

            tipo_pack = str(
                detalle[
                    "pack_tipo"
                ]
                or ""
            ).upper()

            # -----------------------------------------------
            # Pack fijo
            # -----------------------------------------------

            if tipo_pack == "FIJO":

                componentes = (
                    componentes_por_pack.get(
                        detalle["pack_id"],
                        [],
                    )
                )

                if not componentes:

                    return {
                        "ok": False,
                        "mensaje":
                            (
                                "Uno de los packs fijos no "
                                "tiene composición registrada."
                            ),
                    }

                for componente in componentes:

                    variante_id = (
                        componente[
                            "variante_id"
                        ]
                    )

                    variante = variantes.get(
                        variante_id
                    )

                    if not variante:

                        return {
                            "ok": False,
                            "mensaje":
                                (
                                    "Una variante de un pack "
                                    "ya no está disponible."
                                ),
                        }

                    composicion.append({
                        "variante_id":
                            variante_id,

                        "nombre_variante":
                            variante[
                                "nombre_variante"
                            ],

                        # Cantidad correspondiente a UNA
                        # unidad comercial del pack.
                        "cantidad":
                            int(
                                componente[
                                    "cantidad"
                                ]
                            ),
                    })

            # -----------------------------------------------
            # Pack personalizado
            # -----------------------------------------------

            else:

                componentes = (
                    composicion_personalizada.get(
                        detalle[
                            "carrito_detalle_id"
                        ],
                        [],
                    )
                )

                if not componentes:

                    return {
                        "ok": False,
                        "mensaje":
                            (
                                "Uno de los packs "
                                "personalizados no tiene "
                                "composición."
                            ),
                    }

                for componente in componentes:

                    variante_id = (
                        componente[
                            "variante_id"
                        ]
                    )

                    variante = variantes.get(
                        variante_id
                    )

                    if not variante:

                        return {
                            "ok": False,
                            "mensaje":
                                (
                                    "Una variante del pack "
                                    "personalizado ya no está "
                                    "disponible."
                                ),
                        }

                    composicion.append({
                        "variante_id":
                            variante_id,

                        "nombre_variante":
                            variante[
                                "nombre_variante"
                            ],

                        # También representa la composición
                        # de UNA unidad comercial del pack.
                        "cantidad":
                            int(
                                componente[
                                    "cantidad"
                                ]
                            ),
                    })

        else:

            return {
                "ok": False,
                "mensaje":
                    (
                        "El carrito contiene un tipo "
                        "de artículo no válido."
                    ),
            }

        if not nombre:

            return {
                "ok": False,
                "mensaje":
                    (
                        "Uno de los artículos no tiene "
                        "un nombre válido."
                    ),
            }

        items.append({
            "articulo_venta_id":
                detalle[
                    "articulo_venta_id"
                ],

            "nombre":
                nombre,

            "cantidad":
                cantidad,

            "precio":
                precio,

            "moneda":
                detalle[
                    "moneda"
                ],

            "composicion":
                composicion,
        })

    return {
        "ok": True,

        "items":
            items,

        "consumos":
            obtener_consumos_carrito_pedido(
                usuario_id
            ),
    }

# ============================================================
# 18. GENERAR NÚMERO DE PEDIDO
# ============================================================

def _generar_numero_pedido():
    """
    Genera un número comercial legible y suficientemente
    pequeño para pedidos.numero_pedido VARCHAR(30).

    Ejemplo:
        PED-20260908-A1B2C3
    """

    fecha = datetime.now().strftime(
        "%Y%m%d"
    )

    aleatorio = uuid.uuid4().hex[
        :6
    ].upper()

    return (
        f"PED-{fecha}-{aleatorio}"
    )


# ============================================================
# 19. CONFIRMAR CHECKOUT
# ============================================================

def confirmar_checkout(
    usuario_id,
    tipo_entrega,
    metodo_pago_id,
    costo_entrega,
    entrega=None,
):
    """
    Orquesta la confirmación definitiva del checkout.

    Orden seguro:

    1. Volver a preparar el carrito desde backend.
    2. Reservar inventario.
    3. Crear pedido.
    4. Crear pago.
    5. Cerrar carrito.
    6. Confirmar salida física del inventario.

    Si algo falla antes de confirmar el inventario,
    se ejecutan compensaciones para evitar datos
    inconsistentes entre módulos.
    """

    # --------------------------------------------------------
    # 1. Validaciones básicas
    # --------------------------------------------------------

    if not usuario_id:

        return {
            "ok": False,
            "mensaje":
                "No se pudo identificar al usuario.",
        }

    if not entrega or not entrega.get('ok'):
        return {'ok': False, 'mensaje': 'La entrega debe validarse antes de crear el pedido.'}

    tipo_entrega = str(
        tipo_entrega or ""
    ).strip().upper()

    tipos_validos = {
        "RECOJO_LOCAL",
        "DELIVERY_LOCAL",
        "TRANSPORTISTA",
    }

    if tipo_entrega not in tipos_validos:

        return {
            "ok": False,
            "mensaje":
                "La modalidad de entrega no es válida.",
        }

    if not metodo_pago_id:

        return {
            "ok": False,
            "mensaje":
                "Debe seleccionar un método de pago.",
        }

    try:

        costo_entrega = Decimal(
            str(
                costo_entrega or 0
            )
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    except Exception:

        return {
            "ok": False,
            "mensaje":
                "El costo de entrega no es válido.",
        }

    if costo_entrega < 0:

        return {
            "ok": False,
            "mensaje":
                "El costo de entrega no puede ser negativo.",
        }

    if tipo_entrega == "RECOJO_LOCAL":

        costo_entrega = Decimal(
            "0.00"
        )

    # --------------------------------------------------------
    # 2. Snapshot seguro del carrito
    # --------------------------------------------------------

    snapshot = preparar_snapshot_pedido(
        usuario_id
    )

    if not snapshot.get(
        "ok"
    ):

        return snapshot

    items = snapshot.get(
        "items",
        [],
    )

    consumos = snapshot.get(
        "consumos",
        [],
    )

    if not items:

        return {
            "ok": False,
            "mensaje":
                "El carrito está vacío.",
        }

    if not consumos:

        return {
            "ok": False,
            "mensaje":
                "No se pudo determinar el consumo de inventario.",
        }

    # --------------------------------------------------------
    # 3. Calcular subtotal nuevamente
    # --------------------------------------------------------

    subtotal = Decimal(
        "0.00"
    )

    for item in items:

        cantidad = Decimal(
            str(
                item.get(
                    "cantidad",
                    0,
                )
            )
        )

        precio = Decimal(
            str(
                item.get(
                    "precio",
                    0,
                )
            )
        )

        subtotal += (
            cantidad
            * precio
        )

    subtotal = subtotal.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    total = (
        subtotal
        + costo_entrega
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    # --------------------------------------------------------
    # 4. Identificadores
    # --------------------------------------------------------

    pedido_id = str(
        uuid.uuid4()
    )

    pago_id = str(
        uuid.uuid4()
    )

    numero_pedido = (
        _generar_numero_pedido()
    )

    reserva_creada = False
    pedido_creado = False
    pago_creado = False
    carrito_cerrado = False
    entrega_creada = False

    try:

        # ----------------------------------------------------
        # 5. Reservar inventario
        # ----------------------------------------------------

        resultado_reserva = (
            reservar_stock_pedido(
                pedido_id=pedido_id,
                consumos=consumos,
            )
        )

        if not resultado_reserva.get(
            "ok"
        ):

            return resultado_reserva

        reserva_creada = True

        # ----------------------------------------------------
        # 6. Crear pedido en Comercio
        # ----------------------------------------------------

        resultado_pedido = crear_pedido(
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            usuario_id=usuario_id,
            items=items,
            costo_entrega=costo_entrega,
            moneda="PEN",
        )

        if not resultado_pedido.get(
            "ok"
        ):

            raise RuntimeError(
                resultado_pedido.get(
                    "mensaje",
                    "No se pudo crear el pedido.",
                )
            )

        pedido_creado = True

        # ----------------------------------------------------
        # 7. Crear pago
        # ----------------------------------------------------

        resultado_pago = (
            crear_pago_checkout(
                pago_id=pago_id,
                pedido_id=pedido_id,
                usuario_id=usuario_id,
                tipo_entrega=tipo_entrega,
                metodo_pago_id=metodo_pago_id,
                monto=total,
                moneda="PEN",
            )
        )

        if not resultado_pago.get(
            "ok"
        ):

            raise RuntimeError(
                resultado_pago.get(
                    "mensaje",
                    "No se pudo crear el pago.",
                )
            )

        pago_creado = True

        # Persistir el destino antes de cerrar carrito y confirmar stock.
        entrega_id = crear_entrega_pedido(pedido_id, usuario_id, entrega)
        entrega_creada = True

        # ----------------------------------------------------
        # 8. Cerrar carrito
        # ----------------------------------------------------

        resultado_carrito = (
            cerrar_carrito_usuario(
                usuario_id
            )
        )

        if resultado_carrito is False or (
            isinstance(resultado_carrito, dict) and not resultado_carrito.get('ok', False)
        ):

            raise RuntimeError(
                "No se pudo cerrar el carrito."
            )

        carrito_cerrado = True

        # ----------------------------------------------------
        # 9. Confirmar salida del inventario
        # ----------------------------------------------------

        resultado_inventario = (
            confirmar_stock_pedido(
                pedido_id=pedido_id,
                usuario_id=usuario_id,
            )
        )

        if not resultado_inventario.get(
            "ok"
        ):

            raise RuntimeError(
                resultado_inventario.get(
                    "mensaje",
                    "No se pudo confirmar el inventario.",
                )
            )

        # ----------------------------------------------------
        # 10. Compra terminada correctamente
        # ----------------------------------------------------

        return {
            "ok": True,
            "mensaje":
                "Pedido confirmado correctamente.",
            "pedido_id":
                pedido_id,
            "numero_pedido":
                numero_pedido,
            "pago_id":
                pago_id,
            "subtotal":
                float(
                    subtotal
                ),
            "costo_entrega":
                float(
                    costo_entrega
                ),
            "total":
                float(
                    total
                ),
            "tipo_entrega":
                tipo_entrega,
            "entrega_id": entrega_id,
            "direccion_entrega": entrega['direccion_entrega'],
        }

    except Exception as error:

        # ----------------------------------------------------
        # COMPENSACIONES
        # ----------------------------------------------------

        if entrega_creada:
            try:
                compensar_entrega_pedido(pedido_id, usuario_id)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('No se pudo cancelar la entrega del pedido %s', pedido_id)

        if carrito_cerrado:

            try:

                reabrir_carrito_usuario(
                    usuario_id
                )

            except Exception:

                pass

        if pago_creado:

            try:

                cancelar_pago_checkout(
                    pedido_id=pedido_id,
                    usuario_id=usuario_id,
                    observacion=(
                        "Pago cancelado automáticamente "
                        "por error durante checkout."
                    ),
                )

            except Exception:

                pass

        if pedido_creado:

            try:

                actualizar_estado_pedido(
                    pedido_id,
                    "CANCELADO",
                )

            except Exception:

                pass

        if reserva_creada:

            try:

                liberar_stock_pedido(
                    pedido_id
                )

            except Exception:

                pass

        return {
            "ok": False,
            "mensaje":
                str(error),
        }

# ============================================================
# 20. CONFIRMAR CHECKOUT DESDE DATOS DE ENTREGA
# ============================================================

def confirmar_checkout_con_entrega(
    usuario_id,
    datos,
):
    """
    Punto de entrada seguro para confirmar una compra.

    El navegador informa únicamente las decisiones del usuario:

    - tipo de comprobante;
    - documento de facturación;
    - modalidad de entrega;
    - método de pago;
    - distancia calculada por el mapa;
    - transportista/servicio/destino seleccionados.

    IMPORTANTE:

    Antes de crear cualquier pedido se exige una
    facturación válida.

    BOLETA:
        El DNI se verifica nuevamente desde backend
        y debe corresponder al titular de la cuenta.

    FACTURA:
        El RUC se verifica nuevamente desde backend.

    El costo final de entrega también se vuelve a
    calcular en backend.
    """

    # ========================================================
    # 1. VALIDAR ESTRUCTURA DEL CHECKOUT
    # ========================================================

    if not isinstance(datos, dict):

        return {
            "ok": False,
            "mensaje":
                "Los datos del checkout no son válidos.",
        }

    if not usuario_id:

        return {
            "ok": False,
            "mensaje":
                "No se pudo identificar al usuario.",
        }

    # ========================================================
    # 2. FACTURACIÓN OBLIGATORIA
    # ========================================================
    #
    # Nunca confiamos únicamente en que JavaScript haya
    # verificado visualmente el DNI o RUC.
    #
    # El backend vuelve a ejecutar la validación oficial
    # antes de permitir crear el pedido.
    # ========================================================

    tipo_comprobante = str(
        datos.get(
            "tipo_comprobante",
            ""
        )
    ).strip().upper()

    documento_facturacion = str(
        datos.get(
            "documento_facturacion",
            ""
        )
    ).strip()

    # --------------------------------------------------------
    # Tipo de comprobante obligatorio
    # --------------------------------------------------------

    if tipo_comprobante not in {
        "BOLETA",
        "FACTURA",
    }:

        return {
            "ok": False,
            "mensaje":
                "Debes seleccionar Boleta o Factura antes de realizar la compra.",
        }

    # --------------------------------------------------------
    # Documento obligatorio
    # --------------------------------------------------------

    if not documento_facturacion:

        if tipo_comprobante == "BOLETA":

            mensaje_documento = (
                "Debes ingresar y verificar tu DNI "
                "para emitir la boleta."
            )

        else:

            mensaje_documento = (
                "Debes ingresar y verificar un RUC "
                "para emitir la factura."
            )

        return {
            "ok": False,
            "mensaje":
                mensaje_documento,
        }

    # --------------------------------------------------------
    # Import local.
    #
    # Identidad es responsable de validar y guardar los
    # datos fiscales del cliente.
    #
    # Se mantiene fuera de los imports globales para
    # reducir acoplamiento entre módulos.
    # --------------------------------------------------------

    from app.identidad.services import (
        registrar_facturacion_checkout,
    )

    resultado_facturacion = (
        registrar_facturacion_checkout(
            usuario_id=usuario_id,
            tipo=tipo_comprobante,
            documento=documento_facturacion,
        )
    )

    if not resultado_facturacion.get(
        "ok"
    ):

        return {
            "ok": False,
            "mensaje":
                resultado_facturacion.get(
                    "mensaje",
                    "No se pudieron verificar los datos de facturación.",
                ),
        }

    # ========================================================
    # 3. DATOS GENERALES DE ENTREGA Y PAGO
    # ========================================================

    tipo_entrega = str(
        datos.get(
            "tipo_entrega",
            ""
        )
    ).strip().upper()

    metodo_pago_id = datos.get(
        "metodo_pago_id"
    )

    entrega_validada = validar_entrega_confirmacion(usuario_id, datos)
    if not entrega_validada.get('ok'):
        return entrega_validada

    if not metodo_pago_id:

        return {
            "ok": False,
            "mensaje":
                "Debes seleccionar un método de pago.",
        }

    # ========================================================
    # 4. RECOJO EN LOCAL
    # ========================================================

    if tipo_entrega == "RECOJO_LOCAL":

        costo_entrega = entrega_validada['costo_entrega']

    # ========================================================
    # 5. DELIVERY LOCAL
    # ========================================================

    elif tipo_entrega == "DELIVERY_LOCAL":

        resultado_cotizacion = entrega_validada

        if not resultado_cotizacion.get(
            "ok"
        ):

            return resultado_cotizacion

        costo_entrega = (
            resultado_cotizacion[
                "costo_entrega"
            ]
        )

    # ========================================================
    # 6. TRANSPORTISTA
    # ========================================================

    elif tipo_entrega == "TRANSPORTISTA":

        resultado_cotizacion = entrega_validada

        if not resultado_cotizacion.get(
            "ok"
        ):

            return resultado_cotizacion

        costo_entrega = (
            resultado_cotizacion[
                "costo_entrega"
            ]
        )

    # ========================================================
    # 7. MODALIDAD DE ENTREGA INVÁLIDA
    # ========================================================

    else:

        return {
            "ok": False,
            "mensaje":
                "Selecciona una modalidad de entrega válida.",
        }

    # ========================================================
    # 8. EJECUTAR ORQUESTADOR DEFINITIVO
    # ========================================================

    resultado_checkout = confirmar_checkout(
        usuario_id=usuario_id,
        tipo_entrega=tipo_entrega,
        metodo_pago_id=metodo_pago_id,
        costo_entrega=costo_entrega,
        entrega=entrega_validada,
    )

    if not resultado_checkout.get(
        "ok"
    ):

        return resultado_checkout

    # ========================================================
    # 9. AGREGAR INFORMACIÓN DE FACTURACIÓN AL RESULTADO
    # ========================================================
    #
    # Esto será útil posteriormente para:
    #
    # - generar el comprobante PDF;
    # - enviar el correo;
    # - mostrar el resumen de compra.
    # ========================================================

    resultado_checkout[
        "tipo_comprobante"
    ] = tipo_comprobante

    resultado_checkout[
        "facturacion_id"
    ] = resultado_facturacion.get(
        "facturacion_id"
    )

    return resultado_checkout
