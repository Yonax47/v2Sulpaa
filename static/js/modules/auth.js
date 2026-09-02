/*
============================================================
SULPAA V2 - MÓDULO DE AUTENTICACIÓN
============================================================

Archivo:
static/js/modules/auth.js

Responsabilidades:
- Mostrar y ocultar contraseñas.
- Limitar DNI a caracteres numéricos.
- Limitar teléfonos a caracteres numéricos.
- Evitar números y símbolos inválidos en nombres.

Este archivo puede ser utilizado por:
- Registro
- Login
- Recuperación de contraseña
- Otras pantallas relacionadas con autenticación.

IMPORTANTE:
Las validaciones JavaScript mejoran la experiencia del
usuario, pero NO reemplazan las validaciones del backend.
============================================================
*/


document.addEventListener("DOMContentLoaded", () => {

    // ========================================================
    // 1. MOSTRAR / OCULTAR CONTRASEÑAS
    // ========================================================

    const passwordToggles =
        document.querySelectorAll(
            "[data-password-toggle]"
        );

    passwordToggles.forEach((toggle) => {

        toggle.addEventListener("click", () => {

            const inputId =
                toggle.getAttribute(
                    "data-password-toggle"
                );

            const passwordInput =
                document.getElementById(inputId);

            // Protección por si el elemento no existe.
            if (!passwordInput) {
                return;
            }

            const estaVisible =
                passwordInput.type === "text";

            passwordInput.type =
                estaVisible
                    ? "password"
                    : "text";

            toggle.textContent =
                estaVisible
                    ? "Ver"
                    : "Ocultar";

            toggle.setAttribute(
                "aria-label",
                estaVisible
                    ? "Mostrar contraseña"
                    : "Ocultar contraseña"
            );
        });

    });


    // ========================================================
    // 2. DNI
    // ========================================================
    //
    // Mientras el usuario escribe:
    //
    // - elimina cualquier carácter no numérico
    // - limita el valor a 8 dígitos
    //
    // El backend vuelve a validar este dato.
    // ========================================================

    const camposDni =
        document.querySelectorAll(
            '[data-validation="dni"]'
        );

    camposDni.forEach((campo) => {

        campo.addEventListener("input", () => {

            campo.value =
                campo.value
                    .replace(/\D/g, "")
                    .slice(0, 8);

        });

    });


    // ========================================================
    // 3. TELÉFONO
    // ========================================================
    //
    // Para nuestro registro actual utilizamos números
    // móviles peruanos de 9 dígitos.
    // ========================================================

    const camposTelefono =
        document.querySelectorAll(
            '[data-validation="telefono"]'
        );

    camposTelefono.forEach((campo) => {

        campo.addEventListener("input", () => {

            campo.value =
                campo.value
                    .replace(/\D/g, "")
                    .slice(0, 9);

        });

    });


    // ========================================================
    // 4. NOMBRES Y APELLIDOS
    // ========================================================
    //
    // Permitimos:
    //
    // - Letras
    // - Vocales con tilde
    // - Ñ
    // - Ü
    // - Espacios
    // - Apóstrofes
    // - Guiones
    //
    // Ejemplos:
    //
    // Carlos Alberto
    // María-José
    // O'Connor
    // ========================================================

    const camposNombre =
        document.querySelectorAll(
            '[data-validation="nombre"]'
        );

    camposNombre.forEach((campo) => {

        campo.addEventListener("input", () => {

            campo.value =
                campo.value.replace(
                    /[^A-Za-zÁÉÍÓÚáéíóúÑñÜü '\-]/g,
                    ""
                );

        });

    });

});