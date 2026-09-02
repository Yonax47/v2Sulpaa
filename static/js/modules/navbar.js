/*
============================================================
SULPAA V2 - NAVBAR RESPONSIVE
============================================================

Controla únicamente la apertura y cierre
del menú móvil.

No contiene lógica de negocio.
============================================================
*/

document.addEventListener("DOMContentLoaded", () => {

    const toggle =
        document.querySelector(
            "[data-navbar-toggle]"
        );

    const menu =
        document.querySelector(
            "[data-navbar-menu]"
        );


    // Si la página no contiene navbar,
    // simplemente no hacemos nada.
    if (!toggle || !menu) {
        return;
    }


    toggle.addEventListener(
        "click",
        () => {

            const abierto =
                menu.classList.toggle(
                    "is-open"
                );


            /*
            Actualizamos aria-expanded para que
            lectores de pantalla sepan si el menú
            se encuentra abierto o cerrado.
            */
            toggle.setAttribute(
                "aria-expanded",
                abierto
                    ? "true"
                    : "false"
            );


            toggle.setAttribute(
                "aria-label",
                abierto
                    ? "Cerrar menú"
                    : "Abrir menú"
            );


            toggle.textContent =
                abierto
                    ? "✕"
                    : "☰";
        }
    );

});