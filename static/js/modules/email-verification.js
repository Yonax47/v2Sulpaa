(function () {
    "use strict";
    document.addEventListener("DOMContentLoaded", function () {
        var input = document.querySelector("[data-verification-token]");
        if (!input || !window.location.hash) { return; }
        var params = new URLSearchParams(window.location.hash.slice(1));
        var token = params.get("token") || "";
        if (token.length >= 20 && token.length <= 200) {
            input.value = token;
            // El fragmento no llegó al servidor; se elimina de la barra para
            // evitar que quede visible al compartir una captura o URL.
            history.replaceState(null, document.title, window.location.pathname);
        }
    });
}());
