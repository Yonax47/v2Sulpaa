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
