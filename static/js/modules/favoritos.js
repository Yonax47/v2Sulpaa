/*
============================================================
SULPAA V2 - FAVORITOS DEL CLIENTE
============================================================

Este módulo solo coordina la interacción visual. El backend valida
la variante, persiste el favorito y registra la auditoría KPI-06.
============================================================
*/

document.addEventListener("DOMContentLoaded", () => {
    let toastTimer = null;

    function showMessage(message, type = "success") {
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
        toast.classList.add(type === "error" ? "is-error" : "is-success");
        toast.textContent = message;

        window.requestAnimationFrame(() => {
            toast.classList.add("is-visible");
        });

        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => {
            toast.classList.remove("is-visible");
        }, 3500);
    }

    function updateButtons(varianteId, active) {
        document.querySelectorAll("[data-favorite-toggle]").forEach((button) => {
            if (button.dataset.varianteId !== varianteId) {
                return;
            }

            const productName = button.dataset.productName || "este producto";
            const action = active ? "Quitar" : "Agregar";
            const preposition = active ? "de" : "a";

            button.dataset.active = active ? "true" : "false";
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-pressed", active ? "true" : "false");
            button.setAttribute(
                "aria-label",
                `${action} ${productName} ${preposition} favoritos`,
            );
            button.title = active ? "Quitar de favoritos" : "Agregar a favoritos";

            const icon = button.querySelector("[data-favorite-icon]");
            const label = button.querySelector("[data-favorite-label]");

            if (icon) {
                icon.textContent = active ? "♥" : "♡";
            }
            if (label) {
                label.textContent = active ? "Guardado" : "Guardar";
            }
        });
    }

    document.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-favorite-toggle]");

        if (!button || button.disabled) {
            return;
        }

        const varianteId = button.dataset.varianteId;
        const active = button.dataset.active === "true";
        const url = active ? button.dataset.removeUrl : button.dataset.addUrl;

        if (!varianteId || !url) {
            showMessage("No se encontró la variante seleccionada.", "error");
            return;
        }

        button.disabled = true;

        try {
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({variante_id: varianteId}),
            });
            const data = await response.json();

            if (!response.ok || !data.ok) {
                throw new Error(data.mensaje || "No se pudo actualizar favoritos.");
            }

            updateButtons(varianteId, !active);
            showMessage(data.mensaje || "Favoritos actualizados.");
        } catch (error) {
            showMessage(
                error.message || "No se pudo conectar con el servidor.",
                "error",
            );
        } finally {
            button.disabled = false;
        }
    });
});
