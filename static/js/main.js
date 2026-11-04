(function protegerSolicitudesDeSulpaa() {
    "use strict";

    /*
     * Los formularios envían el token como campo oculto, pero las acciones
     * realizadas con fetch no tienen ese campo. Este envoltorio agrega la
     * cabecera CSRF a toda petición que modifica datos dentro del mismo sitio.
     * Nunca envía el token a servicios externos, como el proveedor de mapas.
     */
    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (!metaToken || typeof window.fetch !== "function") {
        return;
    }

    const token = metaToken.getAttribute("content") || "";
    const fetchOriginal = window.fetch.bind(window);
    const metodosSeguros = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

    window.fetch = function fetchProtegido(recurso, opciones) {
        const configuracion = opciones ? { ...opciones } : {};
        const esRequest = typeof Request !== "undefined" && recurso instanceof Request;
        const metodo = String(
            configuracion.method || (esRequest ? recurso.method : "GET")
        ).toUpperCase();
        const urlTexto = esRequest ? recurso.url : String(recurso);
        const url = new URL(urlTexto, window.location.href);

        if (!metodosSeguros.has(metodo) && url.origin === window.location.origin) {
            /*
             * Se conservan las cabeceras que ya tenía la llamada, por ejemplo
             * Content-Type. Solo se agrega CSRF si el módulo no lo hizo antes.
             */
            const cabeceras = new Headers(
                configuracion.headers || (esRequest ? recurso.headers : undefined)
            );
            if (!cabeceras.has("X-CSRF-Token")) {
                cabeceras.set("X-CSRF-Token", token);
            }
            configuracion.headers = cabeceras;
        }

        return fetchOriginal(recurso, configuracion);
    };
}());

(function confirmarAccionesAdministrativas() {
    "use strict";

    /*
     * Los formularios con data-confirmar representan cambios de estado u
     * otras acciones sensibles. Se muestra el texto definido por la plantilla
     * y se cancela el envío cuando la persona no confirma. Sin JavaScript el
     * formulario sigue protegido por CSRF y por las reglas del servidor.
     */
    document.addEventListener("submit", function alEnviar(evento) {
        const formulario = evento.target.closest("form[data-confirmar]");
        if (!formulario) {
            return;
        }

        const mensaje = formulario.getAttribute("data-confirmar") ||
            "¿Deseas continuar con esta acción?";
        if (!window.confirm(mensaje)) {
            evento.preventDefault();
        }
    });
}());

(function inicializarNotificacionesSulpaa() {
    "use strict";

    const TIPOS = new Set(["success", "danger", "warning", "info"]);

    function normalizarTipo(tipo) {
        const valor = String(tipo || "info").toLowerCase();
        if (valor === "error") {
            return "danger";
        }
        return TIPOS.has(valor) ? valor : "info";
    }

    function obtenerRegion() {
        let region = document.querySelector("[data-toast-region]");
        if (!region) {
            region = document.createElement("div");
            region.className = "sulpaa-toast-region";
            region.dataset.toastRegion = "";
            region.setAttribute("aria-live", "polite");
            region.setAttribute("aria-relevant", "additions");
            document.body.appendChild(region);
        }
        return region;
    }

    function cerrar(toast) {
        if (toast && toast.parentNode) {
            toast.remove();
        }
    }

    function programarCierre(toast) {
        const demora = Number(toast.dataset.toastAutoclose || 0);
        if (demora > 0) {
            window.setTimeout(function cerrarLuego() {
                cerrar(toast);
            }, demora);
        }
    }

    function mostrar(mensaje, tipo, opciones) {
        const texto = String(mensaje || "").trim();
        if (!texto) {
            return null;
        }

        const tipoNormalizado = normalizarTipo(tipo);
        const repetido = Array.from(document.querySelectorAll("[data-toast]")).find(
            (item) => item.dataset.toastType === tipoNormalizado &&
                item.querySelector("p")?.textContent === texto
        );
        if (repetido) { return repetido; }
        const configuracion = opciones || {};
        const toast = document.createElement("div");
        toast.className = "sulpaa-toast is-" + tipoNormalizado;
        toast.dataset.toast = "";
        toast.dataset.toastType = tipoNormalizado;
        toast.setAttribute(
            "role",
            tipoNormalizado === "danger" || tipoNormalizado === "warning"
                ? "alert"
                : "status"
        );

        const iconos = { success: "✓", danger: "!", warning: "⚠", info: "i" };
        const icono = document.createElement("span");
        icono.className = "sulpaa-toast-icon";
        icono.setAttribute("aria-hidden", "true");
        icono.textContent = iconos[tipoNormalizado];

        const contenido = document.createElement("p");
        contenido.textContent = texto;

        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "sulpaa-toast-close";
        boton.dataset.toastClose = "";
        boton.setAttribute("aria-label", "Cerrar notificación");
        boton.textContent = "×";

        toast.append(icono, contenido, boton);
        if (configuracion.autoclose !== false &&
            (tipoNormalizado === "success" || tipoNormalizado === "info")) {
            toast.dataset.toastAutoclose = String(configuracion.demora || 6000);
        }
        obtenerRegion().appendChild(toast);
        programarCierre(toast);
        return toast;
    }

    document.addEventListener("click", function cerrarDesdeBoton(evento) {
        const boton = evento.target.closest("[data-toast-close]");
        if (boton) {
            cerrar(boton.closest("[data-toast]"));
        }
    });

    document.querySelectorAll("[data-toast]").forEach(programarCierre);

    window.SulpaaToast = Object.freeze({
        show: mostrar,
        normalizeType: normalizarTipo,
    });
}());

(function prepararMensajesDeGraficos() {
    "use strict";

    function mostrarErrorCarga(contenedor) {
        const raiz = contenedor || document;
        raiz.querySelectorAll('canvas[id^="chart-"]').forEach(function ocultar(lienzo) {
            lienzo.hidden = true;
            const aviso = document.createElement("p");
            aviso.className = "admin-chart-empty";
            aviso.textContent = "No se pudo cargar el componente de gráficos.";
            lienzo.insertAdjacentElement("afterend", aviso);
        });
        console.error("SULPAA: Chart.js no está disponible.");
    }

    window.SulpaaCharts = Object.freeze({
        showLoadError: mostrarErrorCarga,
    });
}());
