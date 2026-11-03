"""Lógica del módulo administrativo del catálogo comercial de SULPAA V2.

Responsabilidades:

- Comprobar el permiso real antes de cada lectura o escritura.
- Aplicar las reglas puras de ``validaciones.py``.
- Orquestar los repositorios de Comercio sin duplicar su SQL.
- Registrar cada cambio en la auditoría DESPUÉS de confirmarlo.
- Leer el stock real de Inventario sin modificarlo nunca.

El catálogo no tiene stock propio: las variantes consultan sus existencias y
los packs se calculan a partir de sus componentes. Esta separación es la misma
que ya usa la tienda, así que la administración y la venta ven los mismos
números.
"""

import logging
from decimal import Decimal

from app.admin.auditoria.services import registrar_evento
from app.admin.catalogo import repositories as repos
from app.admin.catalogo.imagenes import (
    eliminar_archivo_no_registrado,
    guardar_imagen_segura,
    normalizar_ruta_imagen,
)
from app.admin.catalogo.validaciones import (
    ErrorCatalogo,
    ESTADOS,
    MONEDA_POR_DEFECTO,
    ROLES_CATALOGO,
    TIPOS_PACK,
    TIPOS_UNIDAD,
    calcular_stock_pack_fijo,
    generar_slug,
    normalizar_booleano,
    normalizar_decimal,
    normalizar_entero,
    normalizar_estado,
    normalizar_fecha,
    normalizar_texto,
    validar_componentes_pack,
    validar_monto,
    validar_rango_precio,
    validar_reglas_pack,
)
from app.inventario.services import obtener_disponibilidad_variantes
from app.shared.pagination import crear_paginacion


logger = logging.getLogger(__name__)

# Recursos que comparten un formulario sencillo.
RECURSOS_SIMPLES = ("categorias", "sabores", "presentaciones")

ETIQUETAS_RECURSO = {
    "categorias": "Categoría",
    "sabores": "Sabor",
    "presentaciones": "Presentación",
}


def _listar_paginado(contador, listador, pagina, por_pagina, **filtros):
    """Ejecuta conteo y SELECT limitado con una página ya normalizada."""
    total = contador(**filtros)
    paginacion = crear_paginacion(total, pagina, por_pagina)
    elementos = listador(
        **filtros,
        limite=paginacion["por_pagina"],
        offset=paginacion["offset"],
    )
    return {"elementos": elementos, "paginacion": paginacion}

ETIQUETAS_TIPO_UNIDAD = {
    "ML": "Mililitros",
    "L": "Litros",
    "G": "Gramos",
    "KG": "Kilogramos",
    "UNIDAD": "Unidades",
}


# ============================================================
# PERMISOS Y AUDITORÍA
# ============================================================

def _validar_acceso(roles):
    """Niega el acceso a cualquier rol que no sea GERENTE o ADMINISTRADOR."""

    if not (set(ROLES_CATALOGO) & set(roles or [])):
        raise ErrorCatalogo(
            "No tienes permisos para administrar el catálogo."
        )


def _auditar(
    actor_id,
    roles,
    accion,
    entidad,
    entidad_id=None,
    anteriores=None,
    nuevos=None,
    detalle=None,
    direccion_ip=None,
):
    """Registra un cambio ya confirmado sin romper la operación."""

    registrar_evento(
        usuario_id=actor_id,
        modulo="catalogo",
        entidad=entidad,
        accion=accion,
        rol_actual=roles,
        entidad_id=entidad_id,
        tipo_operacion="ESCRITURA",
        detalle=detalle,
        datos_anteriores=anteriores,
        datos_nuevos=nuevos,
        direccion_ip=direccion_ip,
    )


def _traducir_error(error, mensaje_general):
    """Convierte un error interno en un mensaje seguro para la interfaz."""

    logger.exception(mensaje_general)
    return ErrorCatalogo(
        "No se pudo completar la operación. No se guardaron cambios."
    )


# ============================================================
# RESUMEN DEL PANEL
# ============================================================

def obtener_resumen(roles):
    """Devuelve los conteos del catálogo para la pantalla principal."""

    _validar_acceso(roles)
    return repos.contar_catalogo()


def obtener_selectores(roles):
    """Reúne las listas que usan los formularios del módulo."""

    _validar_acceso(roles)

    return {
        # Los formularios de edición también muestran relaciones inactivas.
        # El Service impide publicarlas, pero ocultarlas haría imposible
        # revisar o corregir registros históricos que todavía las usan.
        "categorias": repos.listar_simples("categorias"),
        "sabores": repos.listar_simples("sabores"),
        "presentaciones": repos.listar_simples("presentaciones"),
        "variantes": repos.listar_variantes_selector(),
        "productos": repos.listar_productos_selector(),
        "tipos_precio": repos.listar_tipos_precio(),
        "tipos_unidad": [
            (codigo, ETIQUETAS_TIPO_UNIDAD[codigo])
            for codigo in TIPOS_UNIDAD
        ],
        "tipos_pack": list(TIPOS_PACK),
    }


# ============================================================
# CATÁLOGOS SIMPLES
# ============================================================

def _validar_recurso(recurso):
    """Solo admite los tres catálogos simples conocidos."""

    if recurso not in RECURSOS_SIMPLES:
        raise ErrorCatalogo("El tipo de catálogo indicado no es válido.")
    return recurso


def _detalle_recurso(recurso, datos):
    """Normaliza los campos propios de categorías, sabores y presentaciones."""

    nombre = normalizar_texto(
        datos.get("nombre"), "El nombre", maximo=100
    )
    estado = normalizar_estado(datos.get("estado"))

    normalizado = {
        "nombre": nombre,
        "estado": estado,
    }

    if recurso == "categorias":
        normalizado["descripcion"] = normalizar_texto(
            datos.get("descripcion"),
            "La descripción",
            obligatorio=False,
            maximo=500,
        )
        normalizado["orden"] = normalizar_entero(
            datos.get("orden") or 0,
            "El orden",
            minimo=0,
            maximo=32767,
        )
    elif recurso == "sabores":
        normalizado["descripcion"] = normalizar_texto(
            datos.get("descripcion"),
            "La descripción",
            obligatorio=False,
            maximo=500,
        )
    else:
        tipo_unidad = str(datos.get("tipo_unidad") or "").strip().upper()
        if tipo_unidad not in TIPOS_UNIDAD:
            raise ErrorCatalogo(
                "El tipo de unidad debe ser ML, L, G, KG o UNIDAD."
            )
        normalizado["tipo_unidad"] = tipo_unidad
        normalizado["cantidad"] = normalizar_decimal(
            datos.get("cantidad"),
            "La cantidad",
            obligatorio=True,
            mayor_que_cero=True,
            maximo=Decimal("99999999.99"),
        )
        normalizado["descripcion"] = normalizar_texto(
            datos.get("descripcion"),
            "La descripción",
            obligatorio=False,
            maximo=255,
        )

    return normalizado


