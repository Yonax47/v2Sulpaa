"""Rutas HTTP del módulo administrativo del catálogo comercial.

URLs principales:

- ``/admin/catalogo/``              panel del catálogo
- ``/admin/catalogo/categorias/``   categorías
- ``/admin/catalogo/sabores/``      sabores
- ``/admin/catalogo/presentaciones/`` presentaciones
- ``/admin/catalogo/productos/``    productos
- ``/admin/catalogo/variantes/``    variantes, precios y stock
- ``/admin/catalogo/imagenes/``     imágenes del catálogo
- ``/admin/catalogo/packs/``        packs fijos y personalizables

Las rutas solo coordinan formularios, mensajes y redirecciones. Los permisos,
las reglas de negocio y la auditoría viven en ``services.py``.
"""

import logging

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.admin.catalogo.services import (
    ETIQUETAS_RECURSO,
    ErrorCatalogo,
    actualizar_catalogo_simple,
    actualizar_imagen,
    actualizar_pack,
    actualizar_producto,
    actualizar_variante,
    cambiar_estado_catalogo_simple,
    cambiar_estado_imagen,
    cambiar_estado_pack,
    cambiar_estado_producto,
    cambiar_estado_variante,
    cerrar_precio,
    crear_catalogo_simple,
    crear_imagen,
    crear_pack,
    crear_precio_pack,
    crear_precio_variante,
    crear_producto,
    crear_variante,
    listar_catalogo_simple,
    listar_imagenes,
    listar_packs,
    listar_precios_por_vencer,
    listar_productos,
    listar_variantes,
    obtener_catalogo_simple,
    obtener_imagen,
    obtener_pack,
    obtener_producto,
    obtener_resumen,
    obtener_selectores,
    obtener_stock_pack,
    obtener_stock_variante,
    obtener_variante,
)
from app.shared.decorators import login_required, role_required
from app.shared.network import obtener_ip_cliente

logger = logging.getLogger(__name__)

admin_catalogo_bp = Blueprint(
    "admin_catalogo",
    __name__,
    url_prefix="/admin/catalogo",
    template_folder="../../../templates",
)

ROLES = ("GERENTE", "ADMINISTRADOR")


# ============================================================
# AYUDANTES INTERNOS
# ============================================================

def _roles():
    """Roles vigentes de la sesión (ya revalidados por el decorador)."""

    return session.get("roles") or []


def _actor():
    """Identificador del usuario que realiza el cambio."""

    return session.get("usuario_id")


def _ip():
    """IP confiable para la auditoría."""

    return obtener_ip_cliente(request)


def _destino_local(valor, por_defecto):
    """Acepta únicamente una ruta interna para evitar redirecciones externas."""

    destino = str(valor or "").strip()
    if destino.startswith("/") and not destino.startswith("//"):
        return destino
    return por_defecto


def _datos_simples():
    """Reúne los campos comunes de un catálogo simple."""

    return {
        "nombre": request.form.get("nombre"),
        "slug": request.form.get("slug"),
        "descripcion": request.form.get("descripcion"),
        "orden": request.form.get("orden"),
        "tipo_unidad": request.form.get("tipo_unidad"),
        "cantidad": request.form.get("cantidad"),
        "estado": request.form.get("estado", "ACTIVO"),
    }


def _datos_producto():
    """Reúne los campos del formulario de productos."""

    return {
        "nombre": request.form.get("nombre"),
        "slug": request.form.get("slug"),
        "categoria_id": request.form.get("categoria_id"),
        "descripcion": request.form.get("descripcion"),
        "estado": request.form.get("estado", "ACTIVO"),
    }


def _datos_variante():
    """Reúne los campos del formulario de variantes."""

    return {
        "producto_id": request.form.get("producto_id"),
        "sabor_id": request.form.get("sabor_id"),
        "presentacion_id": request.form.get("presentacion_id"),
        "sku": request.form.get("sku"),
        "nombre_comercial": request.form.get("nombre_comercial"),
        "peso_gramos": request.form.get("peso_gramos"),
        "largo_cm": request.form.get("largo_cm"),
        "ancho_cm": request.form.get("ancho_cm"),
        "alto_cm": request.form.get("alto_cm"),
        "estado": request.form.get("estado", "ACTIVO"),
        "monto_inicial": request.form.get("monto_inicial"),
    }


