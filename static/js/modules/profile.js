(function () {
    "use strict";

    function avisar(mensaje, tipo) {
        if (window.SulpaaToast && typeof window.SulpaaToast.show === "function") {
            window.SulpaaToast.show(mensaje, tipo || "info");
        }
    }

    function estadoDelFormulario(form) {
        return form.querySelector("[data-form-status]");
    }

    function mostrarEstado(form, mensaje, esError) {
        var estado = estadoDelFormulario(form);
        if (!estado) { return; }
        estado.textContent = mensaje || "";
        estado.className = "profile-form-status" + (mensaje ? (esError ? " is-error" : " is-success") : "");
    }

    function campoError(campo, mensaje) {
        var contenedor = campo.closest("label");
        var salida = contenedor ? contenedor.querySelector("[data-field-error]") : null;
        if (!salida) { return; }
        salida.textContent = mensaje || "";
        if (mensaje) {
            campo.setAttribute("aria-invalid", "true");
        } else {
            campo.removeAttribute("aria-invalid");
        }
    }

    function validarFormulario(form) {
        var campos = form.querySelectorAll("input, select, textarea");
        var primerError = null;
        campos.forEach(function (campo) {
            campoError(campo, "");
            if (!campo.willValidate || campo.validity.valid) { return; }
            var mensaje = campo.validationMessage || "Revisa este campo.";
            campoError(campo, mensaje);
            if (!primerError) { primerError = campo; }
        });
        if (primerError) {
            mostrarEstado(form, primerError.validationMessage || "Revisa los datos ingresados.", true);
            avisar(primerError.validationMessage || "Revisa los datos ingresados.", "danger");
            primerError.focus();
            return false;
        }
        return true;
    }

    document.addEventListener("DOMContentLoaded", function () {
        var formularios = document.querySelectorAll("[data-profile-form]");
        formularios.forEach(function (form) {
            var telefono = form.querySelector('input[name="telefono"]');
            if (telefono) {
                telefono.addEventListener("input", function () {
                    telefono.value = telefono.value.replace(/\D/g, "").slice(0, 9);
                });
            }
            form.addEventListener("input", function (evento) {
                campoError(evento.target, "");
                mostrarEstado(form, "", false);
            });
            form.addEventListener("change", function (evento) {
                campoError(evento.target, "");
                mostrarEstado(form, "", false);
            });
            form.addEventListener("submit", function (evento) {
                if (!validarFormulario(form)) {
                    evento.preventDefault();
                    return;
                }
                if (telefono) {
                    telefono.value = telefono.value.replace(/\D/g, "");
                }
                mostrarEstado(form, "Guardando cambios…", false);
            });
        });

        var ubicacion = document.querySelector("[data-location-form]");
        if (ubicacion) {
            var departamento = ubicacion.querySelector("[data-departamento]");
            var provincia = ubicacion.querySelector("[data-provincia]");
            var distrito = ubicacion.querySelector("[data-distrito]");

            function opciones(select, filas) {
                select.innerHTML = '<option value="">Selecciona</option>';
                filas.forEach(function (fila) {
                    var opcion = document.createElement("option");
                    opcion.value = fila.id;
                    opcion.textContent = fila.nombre;
                    select.appendChild(opcion);
                });
                select.disabled = filas.length === 0;
            }

            function cargar(select, url, clave) {
                fetch(url, {headers: {"Accept": "application/json"}})
                    .then(function (respuesta) {
                        if (!respuesta.ok) { throw new Error("respuesta no válida"); }
                        return respuesta.json();
                    })
                    .then(function (datos) {
                        opciones(select, datos[clave] || []);
                    })
                    .catch(function () {
                        opciones(select, []);
                        avisar("No se pudieron cargar las opciones de ubicación.", "danger");
                    });
            }

            if (departamento && provincia && distrito) {
                departamento.addEventListener("change", function () {
                    provincia.disabled = true;
                    distrito.disabled = true;
                    opciones(provincia, []);
                    opciones(distrito, []);
                    if (!departamento.value) { return; }
                    cargar(
                        provincia,
                        "/identidad/api/ubicacion/provincias/" + encodeURIComponent(departamento.value),
                        "provincias"
                    );
                });
                provincia.addEventListener("change", function () {
                    distrito.disabled = true;
                    opciones(distrito, []);
                    if (!provincia.value) { return; }
                    cargar(
                        distrito,
                        "/identidad/api/ubicacion/distritos/" + encodeURIComponent(provincia.value),
                        "distritos"
                    );
                });
            }
        }

        var tipo = document.querySelector("[data-billing-type]");
        var documento = document.querySelector("[data-billing-document]");
        if (tipo && documento) {
            function ajustarDocumento() {
                var factura = tipo.value === "FACTURA";
                documento.value = "";
                documento.maxLength = factura ? 11 : 8;
                documento.minLength = factura ? 11 : 8;
                documento.pattern = factura ? "[0-9]{11}" : "[0-9]{8}";
                documento.placeholder = factura ? "RUC de 11 dígitos" : "DNI de 8 dígitos";
                campoError(documento, "");
            }
            tipo.addEventListener("change", ajustarDocumento);
            ajustarDocumento();
            documento.addEventListener("input", function () {
                documento.value = documento.value.replace(/\D/g, "").slice(0, documento.maxLength);
            });
        }
    });
}());