def _slug_unico(tabla, base, excluir_id=None):
    """Construye un slug libre agregando un número cuando hace falta."""

    candidato = base
    contador = 2

    while not repos.slug_disponible(tabla, candidato, excluir_id=excluir_id):
        candidato = f"{base[:165]}-{contador}"
        contador += 1

    return candidato


def listar_catalogo_simple(roles, recurso, estado=None, busqueda=None,
                           pagina=1, por_pagina=25):
    """Lista categorías, sabores o presentaciones con filtros válidos."""

    _validar_acceso(roles)
    recurso = _validar_recurso(recurso)

    if estado not in (None, "", *ESTADOS):
        raise ErrorCatalogo("El estado indicado no es válido.")

    filtros = {
        "recurso": recurso,
        "estado": estado or None,
        "busqueda": str(busqueda or "").strip() or None,
    }
    return _listar_paginado(
        repos.contar_simples, repos.listar_simples,
        pagina, por_pagina, **filtros
    )


def obtener_catalogo_simple(roles, recurso, registro_id):
    """Devuelve una fila concreta de un catálogo simple."""

    _validar_acceso(roles)
    recurso = _validar_recurso(recurso)
    return repos.obtener_simple(recurso, registro_id)


def crear_catalogo_simple(
    actor_id,
    roles,
    recurso,
    datos,
    direccion_ip=None,
):
    """Crea una categoría, sabor o presentación."""

    _validar_acceso(roles)
    recurso = _validar_recurso(recurso)
    normalizado = _detalle_recurso(recurso, datos)

    if recurso == "categorias":
        slug_pedido = str(datos.get("slug") or "").strip()
        base = generar_slug(slug_pedido or normalizado["nombre"])
        normalizado["slug"] = _slug_unico("categorias", base)

    try:
        resultado = repos.crear_simple(recurso, normalizado)
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(error, f"Falló la creación de {recurso}") from None

    _auditar(
        actor_id,
        roles,
        "CREAR",
        recurso,
        entidad_id=resultado.get("id"),
        nuevos=normalizado,
        detalle=f"Se creó {ETIQUETAS_RECURSO[recurso].lower()}.",
        direccion_ip=direccion_ip,
    )

    return resultado