def _datos_precio():
    """Reúne los campos del formulario de precio."""

    return {
        "monto": request.form.get("monto"),
        "moneda": request.form.get("moneda", "PEN"),
        "tipo_precio_id": request.form.get("tipo_precio_id", "1"),
        "vigente_desde": request.form.get("vigente_desde"),
        "vigente_hasta": request.form.get("vigente_hasta"),
    }


def _datos_imagen():
    """Reúne los campos del formulario de imágenes."""

    return {
        "producto_id": request.form.get("producto_id"),
        "variante_id": request.form.get("variante_id"),
        "ruta": request.form.get("ruta"),
        "texto_alternativo": request.form.get("texto_alternativo"),
        "es_principal": request.form.get("es_principal"),
        "orden": request.form.get("orden"),
        "estado": request.form.get("estado", "ACTIVO"),
    }


def _datos_pack():
    """Reúne los campos del formulario de packs, incluidas sus listas."""

    variantes = request.form.getlist("componente_variante")
    cantidades = request.form.getlist("componente_cantidad")
    sabores = request.form.getlist("regla_sabores")
    unidades = request.form.getlist("regla_unidades")

    componentes = [
        {"variante_id": variante_id, "cantidad": cantidad}
        for variante_id, cantidad in zip(variantes, cantidades)
    ]

    reglas = [
        {"numero_sabores": numero, "unidades_por_sabor": unidad}
        for numero, unidad in zip(sabores, unidades)
    ]

    return {
        "nombre": request.form.get("nombre"),
        "slug": request.form.get("slug"),
        "tipo": request.form.get("tipo"),
        "cantidad_unidades": request.form.get("cantidad_unidades"),
        "descripcion": request.form.get("descripcion"),
        "peso_embalaje_gramos": request.form.get("peso_embalaje_gramos"),
        "estado": request.form.get("estado", "ACTIVO"),
        "componentes": componentes,
        "reglas": reglas,
        "permitidas": request.form.getlist("permitidas"),
    }


def _urls_simples(recurso):
    """Nombres de endpoint usados por las plantillas genéricas."""

    singular, endpoint_nuevo = {
        "categorias": ("categoria", "nueva_categoria"),
        "sabores": ("sabor", "nuevo_sabor"),
        "presentaciones": ("presentacion", "nueva_presentacion"),
    }[recurso]

    return {
        "lista": f"admin_catalogo.{recurso}",
        "nuevo": f"admin_catalogo.{endpoint_nuevo}",
        "editar": f"admin_catalogo.{singular}",
        "estado": f"admin_catalogo.estado_{singular}",
    }


def _listar_simple(recurso):
    """Lista un catálogo simple con sus filtros."""

    estado = request.args.get("estado", "")
    busqueda = request.args.get("q", "")

    registros = []
    try:
        registros = listar_catalogo_simple(
            _roles(), recurso, estado=estado, busqueda=busqueda
        )
    except ErrorCatalogo as error:
        flash(str(error), "danger")

    return render_template(
        "admin/catalogo/simple_lista.html",
        recurso=recurso,
        etiqueta=ETIQUETAS_RECURSO[recurso],
        etiqueta_plural={
            "categorias": "Categorías",
            "sabores": "Sabores",
            "presentaciones": "Presentaciones",
        }[recurso],
        registros=registros,
        estado=estado,
        busqueda=busqueda,
        urls=_urls_simples(recurso),
        admin_activo="catalogo",
        subactivo=recurso,
    )


