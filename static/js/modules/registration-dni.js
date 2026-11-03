(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var form = document.getElementById("registro-form");
        var boton = document.getElementById("verificar-dni");
        var dni = document.getElementById("dni");
        var estado = document.getElementById("dni-status");
        if (!form || !boton || !dni || !estado) { return; }

        var campos = {
            nombres: document.getElementById("nombres"),
            apellido_paterno: document.getElementById("apellido_paterno"),
            apellido_materno: document.getElementById("apellido_materno")
        };
        var verificado = "";

        function mostrar(tipo, mensaje) {
            estado.className = "form-help auth-dni-status is-" + tipo;
            estado.textContent = mensaje;
        }

        function limpiarIdentidad() {
            verificado = "";
            Object.keys(campos).forEach(function (clave) {
                if (campos[clave]) { campos[clave].value = ""; }
            });
        }

        dni.addEventListener("input", function () {
            if (dni.value !== verificado) {
                limpiarIdentidad();
                mostrar("idle", "DNI pendiente de verificación.");
            }
        });

        boton.addEventListener("click", function () {
            if (!/^\d{8}$/.test(dni.value)) {
                mostrar("invalid", "El DNI debe contener exactamente 8 dígitos.");
                return;
            }
            boton.disabled = true;
            mostrar("loading", "Consultando DNI…");
            var token = document.querySelector('meta[name="csrf-token"]');
            fetch(form.dataset.dniVerificationUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": token ? token.content : ""
                },
                body: JSON.stringify({dni: dni.value})
            }).then(function (respuesta) {
                return respuesta.json().then(function (datos) {
                    return {ok: respuesta.ok, datos: datos};
                });
            }).then(function (resultado) {
                if (!resultado.ok || !resultado.datos.ok) {
                    limpiarIdentidad();
                    mostrar(
                        resultado.datos.estado === "INVALIDO" ? "invalid" : "error",
                        resultado.datos.mensaje || "No fue posible verificar el DNI."
                    );
                    return;
                }
                var persona = resultado.datos.persona || {};
                campos.nombres.value = persona.nombres || "";
                campos.apellido_paterno.value = persona.apellido_paterno || "";
                campos.apellido_materno.value = persona.apellido_materno || "";
                verificado = dni.value;
                mostrar("verified", "DNI consultado. Revisa los datos autocompletados.");
            }).catch(function () {
                limpiarIdentidad();
                mostrar("error", "No fue posible consultar el DNI. Intenta nuevamente.");
            }).finally(function () {
                boton.disabled = false;
            });
        });

        form.addEventListener("submit", function (evento) {
            if (verificado !== dni.value) {
                evento.preventDefault();
                mostrar("invalid", "Verifica el DNI antes de crear la cuenta.");
            }
        });
    });
}());