def actualizar_catalogo_simple(
    actor_id,
    roles,
    recurso,
    registro_id,
    datos,
    direccion_ip=None,
):
    """Actualiza un catálogo simple conservando su historia."""

    _validar_acceso(roles)
    recurso = _validar_recurso(recurso)

    anterior = repos.obtener_simple(recurso, registro_id)
    if not anterior:
        raise ErrorCatalogo("El registro indicado no existe.")

    normalizado = _detalle_recurso(recurso, datos)

    if recurso == "categorias":
        slug_pedido = str(datos.get("slug") or "").strip()
        base = generar_slug(slug_pedido or normalizado["nombre"])
        normalizado["slug"] = _slug_unico(
            "categorias", base, excluir_id=registro_id
        )

    if (
        anterior.get("estado") == "ACTIVO"
        and normalizado["estado"] == "INACTIVO"
    ):
        referencias = repos.referencias_activas_simple(
            recurso, registro_id
        )
        if referencias:
            raise ErrorCatalogo(
                "No se puede desactivar: todavía existen registros activos "
                "que dependen de este elemento."
            )

    try:
        repos.actualizar_simple(recurso, registro_id, normalizado)
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló la actualización de {recurso} {registro_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "ACTUALIZAR",
        recurso,
        entidad_id=registro_id,
        anteriores={
            clave: str(anterior.get(clave))
            for clave in normalizado
        },
        nuevos=normalizado,
        detalle=f"Se actualizó {ETIQUETAS_RECURSO[recurso].lower()}.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "id": registro_id}


def cambiar_estado_catalogo_simple(
    actor_id,
    roles,
    recurso,
    registro_id,
    estado,
    direccion_ip=None,
):
    """Activa o desactiva un catálogo simple sin borrarlo."""

    _validar_acceso(roles)
    recurso = _validar_recurso(recurso)
    estado = normalizar_estado(estado)

    anterior = repos.obtener_simple(recurso, registro_id)
    if not anterior:
        raise ErrorCatalogo("El registro indicado no existe.")

    if estado == "INACTIVO":
        referencias = repos.referencias_activas_simple(
            recurso, registro_id
        )
        if referencias:
            raise ErrorCatalogo(
                "No se puede desactivar: todavía existen registros activos "
                "que dependen de este elemento."
            )

    try:
        repos.actualizar_simple(recurso, registro_id, {"estado": estado})
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló el cambio de estado de {recurso} {registro_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "CAMBIAR_ESTADO",
        recurso,
        entidad_id=registro_id,
        anteriores={"estado": anterior.get("estado")},
        nuevos={"estado": estado},
        detalle="Cambio de estado del catálogo.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "estado": estado}


# ============================================================
# PRODUCTOS
# ============================================================

def listar_productos(roles, estado=None, busqueda=None, categoria_id=None,
                      pagina=1, por_pagina=25):
    """Lista productos con su categoría y conteo de variantes."""

    _validar_acceso(roles)

    if estado not in (None, "", *ESTADOS):
        raise ErrorCatalogo("El estado indicado no es válido.")

    return _listar_paginado(
        repos.contar_productos, repos.listar_productos, pagina, por_pagina,
        estado=(estado or None),
        busqueda=(str(busqueda or "").strip() or None),
        categoria_id=(categoria_id or None),
    )


def obtener_producto(roles, producto_id):
    """Devuelve el producto con sus variantes e imágenes."""

    _validar_acceso(roles)
    return repos.obtener_producto(producto_id)


def _validar_categoria_para_publicar(categoria_id, estado):
    """Un producto activo solo puede vivir en una categoría activa."""

    categoria = repos.obtener_simple("categorias", categoria_id)
    if not categoria:
        raise ErrorCatalogo("La categoría indicada no existe.")

    if estado == "ACTIVO" and categoria.get("estado") != "ACTIVO":
        raise ErrorCatalogo(
            "No se puede publicar un producto en una categoría inactiva."
        )

    return categoria


def _detalle_producto(datos):
    """Normaliza los campos del formulario de productos."""

    nombre = normalizar_texto(
        datos.get("nombre"), "El nombre", maximo=150
    )
    descripcion = normalizar_texto(
        datos.get("descripcion"),
        "La descripción",
        obligatorio=False,
        maximo=5000,
    )
    estado = normalizar_estado(datos.get("estado"))

    try:
        categoria_id = int(datos.get("categoria_id") or 0)
    except (TypeError, ValueError):
        raise ErrorCatalogo("La categoría indicada no es válida.") from None

    if categoria_id <= 0:
        raise ErrorCatalogo("La categoría es obligatoria.")

    return {
        "nombre": nombre,
        "descripcion": descripcion,
        "estado": estado,
        "categoria_id": categoria_id,
    }


def crear_producto(
    actor_id,
    roles,
    datos,
    direccion_ip=None,
):
    """Crea un producto del catálogo comercial."""

    _validar_acceso(roles)
    normalizado = _detalle_producto(datos)
    _validar_categoria_para_publicar(
        normalizado["categoria_id"], normalizado["estado"]
    )

    base = generar_slug(datos.get("slug") or normalizado["nombre"])
    slug = _slug_unico("productos", base)

    try:
        resultado = repos.crear_producto(
            nombre=normalizado["nombre"],
            slug=slug,
            categoria_id=normalizado["categoria_id"],
            descripcion=normalizado["descripcion"],
            estado=normalizado["estado"],
        )
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(error, "Falló la creación del producto") from None

    _auditar(
        actor_id,
        roles,
        "CREAR",
        "productos",
        entidad_id=resultado.get("producto_id"),
        nuevos={**normalizado, "slug": slug},
        detalle="Se creó un producto.",
        direccion_ip=direccion_ip,
    )

    return resultado


def actualizar_producto(
    actor_id,
    roles,
    producto_id,
    datos,
    direccion_ip=None,
):
    """Actualiza un producto sin borrar sus variantes ni su historia."""

    _validar_acceso(roles)

    anterior = repos.obtener_producto(producto_id)
    if not anterior:
        raise ErrorCatalogo("El producto indicado no existe.")

    normalizado = _detalle_producto(datos)
    _validar_categoria_para_publicar(
        normalizado["categoria_id"], normalizado["estado"]
    )

    if (
        anterior.get("estado") == "ACTIVO"
        and normalizado["estado"] == "INACTIVO"
        and repos.producto_tiene_variantes_activas(producto_id)
    ):
        raise ErrorCatalogo(
            "No se puede desactivar el producto mientras tenga variantes "
            "activas. Desactiva primero sus variantes."
        )

    base = generar_slug(datos.get("slug") or normalizado["nombre"])
    slug = _slug_unico("productos", base, excluir_id=producto_id)

    try:
        repos.actualizar_producto(
            producto_id=producto_id,
            nombre=normalizado["nombre"],
            slug=slug,
            categoria_id=normalizado["categoria_id"],
            descripcion=normalizado["descripcion"],
            estado=normalizado["estado"],
        )
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló la actualización del producto {producto_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "ACTUALIZAR",
        "productos",
        entidad_id=producto_id,
        anteriores={
            "nombre": anterior.get("nombre"),
            "slug": anterior.get("slug"),
            "categoria_id": str(anterior.get("categoria_id")),
            "estado": anterior.get("estado"),
        },
        nuevos={**normalizado, "slug": slug},
        detalle="Se actualizó un producto.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "producto_id": producto_id}


def cambiar_estado_producto(
    actor_id,
    roles,
    producto_id,
    estado,
    direccion_ip=None,
):
    """Activa o desactiva un producto de forma lógica."""

    _validar_acceso(roles)
    estado = normalizar_estado(estado)

    anterior = repos.obtener_producto(producto_id)
    if not anterior:
        raise ErrorCatalogo("El producto indicado no existe.")

    if estado == "ACTIVO":
        _validar_categoria_para_publicar(
            anterior.get("categoria_id"), "ACTIVO"
        )
    elif repos.producto_tiene_variantes_activas(producto_id):
        raise ErrorCatalogo(
            "No se puede desactivar el producto mientras tenga variantes "
            "activas. Desactiva primero sus variantes."
        )

    try:
        repos.cambiar_estado_producto(producto_id, estado)
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló el cambio de estado del producto {producto_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "CAMBIAR_ESTADO",
        "productos",
        entidad_id=producto_id,
        anteriores={"estado": anterior.get("estado")},
        nuevos={"estado": estado},
        detalle="Cambio de estado del producto.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "estado": estado}


# ============================================================
# VARIANTES
# ============================================================

def listar_variantes(roles, estado=None, busqueda=None, producto_id=None,
                      pagina=1, por_pagina=25):
    """Lista variantes con precio vigente, imagen y estados relacionados."""

    _validar_acceso(roles)

    if estado not in (None, "", *ESTADOS):
        raise ErrorCatalogo("El estado indicado no es válido.")

    return _listar_paginado(
        repos.contar_variantes, repos.listar_variantes, pagina, por_pagina,
        estado=(estado or None),
        busqueda=(str(busqueda or "").strip() or None),
        producto_id=(producto_id or None),
    )


def obtener_variante(roles, variante_id):
    """Devuelve una variante con precios e imágenes."""

    _validar_acceso(roles)
    return repos.obtener_variante(variante_id)


def _detalle_variante(datos):
    """Normaliza los campos del formulario de variantes."""

    nombre_comercial = normalizar_texto(
        datos.get("nombre_comercial"),
        "El nombre comercial",
        maximo=180,
    )

    sku = normalizar_texto(
        datos.get("sku"), "El SKU", maximo=80
    ).upper()

    if any(caracter.isspace() for caracter in sku):
        raise ErrorCatalogo("El SKU no puede contener espacios.")

    try:
        producto_id = str(datos.get("producto_id") or "").strip()
        presentacion_id = int(datos.get("presentacion_id") or 0)
    except (TypeError, ValueError):
        raise ErrorCatalogo(
            "El producto o la presentación no son válidos."
        ) from None

    if not producto_id:
        raise ErrorCatalogo("El producto es obligatorio.")
    if presentacion_id <= 0:
        raise ErrorCatalogo("La presentación es obligatoria.")

    sabor_id = datos.get("sabor_id")
    if str(sabor_id or "").strip() == "":
        sabor_id = None
    else:
        try:
            sabor_id = int(sabor_id)
        except (TypeError, ValueError):
            raise ErrorCatalogo("El sabor indicado no es válido.") from None
        if sabor_id <= 0:
            raise ErrorCatalogo("El sabor indicado no es válido.")

    estado = normalizar_estado(datos.get("estado"))

    return {
        "producto_id": producto_id,
        "sabor_id": sabor_id,
        "presentacion_id": presentacion_id,
        "sku": sku,
        "nombre_comercial": nombre_comercial,
        "peso_gramos": normalizar_decimal(
            datos.get("peso_gramos"),
            "El peso",
            obligatorio=False,
            maximo=Decimal("99999999.99"),
        ),
        "largo_cm": normalizar_decimal(
            datos.get("largo_cm"),
            "El largo",
            obligatorio=False,
            maximo=Decimal("99999999.99"),
        ),
        "ancho_cm": normalizar_decimal(
            datos.get("ancho_cm"),
            "El ancho",
            obligatorio=False,
            maximo=Decimal("99999999.99"),
        ),
        "alto_cm": normalizar_decimal(
            datos.get("alto_cm"),
            "El alto",
            obligatorio=False,
            maximo=Decimal("99999999.99"),
        ),
        "estado": estado,
    }


def _validar_relaciones_variante(detalle):
    """Impide publicar variantes con producto, sabor o presentación inactivos."""

    if detalle["estado"] != "ACTIVO":
        return

    producto = repos.obtener_producto(detalle["producto_id"])
    if not producto:
        raise ErrorCatalogo("El producto indicado no existe.")
    if producto.get("estado") != "ACTIVO":
        raise ErrorCatalogo(
            "No se puede publicar una variante de un producto inactivo."
        )

    presentacion = repos.obtener_simple(
        "presentaciones", detalle["presentacion_id"]
    )
    if not presentacion:
        raise ErrorCatalogo("La presentación indicada no existe.")
    if presentacion.get("estado") != "ACTIVO":
        raise ErrorCatalogo(
            "No se puede publicar una variante con una presentación inactiva."
        )

    if detalle["sabor_id"] is not None:
        sabor = repos.obtener_simple("sabores", detalle["sabor_id"])
        if not sabor:
            raise ErrorCatalogo("El sabor indicado no existe.")
        if sabor.get("estado") != "ACTIVO":
            raise ErrorCatalogo(
                "No se puede publicar una variante con un sabor inactivo."
            )


def crear_variante(
    actor_id,
    roles,
    datos,
    direccion_ip=None,
):
    """Crea una variante y su artículo de venta en una sola transacción.

    Si la variante nace ACTIVA exige un precio inicial mayor que cero. La
    tienda necesita un precio vigente para poder mostrarla.
    """

    _validar_acceso(roles)
    detalle = _detalle_variante(datos)
    _validar_relaciones_variante(detalle)

    monto_inicial = None
    if str(datos.get("monto_inicial") or "").strip():
        monto_inicial = validar_monto(datos.get("monto_inicial"))

    if detalle["estado"] == "ACTIVO" and monto_inicial is None:
        raise ErrorCatalogo(
            "Una variante activa necesita un precio inicial mayor que cero."
        )

    try:
        resultado = repos.crear_variante(
            **detalle,
            actor_id=actor_id,
            monto_inicial=monto_inicial,
            moneda=MONEDA_POR_DEFECTO,
            tipo_precio_id=1,
        )
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(error, "Falló la creación de la variante") from None

    _auditar(
        actor_id,
        roles,
        "CREAR",
        "variantes",
        entidad_id=resultado.get("variante_id"),
        nuevos={
            **detalle,
            "monto_inicial": str(monto_inicial) if monto_inicial else None,
        },
        detalle="Se creó una variante y su artículo de venta.",
        direccion_ip=direccion_ip,
    )

    return resultado


def actualizar_variante(
    actor_id,
    roles,
    variante_id,
    datos,
    direccion_ip=None,
):
    """Actualiza una variante y sincroniza su artículo de venta."""

    _validar_acceso(roles)

    anterior = repos.obtener_variante(variante_id)
    if not anterior:
        raise ErrorCatalogo("La variante indicada no existe.")

    detalle = _detalle_variante(datos)
    _validar_relaciones_variante(detalle)

    if detalle["estado"] == "ACTIVO":
        precio = anterior.get("precio_actual")
        if precio is None or Decimal(str(precio)) <= 0:
            raise ErrorCatalogo(
                "No se puede activar una variante sin un precio vigente "
                "mayor que cero. Registra primero su precio."
            )

    if (
        anterior.get("estado") == "ACTIVO"
        and detalle["estado"] == "INACTIVO"
        and repos.variante_en_pack_activo(variante_id)
    ):
        raise ErrorCatalogo(
            "No se puede desactivar la variante mientras un pack activo "
            "dependa de ella. Ajusta primero ese pack."
        )

    try:
        repos.actualizar_variante(
            variante_id=variante_id,
            **detalle,
        )
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló la actualización de la variante {variante_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "ACTUALIZAR",
        "variantes",
        entidad_id=variante_id,
        anteriores={
            "sku": anterior.get("sku"),
            "nombre_comercial": anterior.get("nombre_comercial"),
            "estado": anterior.get("estado"),
            "producto_id": anterior.get("producto_id"),
            "sabor_id": str(anterior.get("sabor_id")),
            "presentacion_id": str(anterior.get("presentacion_id")),
        },
        nuevos=detalle,
        detalle="Se actualizó una variante.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "variante_id": variante_id}


def cambiar_estado_variante(
    actor_id,
    roles,
    variante_id,
    estado,
    direccion_ip=None,
):
    """Activa o desactiva una variante y su artículo de venta."""

    _validar_acceso(roles)
    estado = normalizar_estado(estado)

    anterior = repos.obtener_variante(variante_id)
    if not anterior:
        raise ErrorCatalogo("La variante indicada no existe.")

    if estado == "ACTIVO":
        _validar_relaciones_variante({
            "producto_id": anterior.get("producto_id"),
            "presentacion_id": anterior.get("presentacion_id"),
            "sabor_id": anterior.get("sabor_id"),
            "estado": "ACTIVO",
        })
        precio = anterior.get("precio_actual")
        if precio is None or Decimal(str(precio)) <= 0:
            raise ErrorCatalogo(
                "No se puede activar una variante sin un precio vigente "
                "mayor que cero. Registra primero su precio."
            )
    elif repos.variante_en_pack_activo(variante_id):
        raise ErrorCatalogo(
            "No se puede desactivar la variante mientras un pack activo "
            "dependa de ella. Ajusta primero ese pack."
        )

    try:
        repos.cambiar_estado_variante(variante_id, estado)
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló el cambio de estado de la variante {variante_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "CAMBIAR_ESTADO",
        "variantes",
        entidad_id=variante_id,
        anteriores={"estado": anterior.get("estado")},
        nuevos={"estado": estado},
        detalle="Cambio de estado de la variante.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "estado": estado}


# ============================================================
# PRECIOS
# ============================================================

def listar_precios_por_vencer(roles, dias=30):
    """Lista precios vigentes que terminarán pronto."""

    _validar_acceso(roles)
    dias = normalizar_entero(dias or 30, "Los días", minimo=1, maximo=365)
    return repos.listar_precios_por_vencer(dias)


def _detalle_precio(datos):
    """Normaliza monto, moneda, tipo y vigencia de un precio."""

    monto = validar_monto(datos.get("monto"))
    moneda = str(
        datos.get("moneda") or MONEDA_POR_DEFECTO
    ).strip().upper()

    if len(moneda) != 3 or not moneda.isalpha():
        raise ErrorCatalogo(
            "La moneda debe ser un código de tres letras, por ejemplo PEN."
        )

    try:
        tipo_precio_id = int(datos.get("tipo_precio_id") or 1)
    except (TypeError, ValueError):
        raise ErrorCatalogo("El tipo de precio no es válido.") from None

    if not repos.obtener_tipo_precio(tipo_precio_id):
        raise ErrorCatalogo("El tipo de precio indicado no existe o está inactivo.")

    desde = normalizar_fecha(
        datos.get("vigente_desde"), "La fecha de inicio"
    )
    hasta = normalizar_fecha(
        datos.get("vigente_hasta"),
        "La fecha de fin",
        obligatorio=False,
    )
    validar_rango_precio(desde, hasta)

    return {
        "monto": monto,
        "moneda": moneda,
        "tipo_precio_id": tipo_precio_id,
        "vigente_desde": desde,
        "vigente_hasta": hasta,
    }


def _crear_precio_articulo(
    actor_id,
    roles,
    articulo_venta_id,
    datos,
    entidad,
    entidad_id,
    direccion_ip=None,
):
    """Crea un precio para un artículo ya validado."""

    detalle = _detalle_precio(datos)

    try:
        resultado = repos.crear_precio(
            articulo_venta_id=articulo_venta_id,
            monto=detalle["monto"],
            moneda=detalle["moneda"],
            tipo_precio_id=detalle["tipo_precio_id"],
            vigente_desde=detalle["vigente_desde"],
            vigente_hasta=detalle["vigente_hasta"],
            actor_id=actor_id,
        )
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(error, "Falló la creación del precio") from None

    _auditar(
        actor_id,
        roles,
        "CREAR_PRECIO",
        entidad,
        entidad_id=entidad_id,
        nuevos={
            "precio_id": resultado.get("precio_id"),
            "monto": str(detalle["monto"]),
            "moneda": detalle["moneda"],
            "tipo_precio_id": detalle["tipo_precio_id"],
            "vigente_desde": detalle["vigente_desde"],
            "vigente_hasta": detalle["vigente_hasta"],
        },
        detalle="Se registró un precio con su vigencia.",
        direccion_ip=direccion_ip,
    )

    return resultado


def crear_precio_variante(
    actor_id,
    roles,
    variante_id,
    datos,
    direccion_ip=None,
):
    """Registra un precio nuevo para una variante sin tocar los anteriores."""

    _validar_acceso(roles)

    variante = repos.obtener_variante(variante_id)
    if not variante:
        raise ErrorCatalogo("La variante indicada no existe.")

    articulo = repos.obtener_articulo_por_variante(variante_id)
    if not articulo:
        raise ErrorCatalogo(
            "La variante no tiene artículo de venta. Actualízala primero."
        )

    return _crear_precio_articulo(
        actor_id,
        roles,
        articulo.get("articulo_venta_id"),
        datos,
        entidad="precios",
        entidad_id=variante_id,
        direccion_ip=direccion_ip,
    )


def crear_precio_pack(
    actor_id,
    roles,
    pack_id,
    datos,
    direccion_ip=None,
):
    """Registra un precio nuevo para un pack."""

    _validar_acceso(roles)

    pack = repos.obtener_pack(pack_id)
    if not pack:
        raise ErrorCatalogo("El pack indicado no existe.")

    articulo = repos.obtener_articulo_por_pack(pack_id)
    if not articulo:
        raise ErrorCatalogo(
            "El pack no tiene artículo de venta. Actualízalo primero."
        )

    return _crear_precio_articulo(
        actor_id,
        roles,
        articulo.get("articulo_venta_id"),
        datos,
        entidad="precios",
        entidad_id=pack_id,
        direccion_ip=direccion_ip,
    )


def cerrar_precio(
    actor_id,
    roles,
    precio_id,
    vigente_hasta,
    direccion_ip=None,
):
    """Finaliza una vigencia sin borrar el precio histórico."""

    _validar_acceso(roles)

    hasta = normalizar_fecha(vigente_hasta, "La fecha de cierre")

    try:
        resultado = repos.cerrar_precio(precio_id, hasta)
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló el cierre del precio {precio_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "CERRAR_PRECIO",
        "precios",
        entidad_id=precio_id,
        nuevos={"vigente_hasta": hasta},
        detalle="Se cerró la vigencia de un precio.",
        direccion_ip=direccion_ip,
    )

    return resultado


# ============================================================
# IMÁGENES
# ============================================================

def listar_imagenes(
    roles,
    estado=None,
    busqueda=None,
    producto_id=None,
    variante_id=None,
    pagina=1,
    por_pagina=25,
):
    """Lista las imágenes del catálogo con su destino."""

    _validar_acceso(roles)

    if estado not in (None, "", *ESTADOS):
        raise ErrorCatalogo("El estado indicado no es válido.")

    return _listar_paginado(
        repos.contar_imagenes, repos.listar_imagenes, pagina, por_pagina,
        estado=(estado or None),
        busqueda=(str(busqueda or "").strip() or None),
        producto_id=(producto_id or None),
        variante_id=(variante_id or None),
    )


def obtener_imagen(roles, imagen_id):
    """Devuelve una imagen concreta."""

    _validar_acceso(roles)
    return repos.obtener_imagen(imagen_id)


def _validar_destino_imagen(producto_id, variante_id):
    """Exige exactamente un destino existente para la imagen."""

    producto_id = str(producto_id or "").strip() or None
    variante_id = str(variante_id or "").strip() or None

    if bool(producto_id) == bool(variante_id):
        raise ErrorCatalogo(
            "Selecciona un producto o una variante, pero no ambos."
        )

    if producto_id:
        if not repos.obtener_producto(producto_id):
            raise ErrorCatalogo("El producto indicado no existe.")
    else:
        if not repos.obtener_variante(variante_id):
            raise ErrorCatalogo("La variante indicada no existe.")

    return producto_id, variante_id


def _detalle_imagen(datos):
    """Normaliza texto alternativo, orden y estado de una imagen."""

    texto = normalizar_texto(
        datos.get("texto_alternativo"),
        "El texto alternativo",
        obligatorio=True,
        maximo=255,
    )

    return {
        "texto_alternativo": texto,
        "es_principal": normalizar_booleano(datos.get("es_principal")),
        "orden": normalizar_entero(
            datos.get("orden") or 0,
            "El orden",
            minimo=0,
            maximo=32767,
        ),
        "estado": normalizar_estado(datos.get("estado")),
    }


def crear_imagen(
    actor_id,
    roles,
    datos,
    archivo=None,
    direccion_ip=None,
):
    """Crea una imagen subiendo un archivo o indicando una ruta estática."""

    _validar_acceso(roles)

    producto_id, variante_id = _validar_destino_imagen(
        datos.get("producto_id"), datos.get("variante_id")
    )
    detalle = _detalle_imagen(datos)

    tiene_archivo = bool(getattr(archivo, "filename", ""))
    ruta_manual = str(datos.get("ruta") or "").strip()

    if tiene_archivo:
        ruta = guardar_imagen_segura(archivo)
    elif ruta_manual:
        ruta = normalizar_ruta_imagen(ruta_manual)
    else:
        raise ErrorCatalogo(
            "Selecciona una imagen o indica una ruta estática img/..."
        )

    try:
        resultado = repos.crear_imagen(
            producto_id=producto_id,
            variante_id=variante_id,
            ruta=ruta,
            texto_alternativo=detalle["texto_alternativo"],
            es_principal=detalle["es_principal"],
            orden=detalle["orden"],
            estado=detalle["estado"],
        )
    except ValueError as error:
        if tiene_archivo:
            eliminar_archivo_no_registrado(ruta)
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        if tiene_archivo:
            eliminar_archivo_no_registrado(ruta)
        raise _traducir_error(error, "Falló la creación de la imagen") from None

    _auditar(
        actor_id,
        roles,
        "CREAR",
        "imagenes_catalogo",
        entidad_id=resultado.get("imagen_id"),
        nuevos={
            **detalle,
            "ruta": ruta,
            "producto_id": producto_id,
            "variante_id": variante_id,
        },
        detalle="Se agregó una imagen al catálogo.",
        direccion_ip=direccion_ip,
    )

    return resultado


def actualizar_imagen(
    actor_id,
    roles,
    imagen_id,
    datos,
    archivo=None,
    direccion_ip=None,
):
    """Actualiza los datos de una imagen y, si se envía, su archivo."""

    _validar_acceso(roles)

    anterior = repos.obtener_imagen(imagen_id)
    if not anterior:
        raise ErrorCatalogo("La imagen indicada no existe.")

    detalle = _detalle_imagen(datos)

    tiene_archivo = bool(getattr(archivo, "filename", ""))
    ruta_manual = str(datos.get("ruta") or "").strip()

    if tiene_archivo:
        ruta = guardar_imagen_segura(archivo)
    elif ruta_manual:
        ruta = normalizar_ruta_imagen(ruta_manual)
    else:
        ruta = anterior.get("ruta")

    try:
        repos.actualizar_imagen(
            imagen_id=imagen_id,
            ruta=ruta,
            texto_alternativo=detalle["texto_alternativo"],
            es_principal=detalle["es_principal"],
            orden=detalle["orden"],
            estado=detalle["estado"],
        )
    except ValueError as error:
        if tiene_archivo:
            eliminar_archivo_no_registrado(ruta)
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        if tiene_archivo:
            eliminar_archivo_no_registrado(ruta)
        raise _traducir_error(
            error, f"Falló la actualización de la imagen {imagen_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "ACTUALIZAR",
        "imagenes_catalogo",
        entidad_id=imagen_id,
        anteriores={"ruta": anterior.get("ruta")},
        nuevos={**detalle, "ruta": ruta},
        detalle="Se actualizó una imagen del catálogo.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "imagen_id": imagen_id}


def cambiar_estado_imagen(
    actor_id,
    roles,
    imagen_id,
    estado,
    direccion_ip=None,
):
    """Activa o desactiva una imagen sin borrar el archivo físico."""

    _validar_acceso(roles)
    estado = normalizar_estado(estado)

    anterior = repos.obtener_imagen(imagen_id)
    if not anterior:
        raise ErrorCatalogo("La imagen indicada no existe.")

    try:
        repos.cambiar_estado_imagen(imagen_id, estado)
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló el cambio de estado de la imagen {imagen_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "CAMBIAR_ESTADO",
        "imagenes_catalogo",
        entidad_id=imagen_id,
        anteriores={"estado": anterior.get("estado")},
        nuevos={"estado": estado},
        detalle="Cambio de estado de una imagen.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "estado": estado}


# ============================================================
# PACKS
# ============================================================

def listar_packs(roles, estado=None, busqueda=None, pagina=1, por_pagina=25):
    """Lista packs con su precio vigente y conteo de relaciones."""

    _validar_acceso(roles)

    if estado not in (None, "", *ESTADOS):
        raise ErrorCatalogo("El estado indicado no es válido.")

    return _listar_paginado(
        repos.contar_packs, repos.listar_packs, pagina, por_pagina,
        estado=(estado or None),
        busqueda=(str(busqueda or "").strip() or None),
    )


def obtener_pack(roles, pack_id):
    """Devuelve el pack con componentes, reglas, permitidas y precios."""

    _validar_acceso(roles)
    return repos.obtener_pack(pack_id)


def _normalizar_componentes(componentes):
    """Convierte la entrada del formulario en filas seguras."""

    resultado = []

    for componente in componentes or []:
        variante_id = str(componente.get("variante_id") or "").strip()
        if not variante_id:
            continue
        resultado.append({
            "variante_id": variante_id,
            "cantidad": componente.get("cantidad"),
        })

    return resultado


def _normalizar_reglas(reglas):
    """Convierte la entrada del formulario en reglas seguras."""

    resultado = []

    for regla in reglas or []:
        if (
            str(regla.get("numero_sabores") or "").strip() == ""
            and str(regla.get("unidades_por_sabor") or "").strip() == ""
        ):
            continue
        resultado.append({
            "numero_sabores": regla.get("numero_sabores"),
            "unidades_por_sabor": regla.get("unidades_por_sabor"),
        })

    return resultado


def _normalizar_permitidas(permitidas):
    """Quita repetidos y valores vacíos de las variantes permitidas."""

    resultado = []
    vistos = set()

    for variante_id in permitidas or []:
        variante_id = str(variante_id or "").strip()
        if not variante_id or variante_id in vistos:
            continue
        vistos.add(variante_id)
        resultado.append(variante_id)

    return resultado


def _detalle_pack(datos):
    """Normaliza los campos generales del formulario de packs."""

    nombre = normalizar_texto(
        datos.get("nombre"), "El nombre", maximo=150
    )

    tipo = str(datos.get("tipo") or "").strip().upper()
    if tipo not in TIPOS_PACK:
        raise ErrorCatalogo("El tipo de pack debe ser FIJO o PERSONALIZABLE.")

    estado = normalizar_estado(datos.get("estado"))

    return {
        "nombre": nombre,
        "tipo": tipo,
        "cantidad_unidades": normalizar_entero(
            datos.get("cantidad_unidades"),
            "La cantidad de unidades",
            minimo=1,
            maximo=32767,
        ),
        "descripcion": normalizar_texto(
            datos.get("descripcion"),
            "La descripción",
            obligatorio=False,
            maximo=5000,
        ),
        "peso_embalaje_gramos": normalizar_decimal(
            datos.get("peso_embalaje_gramos") or 0,
            "El peso del embalaje",
            obligatorio=False,
            maximo=Decimal("99999999.99"),
        ) or Decimal("0.00"),
        "estado": estado,
    }


def _validar_variantes_de_pack(ids, publicar):
    """Comprueba que las variantes existan y estén activas si se publica."""

    for variante_id in ids:
        variante = repos.obtener_variante(variante_id)
        if not variante:
            raise ErrorCatalogo(
                "Una de las variantes seleccionadas no existe."
            )
        if publicar and variante.get("estado") != "ACTIVO":
            raise ErrorCatalogo(
                "No se puede publicar un pack con variantes inactivas."
            )


def _preparar_pack(datos):
    """Valida la composición del pack según su tipo."""

    detalle = _detalle_pack(datos)
    componentes = _normalizar_componentes(datos.get("componentes"))
    reglas = _normalizar_reglas(datos.get("reglas"))
    permitidas = _normalizar_permitidas(datos.get("permitidas"))

    if detalle["tipo"] == "FIJO":
        validar_componentes_pack(
            detalle["cantidad_unidades"], componentes
        )
        if reglas or permitidas:
            raise ErrorCatalogo(
                "Un pack fijo no lleva reglas ni variantes permitidas."
            )
        _validar_variantes_de_pack(
            [item["variante_id"] for item in componentes],
            detalle["estado"] == "ACTIVO",
        )
        componentes = [
            {
                "variante_id": item["variante_id"],
                "cantidad": int(str(item["cantidad"]).strip()),
            }
            for item in componentes
        ]
        reglas = []
        permitidas = []
    else:
        validar_reglas_pack(detalle["cantidad_unidades"], reglas)
        if componentes:
            raise ErrorCatalogo(
                "Un pack personalizable no lleva componentes fijos."
            )
        if not permitidas:
            raise ErrorCatalogo(
                "Un pack personalizable necesita variantes permitidas."
            )
        _validar_variantes_de_pack(
            permitidas,
            detalle["estado"] == "ACTIVO",
        )
        reglas = [
            {
                "numero_sabores": int(str(regla["numero_sabores"]).strip()),
                "unidades_por_sabor": int(
                    str(regla["unidades_por_sabor"]).strip()
                ),
            }
            for regla in reglas
        ]
        componentes = []

    return detalle, componentes, reglas, permitidas


def crear_pack(
    actor_id,
    roles,
    datos,
    direccion_ip=None,
):
    """Crea un pack con su composición en una sola transacción."""

    _validar_acceso(roles)
    detalle, componentes, reglas, permitidas = _preparar_pack(datos)

    base = generar_slug(datos.get("slug") or detalle["nombre"])
    slug = _slug_unico("packs", base)

    try:
        resultado = repos.crear_pack(
            **detalle,
            slug=slug,
            componentes=componentes,
            reglas=reglas,
            permitidas=permitidas,
        )
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(error, "Falló la creación del pack") from None

    _auditar(
        actor_id,
        roles,
        "CREAR",
        "packs",
        entidad_id=resultado.get("pack_id"),
        nuevos={
            **detalle,
            "slug": slug,
            "componentes": componentes,
            "reglas": reglas,
            "permitidas": permitidas,
        },
        detalle="Se creó un pack.",
        direccion_ip=direccion_ip,
    )

    return resultado


def actualizar_pack(
    actor_id,
    roles,
    pack_id,
    datos,
    direccion_ip=None,
):
    """Actualiza un pack conservando su artículo y su historia de precios."""

    _validar_acceso(roles)

    anterior = repos.obtener_pack(pack_id)
    if not anterior:
        raise ErrorCatalogo("El pack indicado no existe.")

    detalle, componentes, reglas, permitidas = _preparar_pack(datos)

    componentes_anteriores = {
        (str(item.get("variante_id")), int(item.get("cantidad") or 0))
        for item in (anterior.get("componentes") or [])
    }
    componentes_nuevos = {
        (str(item.get("variante_id")), int(item.get("cantidad") or 0))
        for item in componentes
    }
    reglas_anteriores = {
        (
            int(item.get("numero_sabores") or 0),
            int(item.get("unidades_por_sabor") or 0),
        )
        for item in (anterior.get("reglas") or [])
        if item.get("estado") == "ACTIVO"
    }
    reglas_nuevas = {
        (int(item["numero_sabores"]), int(item["unidades_por_sabor"]))
        for item in reglas
    }
    permitidas_anteriores = {
        str(item.get("variante_id"))
        for item in (anterior.get("permitidas") or [])
        if item.get("estado") == "ACTIVO"
    }
    permitidas_nuevas = set(permitidas)

    # Un pedido conserva su propio snapshot, pero también su artículo de venta.
    # Para no reescribir la definición comercial que originó ese historial, la
    # composición queda congelada desde el primer pedido. Los datos descriptivos
    # y el estado del pack sí pueden seguir administrándose.
    composicion_cambio = (
        str(anterior.get("tipo") or "").upper() != detalle["tipo"]
        or componentes_anteriores != componentes_nuevos
        or reglas_anteriores != reglas_nuevas
        or permitidas_anteriores != permitidas_nuevas
    )
    if composicion_cambio and repos.pack_tiene_pedidos(pack_id):
        raise ErrorCatalogo(
            "La composición no puede cambiar porque el pack ya aparece en "
            "pedidos históricos. Puedes editar su nombre, descripción, "
            "estado y precios, o crear un pack nuevo."
        )

    base = generar_slug(datos.get("slug") or detalle["nombre"])
    slug = _slug_unico("packs", base, excluir_id=pack_id)

    try:
        repos.actualizar_pack(
            pack_id=pack_id,
            **detalle,
            slug=slug,
            componentes=componentes,
            reglas=reglas,
            permitidas=permitidas,
            reemplazar_composicion=composicion_cambio,
        )
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló la actualización del pack {pack_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "ACTUALIZAR",
        "packs",
        entidad_id=pack_id,
        anteriores={
            "nombre": anterior.get("nombre"),
            "tipo": anterior.get("tipo"),
            "estado": anterior.get("estado"),
        },
        nuevos={
            **detalle,
            "slug": slug,
            "componentes": componentes,
            "reglas": reglas,
            "permitidas": permitidas,
        },
        detalle="Se actualizó un pack.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "pack_id": pack_id}


def cambiar_estado_pack(
    actor_id,
    roles,
    pack_id,
    estado,
    direccion_ip=None,
):
    """Activa o desactiva un pack y su artículo de venta."""

    _validar_acceso(roles)
    estado = normalizar_estado(estado)

    anterior = repos.obtener_pack(pack_id)
    if not anterior:
        raise ErrorCatalogo("El pack indicado no existe.")

    if estado == "ACTIVO":
        tipo = str(anterior.get("tipo") or "").upper()
        if tipo == "FIJO":
            ids = [
                item["variante_id"]
                for item in (anterior.get("componentes") or [])
            ]
            if not ids:
                raise ErrorCatalogo(
                    "Un pack fijo activo necesita al menos una variante."
                )
            _validar_variantes_de_pack(ids, True)
        else:
            ids = [
                item["variante_id"]
                for item in (anterior.get("permitidas") or [])
                if item.get("estado") == "ACTIVO"
            ]
            if not ids:
                raise ErrorCatalogo(
                    "Un pack personalizable activo necesita variantes "
                    "permitidas."
                )
            _validar_variantes_de_pack(ids, True)

    try:
        repos.cambiar_estado_pack(pack_id, estado)
    except ValueError as error:
        raise ErrorCatalogo(str(error)) from error
    except Exception as error:
        raise _traducir_error(
            error, f"Falló el cambio de estado del pack {pack_id}"
        ) from None

    _auditar(
        actor_id,
        roles,
        "CAMBIAR_ESTADO",
        "packs",
        entidad_id=pack_id,
        anteriores={"estado": anterior.get("estado")},
        nuevos={"estado": estado},
        detalle="Cambio de estado de un pack.",
        direccion_ip=direccion_ip,
    )

    return {"ok": True, "estado": estado}


# ============================================================
# STOCK DE SOLO LECTURA
# ============================================================

def obtener_stock_variante(roles, variante_id):
    """Muestra el stock físico, reservado y disponible de una variante."""

    _validar_acceso(roles)

    disponibilidad = obtener_disponibilidad_variantes([variante_id])
    return disponibilidad.get(
        variante_id,
        {
            "stock_fisico": 0,
            "stock_reservado": 0,
            "stock_disponible": 0,
            "disponible": False,
        },
    )


def obtener_stock_pack(roles, pack_id):
    """Calcula el stock de un pack a partir de sus componentes reales.

    Los packs no tienen existencias propias. Esta función solo lee el stock
    de Inventario y aplica la misma regla de la tienda:
    ``min(stock_disponible // cantidad_requerida)``.
    """

    _validar_acceso(roles)

    pack = repos.obtener_pack(pack_id)
    if not pack:
        raise ErrorCatalogo("El pack indicado no existe.")

    if str(pack.get("tipo") or "").upper() == "FIJO":
        componentes = pack.get("componentes") or []
        ids = [item["variante_id"] for item in componentes]
        disponibilidad = (
            obtener_disponibilidad_variantes(ids) if ids else {}
        )

        detalle = []
        for componente in componentes:
            stock = disponibilidad.get(
                componente["variante_id"],
                {
                    "stock_fisico": 0,
                    "stock_reservado": 0,
                    "stock_disponible": 0,
                    "disponible": False,
                },
            )
            detalle.append({**componente, **stock})

        return {
            "tipo": "FIJO",
            "componentes": detalle,
            "packs_disponibles": calcular_stock_pack_fijo(
                componentes, disponibilidad
            ),
        }

    permitidas = pack.get("permitidas") or []
    ids = [item["variante_id"] for item in permitidas]
    disponibilidad = (
        obtener_disponibilidad_variantes(ids) if ids else {}
    )

    detalle = [
        {
            **item,
            **disponibilidad.get(
                item["variante_id"],
                {
                    "stock_fisico": 0,
                    "stock_reservado": 0,
                    "stock_disponible": 0,
                    "disponible": False,
                },
            ),
        }
        for item in permitidas
    ]

    return {
        "tipo": "PERSONALIZABLE",
        "permitidas": detalle,
        "packs_disponibles": None,
    }