def _formulario_simple(recurso, registro_id=None):
    """Muestra y guarda el formulario de un catálogo simple."""

    registro = None
    if registro_id is not None:
        registro = obtener_catalogo_simple(_roles(), recurso, registro_id)
        if not registro:
            abort(404)

    if request.method == "POST":
        try:
            if registro_id is None:
                resultado = crear_catalogo_simple(
                    _actor(),
                    _roles(),
                    recurso,
                    _datos_simples(),
                    direccion_ip=_ip(),
                )
                flash(f"{ETIQUETAS_RECURSO[recurso]} creada correctamente.", "success")
                return redirect(
                    url_for(_urls_simples(recurso)["editar"], registro_id=resultado["id"])
                )
            actualizar_catalogo_simple(
                _actor(),
                _roles(),
                recurso,
                registro_id,
                _datos_simples(),
                direccion_ip=_ip(),
            )
            flash(f"{ETIQUETAS_RECURSO[recurso]} actualizada correctamente.", "success")
            return redirect(
                url_for(_urls_simples(recurso)["editar"], registro_id=registro_id)
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    return render_template(
        "admin/catalogo/simple_formulario.html",
        recurso=recurso,
        etiqueta=ETIQUETAS_RECURSO[recurso],
        registro=registro,
        urls=_urls_simples(recurso),
        tipos_unidad=obtener_selectores(_roles())["tipos_unidad"],
        admin_activo="catalogo",
        subactivo=recurso,
    )


def _cambiar_estado_simple(recurso, registro_id):
    """Activa o desactiva un catálogo simple."""

    try:
        cambiar_estado_catalogo_simple(
            _actor(),
            _roles(),
            recurso,
            registro_id,
            request.form.get("estado"),
            direccion_ip=_ip(),
        )
        flash("Estado actualizado correctamente.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el cambio de estado de %s", recurso)
        flash("No se pudo cambiar el estado. No se guardaron cambios.", "danger")

    return redirect(url_for(_urls_simples(recurso)["lista"]))


# ============================================================
# PANEL
# ============================================================

@admin_catalogo_bp.route("/", methods=["GET"])
@login_required
@role_required(*ROLES)
def panel():
    """Resumen del catálogo y precios próximos a vencer."""

    resumen = {}
    por_vencer = []

    try:
        resumen = obtener_resumen(_roles())
        por_vencer = listar_precios_por_vencer(_roles(), 30)
    except ErrorCatalogo as error:
        flash(str(error), "danger")

    return render_template(
        "admin/catalogo/panel.html",
        resumen=resumen,
        por_vencer=por_vencer,
        admin_activo="catalogo",
        subactivo="panel",
    )


# ============================================================
# CATÁLOGOS SIMPLES
# ============================================================

@admin_catalogo_bp.route("/categorias/", methods=["GET"])
@login_required
@role_required(*ROLES)
def categorias():
    """Lista las categorías comerciales."""

    return _listar_simple("categorias")


@admin_catalogo_bp.route("/categorias/nuevo", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def nueva_categoria():
    """Formulario de alta de categoría."""

    return _formulario_simple("categorias")


@admin_catalogo_bp.route("/categorias/<int:registro_id>", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def categoria(registro_id):
    """Edición de una categoría."""

    return _formulario_simple("categorias", registro_id)


@admin_catalogo_bp.route(
    "/categorias/<int:registro_id>/estado", methods=["POST"]
)
@login_required
@role_required(*ROLES)
def estado_categoria(registro_id):
    """Activa o desactiva una categoría."""

    return _cambiar_estado_simple("categorias", registro_id)


@admin_catalogo_bp.route("/sabores/", methods=["GET"])
@login_required
@role_required(*ROLES)
def sabores():
    """Lista los sabores comerciales."""

    return _listar_simple("sabores")


@admin_catalogo_bp.route("/sabores/nuevo", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def nuevo_sabor():
    """Formulario de alta de sabor."""

    return _formulario_simple("sabores")


@admin_catalogo_bp.route("/sabores/<int:registro_id>", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def sabor(registro_id):
    """Edición de un sabor."""

    return _formulario_simple("sabores", registro_id)


@admin_catalogo_bp.route("/sabores/<int:registro_id>/estado", methods=["POST"])
@login_required
@role_required(*ROLES)
def estado_sabor(registro_id):
    """Activa o desactiva un sabor."""

    return _cambiar_estado_simple("sabores", registro_id)


@admin_catalogo_bp.route("/presentaciones/", methods=["GET"])
@login_required
@role_required(*ROLES)
def presentaciones():
    """Lista las presentaciones comerciales."""

    return _listar_simple("presentaciones")


@admin_catalogo_bp.route("/presentaciones/nuevo", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def nueva_presentacion():
    """Formulario de alta de presentación."""

    return _formulario_simple("presentaciones")


@admin_catalogo_bp.route(
    "/presentaciones/<int:registro_id>", methods=["GET", "POST"]
)
@login_required
@role_required(*ROLES)
def presentacion(registro_id):
    """Edición de una presentación."""

    return _formulario_simple("presentaciones", registro_id)


@admin_catalogo_bp.route(
    "/presentaciones/<int:registro_id>/estado", methods=["POST"]
)
@login_required
@role_required(*ROLES)
def estado_presentacion(registro_id):
    """Activa o desactiva una presentación."""

    return _cambiar_estado_simple("presentaciones", registro_id)


# ============================================================
# PRODUCTOS
# ============================================================

@admin_catalogo_bp.route("/productos/", methods=["GET"])
@login_required
@role_required(*ROLES)
def productos():
    """Lista los productos con filtros por estado, categoría y búsqueda."""

    estado = request.args.get("estado", "")
    categoria_id = request.args.get("categoria_id", "")
    busqueda = request.args.get("q", "")

    productos_lista = []
    selectores = {"categorias": []}
    try:
        productos_lista = listar_productos(
            _roles(),
            estado=estado,
            busqueda=busqueda,
            categoria_id=categoria_id or None,
        )
        selectores = obtener_selectores(_roles())
    except ErrorCatalogo as error:
        flash(str(error), "danger")

    return render_template(
        "admin/catalogo/productos_lista.html",
        productos=productos_lista,
        categorias=selectores.get("categorias") or [],
        estado=estado,
        categoria_id=categoria_id,
        busqueda=busqueda,
        admin_activo="catalogo",
        subactivo="productos",
    )


@admin_catalogo_bp.route("/productos/nuevo", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def nuevo_producto():
    """Formulario de alta de producto."""

    if request.method == "POST":
        try:
            resultado = crear_producto(
                _actor(), _roles(), _datos_producto(), direccion_ip=_ip()
            )
            flash("Producto creado correctamente.", "success")
            return redirect(
                url_for(
                    "admin_catalogo.producto",
                    producto_id=resultado["producto_id"],
                )
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    return render_template(
        "admin/catalogo/producto_formulario.html",
        producto=None,
        categorias=obtener_selectores(_roles())["categorias"],
        admin_activo="catalogo",
        subactivo="productos",
    )


@admin_catalogo_bp.route("/productos/<producto_id>", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def producto(producto_id):
    """Edición de un producto con sus variantes e imágenes."""

    actual = obtener_producto(_roles(), producto_id)
    if not actual:
        abort(404)

    if request.method == "POST":
        try:
            actualizar_producto(
                _actor(),
                _roles(),
                producto_id,
                _datos_producto(),
                direccion_ip=_ip(),
            )
            flash("Producto actualizado correctamente.", "success")
            return redirect(
                url_for("admin_catalogo.producto", producto_id=producto_id)
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    actual = obtener_producto(_roles(), producto_id)

    return render_template(
        "admin/catalogo/producto_formulario.html",
        producto=actual,
        categorias=obtener_selectores(_roles())["categorias"],
        admin_activo="catalogo",
        subactivo="productos",
    )


@admin_catalogo_bp.route("/productos/<producto_id>/estado", methods=["POST"])
@login_required
@role_required(*ROLES)
def estado_producto(producto_id):
    """Activa o desactiva un producto."""

    try:
        cambiar_estado_producto(
            _actor(),
            _roles(),
            producto_id,
            request.form.get("estado"),
            direccion_ip=_ip(),
        )
        flash("Estado del producto actualizado.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el cambio de estado del producto %s", producto_id)
        flash("No se pudo cambiar el estado. No se guardaron cambios.", "danger")

    return redirect(
        url_for("admin_catalogo.producto", producto_id=producto_id)
    )


# ============================================================
# VARIANTES
# ============================================================

@admin_catalogo_bp.route("/variantes/", methods=["GET"])
@login_required
@role_required(*ROLES)
def variantes():
    """Lista las variantes con su precio vigente y su imagen principal."""

    estado = request.args.get("estado", "")
    producto_id = request.args.get("producto_id", "")
    busqueda = request.args.get("q", "")

    variantes_lista = []
    productos_selector = []
    try:
        variantes_lista = listar_variantes(
            _roles(),
            estado=estado,
            busqueda=busqueda,
            producto_id=producto_id or None,
        )
        productos_selector = obtener_selectores(_roles())["productos"]
    except ErrorCatalogo as error:
        flash(str(error), "danger")

    return render_template(
        "admin/catalogo/variantes_lista.html",
        variantes=variantes_lista,
        productos=productos_selector,
        estado=estado,
        producto_id=producto_id,
        busqueda=busqueda,
        admin_activo="catalogo",
        subactivo="variantes",
    )


@admin_catalogo_bp.route("/variantes/nuevo", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def nueva_variante():
    """Formulario de alta de variante con su precio inicial."""

    if request.method == "POST":
        try:
            resultado = crear_variante(
                _actor(), _roles(), _datos_variante(), direccion_ip=_ip()
            )
            flash("Variante creada correctamente.", "success")
            return redirect(
                url_for(
                    "admin_catalogo.variante",
                    variante_id=resultado["variante_id"],
                )
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    selectores = obtener_selectores(_roles())

    return render_template(
        "admin/catalogo/variante_formulario.html",
        variante=None,
        producto_id=request.args.get("producto_id", ""),
        productos=selectores["productos"],
        sabores=selectores["sabores"],
        presentaciones=selectores["presentaciones"],
        admin_activo="catalogo",
        subactivo="variantes",
    )


@admin_catalogo_bp.route("/variantes/<variante_id>", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def variante(variante_id):
    """Detalle de una variante: datos, precios, imágenes y stock real."""

    actual = obtener_variante(_roles(), variante_id)
    if not actual:
        abort(404)

    if request.method == "POST":
        try:
            actualizar_variante(
                _actor(),
                _roles(),
                variante_id,
                _datos_variante(),
                direccion_ip=_ip(),
            )
            flash("Variante actualizada correctamente.", "success")
            return redirect(
                url_for("admin_catalogo.variante", variante_id=variante_id)
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    actual = obtener_variante(_roles(), variante_id)
    selectores = obtener_selectores(_roles())

    try:
        stock = obtener_stock_variante(_roles(), variante_id)
    except ErrorCatalogo as error:
        flash(str(error), "danger")
        stock = None

    return render_template(
        "admin/catalogo/variante_formulario.html",
        variante=actual,
        producto_id=actual.get("producto_id"),
        productos=selectores["productos"],
        sabores=selectores["sabores"],
        presentaciones=selectores["presentaciones"],
        tipos_precio=selectores["tipos_precio"],
        stock=stock,
        imagenes=actual.get("imagenes") or [],
        precios=actual.get("precios") or [],
        admin_activo="catalogo",
        subactivo="variantes",
    )


@admin_catalogo_bp.route("/variantes/<variante_id>/estado", methods=["POST"])
@login_required
@role_required(*ROLES)
def estado_variante(variante_id):
    """Activa o desactiva una variante."""

    try:
        cambiar_estado_variante(
            _actor(),
            _roles(),
            variante_id,
            request.form.get("estado"),
            direccion_ip=_ip(),
        )
        flash("Estado de la variante actualizado.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el cambio de estado de la variante %s", variante_id)
        flash("No se pudo cambiar el estado. No se guardaron cambios.", "danger")

    return redirect(
        url_for("admin_catalogo.variante", variante_id=variante_id)
    )


@admin_catalogo_bp.route("/variantes/<variante_id>/precios", methods=["POST"])
@login_required
@role_required(*ROLES)
def precio_variante(variante_id):
    """Registra un precio nuevo para la variante."""

    try:
        crear_precio_variante(
            _actor(),
            _roles(),
            variante_id,
            _datos_precio(),
            direccion_ip=_ip(),
        )
        flash("Precio registrado correctamente.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el alta de precio de la variante %s", variante_id)
        flash("No se pudo registrar el precio. No se guardaron cambios.", "danger")

    return redirect(
        url_for("admin_catalogo.variante", variante_id=variante_id, _anchor="precios")
    )


@admin_catalogo_bp.route("/variantes/<variante_id>/imagenes", methods=["POST"])
@login_required
@role_required(*ROLES)
def imagen_variante(variante_id):
    """Agrega una imagen a la variante."""

    datos = _datos_imagen()
    datos["variante_id"] = variante_id
    datos["producto_id"] = None

    try:
        crear_imagen(
            _actor(),
            _roles(),
            datos,
            archivo=request.files.get("archivo"),
            direccion_ip=_ip(),
        )
        flash("Imagen agregada correctamente.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el alta de imagen de la variante %s", variante_id)
        flash("No se pudo agregar la imagen. No se guardaron cambios.", "danger")

    return redirect(
        url_for("admin_catalogo.variante", variante_id=variante_id, _anchor="imagenes")
    )


# ============================================================
# PRECIOS
# ============================================================

@admin_catalogo_bp.route("/precios/<precio_id>/cerrar", methods=["POST"])
@login_required
@role_required(*ROLES)
def cerrar_precio_ruta(precio_id):
    """Cierra la vigencia de un precio sin borrar su historia."""

    destino = _destino_local(
        request.form.get("volver_a"),
        url_for("admin_catalogo.panel"),
    )

    try:
        cerrar_precio(
            _actor(),
            _roles(),
            precio_id,
            request.form.get("vigente_hasta"),
            direccion_ip=_ip(),
        )
        flash("Vigencia del precio cerrada.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el cierre del precio %s", precio_id)
        flash("No se pudo cerrar el precio. No se guardaron cambios.", "danger")

    return redirect(destino)


# ============================================================
# IMÁGENES
# ============================================================

@admin_catalogo_bp.route("/imagenes/", methods=["GET"])
@login_required
@role_required(*ROLES)
def imagenes():
    """Lista las imágenes del catálogo."""

    estado = request.args.get("estado", "")
    busqueda = request.args.get("q", "")

    imagenes_lista = []
    try:
        imagenes_lista = listar_imagenes(
            _roles(), estado=estado, busqueda=busqueda
        )
    except ErrorCatalogo as error:
        flash(str(error), "danger")

    return render_template(
        "admin/catalogo/imagenes_lista.html",
        imagenes=imagenes_lista,
        estado=estado,
        busqueda=busqueda,
        admin_activo="catalogo",
        subactivo="imagenes",
    )


@admin_catalogo_bp.route("/imagenes/nueva", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def nueva_imagen():
    """Alta de imagen para un producto o una variante."""

    if request.method == "POST":
        try:
            resultado = crear_imagen(
                _actor(),
                _roles(),
                _datos_imagen(),
                archivo=request.files.get("archivo"),
                direccion_ip=_ip(),
            )
            flash("Imagen agregada correctamente.", "success")
            return redirect(
                url_for(
                    "admin_catalogo.imagen",
                    imagen_id=resultado["imagen_id"],
                )
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    selectores = obtener_selectores(_roles())

    return render_template(
        "admin/catalogo/imagen_formulario.html",
        imagen=None,
        productos=selectores["productos"],
        variantes=selectores["variantes"],
        admin_activo="catalogo",
        subactivo="imagenes",
    )


@admin_catalogo_bp.route("/imagenes/<imagen_id>", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def imagen(imagen_id):
    """Edición de una imagen existente."""

    actual = obtener_imagen(_roles(), imagen_id)
    if not actual:
        abort(404)

    if request.method == "POST":
        try:
            actualizar_imagen(
                _actor(),
                _roles(),
                imagen_id,
                _datos_imagen(),
                archivo=request.files.get("archivo"),
                direccion_ip=_ip(),
            )
            flash("Imagen actualizada correctamente.", "success")
            return redirect(
                url_for("admin_catalogo.imagen", imagen_id=imagen_id)
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    actual = obtener_imagen(_roles(), imagen_id)
    selectores = obtener_selectores(_roles())

    return render_template(
        "admin/catalogo/imagen_formulario.html",
        imagen=actual,
        productos=selectores["productos"],
        variantes=selectores["variantes"],
        admin_activo="catalogo",
        subactivo="imagenes",
    )


@admin_catalogo_bp.route("/imagenes/<imagen_id>/estado", methods=["POST"])
@login_required
@role_required(*ROLES)
def estado_imagen(imagen_id):
    """Activa o desactiva una imagen."""

    try:
        cambiar_estado_imagen(
            _actor(),
            _roles(),
            imagen_id,
            request.form.get("estado"),
            direccion_ip=_ip(),
        )
        flash("Estado de la imagen actualizado.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el cambio de estado de la imagen %s", imagen_id)
        flash("No se pudo cambiar el estado. No se guardaron cambios.", "danger")

    destino = _destino_local(
        request.form.get("volver_a"),
        url_for("admin_catalogo.imagenes"),
    )
    return redirect(destino)


# ============================================================
# PACKS
# ============================================================

@admin_catalogo_bp.route("/packs/", methods=["GET"])
@login_required
@role_required(*ROLES)
def packs():
    """Lista los packs con su precio vigente."""

    estado = request.args.get("estado", "")
    busqueda = request.args.get("q", "")

    packs_lista = []
    try:
        packs_lista = listar_packs(
            _roles(), estado=estado, busqueda=busqueda
        )
    except ErrorCatalogo as error:
        flash(str(error), "danger")

    return render_template(
        "admin/catalogo/packs_lista.html",
        packs=packs_lista,
        estado=estado,
        busqueda=busqueda,
        admin_activo="catalogo",
        subactivo="packs",
    )


@admin_catalogo_bp.route("/packs/nuevo", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def nuevo_pack():
    """Formulario de alta de pack."""

    if request.method == "POST":
        try:
            resultado = crear_pack(
                _actor(), _roles(), _datos_pack(), direccion_ip=_ip()
            )
            flash("Pack creado correctamente.", "success")
            return redirect(
                url_for(
                    "admin_catalogo.pack",
                    pack_id=resultado["pack_id"],
                )
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    return render_template(
        "admin/catalogo/pack_formulario.html",
        pack=None,
        variantes=obtener_selectores(_roles())["variantes"],
        admin_activo="catalogo",
        subactivo="packs",
    )


@admin_catalogo_bp.route("/packs/<pack_id>", methods=["GET", "POST"])
@login_required
@role_required(*ROLES)
def pack(pack_id):
    """Detalle de un pack con su composición, precios y stock calculado."""

    actual = obtener_pack(_roles(), pack_id)
    if not actual:
        abort(404)

    if request.method == "POST":
        try:
            actualizar_pack(
                _actor(),
                _roles(),
                pack_id,
                _datos_pack(),
                direccion_ip=_ip(),
            )
            flash("Pack actualizado correctamente.", "success")
            return redirect(
                url_for("admin_catalogo.pack", pack_id=pack_id)
            )
        except ErrorCatalogo as error:
            flash(str(error), "danger")

    actual = obtener_pack(_roles(), pack_id)

    try:
        stock = obtener_stock_pack(_roles(), pack_id)
    except ErrorCatalogo as error:
        flash(str(error), "danger")
        stock = None

    return render_template(
        "admin/catalogo/pack_formulario.html",
        pack=actual,
        variantes=obtener_selectores(_roles())["variantes"],
        tipos_precio=obtener_selectores(_roles())["tipos_precio"],
        stock=stock,
        precios=actual.get("precios") or [],
        admin_activo="catalogo",
        subactivo="packs",
    )


@admin_catalogo_bp.route("/packs/<pack_id>/estado", methods=["POST"])
@login_required
@role_required(*ROLES)
def estado_pack(pack_id):
    """Activa o desactiva un pack."""

    try:
        cambiar_estado_pack(
            _actor(),
            _roles(),
            pack_id,
            request.form.get("estado"),
            direccion_ip=_ip(),
        )
        flash("Estado del pack actualizado.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el cambio de estado del pack %s", pack_id)
        flash("No se pudo cambiar el estado. No se guardaron cambios.", "danger")

    return redirect(
        url_for("admin_catalogo.pack", pack_id=pack_id)
    )


@admin_catalogo_bp.route("/packs/<pack_id>/precios", methods=["POST"])
@login_required
@role_required(*ROLES)
def precio_pack(pack_id):
    """Registra un precio nuevo para el pack."""

    try:
        crear_precio_pack(
            _actor(),
            _roles(),
            pack_id,
            _datos_precio(),
            direccion_ip=_ip(),
        )
        flash("Precio registrado correctamente.", "success")
    except ErrorCatalogo as error:
        flash(str(error), "danger")
    except Exception:
        logger.exception("Falló el alta de precio del pack %s", pack_id)
        flash("No se pudo registrar el precio. No se guardaron cambios.", "danger")

    return redirect(
        url_for("admin_catalogo.pack", pack_id=pack_id, _anchor="precios")
    )
