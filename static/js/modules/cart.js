/* ============================================================
SULPAA V2 - CARRITO LATERAL (MÓDULO REUTILIZABLE)
============================================================

Este archivo controla TODO el carrito de compras del cliente:

- abrir y cerrar el panel lateral;
- mostrar los productos reales del carrito;
- aumentar, disminuir y eliminar cantidades;
- actualizar el contador del navbar;
- agregar productos desde cualquier página (tienda, favoritos
  o ficha de producto).

IDEA IMPORTANTE:

El carrito se dibuja en UN solo lugar (el componente
cart_drawer.html) y se maneja con UN solo archivo (este).
Así evitamos tener varias versiones distintas del carrito.

El backend SIEMPRE vuelve a validar el stock y el precio.
Este archivo solo mejora la experiencia del usuario.
============================================================ */

(function () {
    "use strict";

    // ========================================================
    // 1. RUTAS DE LA API DEL CARRITO
    // ========================================================
    // Centralizamos las direcciones para no repetirlas en el
    // código. Si algún día cambia una ruta, se cambia aquí.

    const RUTAS = {
        listar: "/api/carrito",
        agregar: "/api/carrito/agregar",
        actualizar: "/api/carrito/actualizar",
        eliminar: "/api/carrito/eliminar",
    };


    // ========================================================
    // 2. UTILIDADES PEQUEÑAS
    // ========================================================

    // Convierte un valor a número. Si no es válido, devuelve
    // el valor por defecto.
    function numero(valor, porDefecto = 0) {
        const n = Number(valor);
        return Number.isFinite(n) ? n : porDefecto;
    }

    // Da formato de dinero peruano: S/ 12.50
    function dinero(valor) {
        return `S/ ${numero(valor).toFixed(2)}`;
    }

    // Evita que un texto con caracteres especiales (<, >, ")
    // rompa el HTML. Se usa antes de insertar datos del backend.
    function escaparHTML(valor) {
        const div = document.createElement("div");
        div.textContent = String(valor == null ? "" : valor);
        return div.innerHTML;
    }

    // Quita tildes y mayúsculas para comparar textos con
    // tranquilidad. Ejemplo: "Café" -> "cafe".
    function normalizar(valor) {
        return String(valor || "")
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim();
    }


    // ========================================================
    // 3. NOTIFICACIONES (TOAST)
    // ========================================================
    // Un pequeño aviso que aparece abajo a la derecha para
    // confirmar o avisar de un error.
    // Se expone como window.SulpaaToast para que otros archivos
    // (por ejemplo store.js) lo reutilicen sin duplicar código.

    let temporizadorToast = null;

    function mostrarToast(mensaje, tipo = "success") {
        let toast = document.querySelector("[data-store-toast]");

        if (!toast) {
            toast = document.createElement("div");
            toast.className = "store-toast";
            toast.dataset.storeToast = "";
            toast.setAttribute("role", "status");
            toast.setAttribute("aria-live", "polite");
            document.body.appendChild(toast);
        }

        toast.classList.remove("is-success", "is-error", "is-visible");
        toast.classList.add(tipo === "error" ? "is-error" : "is-success");
        toast.textContent = mensaje;

        window.requestAnimationFrame(() => {
            toast.classList.add("is-visible");
        });

        window.clearTimeout(temporizadorToast);
        temporizadorToast = window.setTimeout(() => {
            toast.classList.remove("is-visible");
        }, 3500);
    }

    window.SulpaaToast = { show: mostrarToast };


    // ========================================================
    // 4. IMÁGENES REALES DE LOS PRODUCTOS
    // ========================================================
    // La base de datos todavía no guarda fotos por variante.
    // Por eso usamos las imágenes reales que ya existen en el
    // proyecto. Si ninguna coincide, mostramos un dibujo
    // neutro (placeholder), nunca una imagen inventada.

    const IMAGEN_POR_SABOR = {
        cafe: "img/BotellaCafe.webp",
        jamaica: "img/Botellaflordejamaica.webp",
        kion: "img/Botellakion.webp",
        limon: "img/Botellalimon.webp",
    };

    const IMAGEN_PACK_POR_SABOR = {
        cafe: "img/Pack6unidadescafe.jpg",
        jamaica: "img/Pack6unidadesJamaica.jpg",
        kion: "img/Pack6unidadeskion.jpg",
        limon: "img/Pack6unidadeslimon.jpg",
    };

    const IMAGEN_BARRIL = "img/Barrilsulpaa.webp";
    const IMAGEN_BOTELLA_LITRO = "img/Botellalitrosulpaa.webp";
    const IMAGEN_PACK_MIXTO = "img/Packmixto.jpg";

    // Base de la carpeta static. La calculamos desde el propio
    // componente para no depender de rutas escritas a mano.
    function baseEstatica() {
        const drawer = document.querySelector("[data-cart-drawer]");
        return drawer?.dataset.cartStatic || "/static/";
    }

    // Dirección de la tienda. También la lee el componente para
    // no escribir rutas a mano en JavaScript.
    function urlTienda() {
        const drawer = document.querySelector("[data-cart-drawer]");
        return drawer?.dataset.cartStoreUrl || "/tienda";
    }

    // Decide qué imagen corresponde a un producto del carrito.
    // Devuelve una URL completa o null si no hay imagen real.
    function resolverImagen(item) {
        const base = baseEstatica();

        // El backend ya resuelve la imagen con las mismas reglas
        // que Tienda, Ficha y Favoritos (app/comercio/imagenes.py).
        // Si viene, la usamos tal cual.
        if (item && item.imagen) {
            return base + item.imagen;
        }

        // Respaldo local (por si algún dato llegara sin imagen).
        const esPack = String(item.tipo || "").toUpperCase() === "PACK";
        const texto = normalizar(item.sabor || item.nombre || "");
        const presentacion = normalizar(item.presentacion || "");

        // --- Packs ---
        if (esPack) {
            for (const sabor in IMAGEN_PACK_POR_SABOR) {
                if (texto.includes(sabor)) {
                    return base + IMAGEN_PACK_POR_SABOR[sabor];
                }
            }
            return base + IMAGEN_PACK_MIXTO;
        }

        // --- Barriles (cambian de forma, no de sabor) ---
        if (presentacion.includes("barril")) {
            return base + IMAGEN_BARRIL;
        }

        // --- Botellas con imagen propia por sabor ---
        for (const sabor in IMAGEN_POR_SABOR) {
            if (texto.includes(sabor)) {
                return base + IMAGEN_POR_SABOR[sabor];
            }
        }

        // --- Botellas de 1 litro (imagen genérica real) ---
        if (presentacion.includes("1 l") || presentacion.includes("litro")) {
            return base + IMAGEN_BOTELLA_LITRO;
        }

        // Sin imagen real disponible.
        return null;
    }

    // Placeholder neutro: un dibujo simple de botella, sin
    // representar ningún sabor en concreto.
    function placeholderImagen() {
        return (
            '<span class="store-cart-thumb-fallback" aria-hidden="true">' +
            '<svg viewBox="0 0 24 40" width="26" height="42" fill="none">' +
            '<path d="M9 2h6v4l2 4v24a4 4 0 0 1-4 4h-2a4 4 0 0 1-4-4V10l2-4V2Z"' +
            ' stroke="currentColor" stroke-width="1.6"/>' +
            '<path d="M9 16h6" stroke="currentColor" stroke-width="1.6"/>' +
            "</svg>" +
            "</span>"
        );
    }


    // ========================================================
    // 5. ESTADO Y ELEMENTOS DEL CARRITO
    // ========================================================

    const elemento = {
        drawer: null,
        overlay: null,
        cerrar: null,
        continuar: null,
        contenido: null,
        subtotal: null,
        loading: null,
    };

    let inicializado = false;
    let cargandoInicial = false;

    // Guardamos los ids de artículos que se están agregando en
    // este momento. Así evitamos enviar la misma solicitud dos
    // veces si el usuario pulsa el botón varias veces rápido.
    const agregando = new Set();


    function cargarElementos() {
        elemento.drawer = document.querySelector("[data-cart-drawer]");
        elemento.overlay = document.querySelector("[data-cart-overlay]");
        elemento.cerrar = document.querySelector("[data-cart-close]");
        elemento.continuar = document.querySelector("[data-cart-continue]");
        elemento.contenido = document.querySelector("[data-cart-content]");
        elemento.subtotal = document.querySelector("[data-cart-subtotal]");
        elemento.loading = document.querySelector("[data-cart-loading]");
    }


    // ========================================================
    // 6. ABRIR Y CERRAR EL PANEL
    // ========================================================

    function abrir() {
        if (!elemento.drawer || !elemento.overlay) {
            return;
        }

        elemento.overlay.hidden = false;

        window.requestAnimationFrame(() => {
            elemento.drawer.classList.add("is-open");
        });

        elemento.drawer.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";

        // Llevamos el foco al botón de cerrar para que el
        // usuario pueda cerrar con Enter o con Escape.
        elemento.cerrar?.focus();
    }


    function cerrar() {
        if (!elemento.drawer || !elemento.overlay) {
            return;
        }

        elemento.drawer.classList.remove("is-open");
        elemento.drawer.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";

        // Esperamos a que termine la animación antes de
        // ocultar por completo la capa oscura.
        window.setTimeout(() => {
            if (!elemento.drawer.classList.contains("is-open")) {
                elemento.overlay.hidden = true;
            }
        }, 320);
    }


    // ========================================================
    // 7. CONTADOR DEL NAVBAR
    // ========================================================
    // Actualiza TODOS los elementos con data-cart-count.
    // Si la cantidad es 0, ocultamos el globito.

    function actualizarContador(cantidad) {
        const total = numero(cantidad);
        const contadores = document.querySelectorAll("[data-cart-count]");

        contadores.forEach((contador) => {
            contador.textContent = String(total);
            contador.hidden = total <= 0;
        });
    }


    // ========================================================
    // 8. PETICIÓN JSON SEGURA
    // ========================================================
    // Envía una petición al backend y devuelve el JSON.
    // Si el servidor responde con error, lanza un mensaje claro.

    async function pedirJSON(url, opciones = {}) {
        const respuesta = await fetch(url, {
            credentials: "same-origin",
            ...opciones,
            headers: {
                "Content-Type": "application/json",
                ...(opciones.headers || {}),
            },
        });

        let datos = {};

        try {
            datos = await respuesta.json();
        } catch {
            datos = {
                ok: false,
                mensaje: "El servidor devolvió una respuesta inválida.",
            };
        }

        if (!respuesta.ok) {
            throw new Error(
                datos.mensaje || "No se pudo completar la operación."
            );
        }

        return datos;
    }


    // ========================================================
    // 9. MARCAR UN PRODUCTO COMO "CARGANDO"
    // ========================================================
    // Mientras se actualiza una línea, bloqueamos sus botones
    // para evitar envíos repetidos.

    function marcarItemCargando(itemElement, cargando) {
        if (!itemElement) {
            return;
        }

        itemElement.dataset.loading = cargando ? "true" : "false";

        itemElement.querySelectorAll("button").forEach((boton) => {
            boton.disabled = cargando;
        });
    }


    // ========================================================
    // 10. DIBUJAR EL CARRITO
    // ========================================================
    // Recibe el objeto carrito del backend y construye el HTML
    // de cada producto.

    function dibujarCarrito(carrito) {
        if (!elemento.contenido) {
            return;
        }

        const items = Array.isArray(carrito?.items) ? carrito.items : [];

        // --- Carrito vacío ---
        if (items.length === 0) {
            elemento.contenido.innerHTML = `
                <div class="store-cart-empty">
                    <span class="store-cart-empty-icon" aria-hidden="true">✦</span>
                    <strong>Tu carrito está vacío</strong>
                    <p>Agrega tus kombuchas favoritas para comenzar tu pedido.</p>
                    <a href="${urlTienda()}" class="store-cart-btn store-cart-btn-primary" data-cart-continue>
                        Ver la tienda
                    </a>
                </div>
            `;
        } else {
            // --- Lista de productos ---
            elemento.contenido.innerHTML = items
                .map((item) => plantillaItem(item))
                .join("");
        }

        // Actualizamos el subtotal general.
        if (elemento.subtotal) {
            elemento.subtotal.textContent = dinero(carrito?.subtotal || 0);
        }

        // Actualizamos el contador del navbar.
        actualizarContador(carrito?.cantidad_items || 0);
    }


    // Construye el HTML de un solo producto del carrito.
    function plantillaItem(item) {
        const cantidad = Math.max(1, numero(item.cantidad, 1));
        const precio = numero(item.precio);
        const subtotal = numero(item.subtotal);
        const detalleId = escaparHTML(item.carrito_detalle_id);
        const nombre = escaparHTML(item.nombre);

        // Presentación y sabor (si existen).
        const partes = [];
        if (item.presentacion) {
            partes.push(escaparHTML(item.presentacion));
        }
        if (item.sabor && String(item.tipo).toUpperCase() !== "PACK") {
            partes.push(escaparHTML(item.sabor));
        }
        const meta = partes.length
            ? `<p class="store-cart-item-meta">${partes.join(" · ")}</p>`
            : "";

        // Imagen real o placeholder neutro.
        const urlImagen = resolverImagen(item);
        const miniatura = urlImagen
            ? `<img src="${urlImagen}" alt="${nombre}" loading="lazy">`
            : placeholderImagen();

        return `
            <article class="store-cart-item" data-cart-item="${detalleId}">

                <div class="store-cart-thumb">
                    ${miniatura}
                </div>

                <div class="store-cart-item-info">

                    <strong class="store-cart-item-name">${nombre}</strong>

                    ${meta}

                    <span class="store-cart-item-price">${dinero(precio)} c/u</span>

                    <div class="store-cart-item-actions">

                        <div class="store-cart-qty" aria-label="Cantidad del producto">

                            <button
                                type="button"
                                data-cart-minus
                                aria-label="Disminuir cantidad"
                                ${cantidad <= 1 ? "disabled" : ""}
                            >−</button>

                            <span data-cart-quantity aria-live="polite">${cantidad}</span>

                            <button
                                type="button"
                                data-cart-plus
                                aria-label="Aumentar cantidad"
                            >+</button>

                        </div>

                        <button
                            type="button"
                            class="store-cart-remove"
                            data-cart-remove
                            aria-label="Eliminar ${nombre} del carrito"
                        >
                            Eliminar
                        </button>

                    </div>

                </div>

                <strong class="store-cart-item-total">${dinero(subtotal)}</strong>

            </article>
        `;
    }


    // ========================================================
    // 11. CONSULTAR EL CARRITO ACTUAL
    // ========================================================

    async function refrescar() {
        const datos = await pedirJSON(RUTAS.listar, {
            method: "GET",
            headers: {},
        });

        dibujarCarrito(datos.carrito);
        return datos.carrito;
    }


    // ========================================================
    // 12. CAMBIAR LA CANTIDAD DE UN PRODUCTO
    // ========================================================

    async function actualizarCantidad(detalleId, cantidad, itemElement) {
        if (!detalleId) {
            return false;
        }

        marcarItemCargando(itemElement, true);

        try {
            const datos = await pedirJSON(RUTAS.actualizar, {
                method: "POST",
                body: JSON.stringify({
                    carrito_detalle_id: detalleId,
                    cantidad: cantidad,
                }),
            });

            if (datos.carrito) {
                dibujarCarrito(datos.carrito);
            } else {
                await refrescar();
            }

            mostrarToast(datos.mensaje || "Cantidad actualizada.");
            return true;
        } catch (error) {
            mostrarToast(error.message, "error");
            marcarItemCargando(itemElement, false);
            return false;
        }
    }


    // ========================================================
    // 13. ELIMINAR UN PRODUCTO
    // ========================================================

    async function eliminarItem(detalleId, itemElement) {
        if (!detalleId) {
            return false;
        }

        marcarItemCargando(itemElement, true);

        try {
            const datos = await pedirJSON(RUTAS.eliminar, {
                method: "POST",
                body: JSON.stringify({ carrito_detalle_id: detalleId }),
            });

            if (datos.carrito) {
                dibujarCarrito(datos.carrito);
            } else {
                await refrescar();
            }

            mostrarToast(datos.mensaje || "Producto eliminado.");
            return true;
        } catch (error) {
            mostrarToast(error.message, "error");
            marcarItemCargando(itemElement, false);
            return false;
        }
    }


    // ========================================================
    // 14. AGREGAR UN PRODUCTO AL CARRITO
    // ========================================================
    // Esta función la usan la tienda, los favoritos y la ficha.
    // Parámetros:
    //   articleId   -> id del artículo de venta (obligatorio)
    //   quantity    -> cantidad a agregar (por defecto 1)
    //   composition -> contenido de un pack personalizado
    //   button      -> botón pulsado (para mostrar "Agregando...")

    async function agregar({
        articleId,
        quantity = 1,
        composition = null,
        button = null,
    } = {}) {
        if (!articleId) {
            mostrarToast("No se encontró el producto seleccionado.", "error");
            return false;
        }

        // Evitamos solicitudes duplicadas.
        if (agregando.has(articleId)) {
            return false;
        }

        agregando.add(articleId);
        bloquearBoton(button, true);

        try {
            const datos = await pedirJSON(RUTAS.agregar, {
                method: "POST",
                body: JSON.stringify({
                    articulo_venta_id: articleId,
                    cantidad: quantity,
                    composicion: composition,
                }),
            });

            if (datos.carrito) {
                dibujarCarrito(datos.carrito);
            } else {
                await refrescar();
            }

            mostrarToast(datos.mensaje || "Producto agregado.");

            // Abrimos el carrito para que el usuario vea su compra.
            abrir();
            return true;
        } catch (error) {
            mostrarToast(error.message, "error");
            return false;
        } finally {
            agregando.delete(articleId);
            bloquearBoton(button, false);
        }
    }


    // Marca un botón como ocupado y lo restaura al terminar.
    function bloquearBoton(button, cargando, textoCarga = "Agregando...") {
        if (!button) {
            return;
        }

        if (cargando) {
            button.dataset.textoOriginal = button.innerHTML;
            button.disabled = true;
            button.textContent = textoCarga;
            return;
        }

        button.disabled = false;

        if (button.dataset.textoOriginal) {
            button.innerHTML = button.dataset.textoOriginal;
            delete button.dataset.textoOriginal;
        }
    }


    // ========================================================
    // 15. EVENTOS
    // ========================================================

    function enlazarEventos() {
        // --- Abrir el carrito desde cualquier botón ---
        document.addEventListener("click", (event) => {
            const abridor = event.target.closest?.("[data-cart-open]");

            if (abridor) {
                event.preventDefault();
                abrir();
                return;
            }

            // El botón "Ver la tienda" del carrito vacío también
            // cierra el panel (luego navega).
            const continuarInterno = event.target.closest?.(
                ".store-cart-empty [data-cart-continue]"
            );
            if (continuarInterno) {
                cerrar();
            }
        });

        // --- Botones de cerrar / seguir comprando / overlay ---
        elemento.cerrar?.addEventListener("click", cerrar);
        elemento.continuar?.addEventListener("click", cerrar);
        elemento.overlay?.addEventListener("click", cerrar);

        // --- Cerrar con la tecla Escape ---
        document.addEventListener("keydown", (event) => {
            if (
                event.key === "Escape" &&
                elemento.drawer?.classList.contains("is-open")
            ) {
                cerrar();
            }
        });

        // --- Cambiar / eliminar productos dentro del carrito ---
        elemento.contenido?.addEventListener("click", async (event) => {
            const button = event.target.closest("button");

            if (!button) {
                return;
            }

            const itemElement = button.closest("[data-cart-item]");

            if (!itemElement || itemElement.dataset.loading === "true") {
                return;
            }

            const detalleId = itemElement.dataset.cartItem;
            const cantidadActual = Math.max(
                1,
                numero(
                    itemElement.querySelector("[data-cart-quantity]")?.textContent,
                    1
                )
            );

            if (button.matches("[data-cart-plus]")) {
                await actualizarCantidad(detalleId, cantidadActual + 1, itemElement);
                return;
            }

            if (button.matches("[data-cart-minus]")) {
                if (cantidadActual <= 1) {
                    return;
                }
                await actualizarCantidad(detalleId, cantidadActual - 1, itemElement);
                return;
            }

            if (button.matches("[data-cart-remove]")) {
                await eliminarItem(detalleId, itemElement);
            }
        });
    }


    // ========================================================
    // 16. INICIO DEL MÓDULO
    // ========================================================

    async function iniciar() {
        cargarElementos();

        // Si la página no tiene carrito lateral, no hacemos nada.
        // Esto permite cargar este archivo en todo el sitio sin
        // provocar errores donde no hace falta.
        if (!elemento.drawer || inicializado) {
            return;
        }

        inicializado = true;
        enlazarEventos();

        // Si la página ya trae el carrito dibujado por el
        // servidor (#store-cart-data), lo mostramos al instante.
        // Si no, lo pedimos al backend.
        const datosIniciales = document.getElementById("store-cart-data");

        if (datosIniciales) {
            try {
                dibujarCarrito(JSON.parse(datosIniciales.textContent));
                return;
            } catch {
                // Si el JSON viene dañado, seguimos con la consulta.
            }
        }

        if (cargandoInicial) {
            return;
        }

        cargandoInicial = true;

        try {
            await refrescar();
        } catch {
            // Sin conexión no rompemos la página: dejamos el
            // carrito con su estado de "cargando".
        } finally {
            cargandoInicial = false;
        }
    }


    // ========================================================
    // 17. API PÚBLICA
    // ========================================================
    // Otros archivos (por ejemplo store.js) usan estas funciones
    // para no repetir la lógica del carrito.

    window.SulpaaCart = {
        open: abrir,
        close: cerrar,
        refresh: refrescar,
        render: dibujarCarrito,
        add: agregar,
        updateCounter: actualizarContador,
    };


    // Arrancamos cuando el documento esté listo.
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})();
