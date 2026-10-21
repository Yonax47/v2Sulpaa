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


    // Deja el menú cerrado y actualiza el botón.
    function cerrarMenu() {

        menu.classList.remove("is-open");

        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Abrir menú");
        toggle.textContent = "☰";
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


    /*
    Al tocar un enlace del menú móvil (incluido "Carrito"),
    cerramos el menú. Así no queda abierto detrás del
    carrito lateral.
    */
    menu.addEventListener(
        "click",
        (event) => {

            if (
                event.target.closest(".navbar-mobile-link")
            ) {

                cerrarMenu();
            }
        }
    );

});