"use strict";

document.addEventListener(
    "DOMContentLoaded",
    () => {

        // ====================================================
        // ELEMENTOS DE COMPROBANTE
        // Implementación rama: serna
        //
        // Controla la selección entre BOLETA y FACTURA
        // y la verificación de DNI/RUC mediante backend.
        //
        // La persistencia definitiva de facturación se realiza
        // al confirmar el pedido desde el backend de checkout.
        // ====================================================

        const boletaRadio = document.getElementById(
            "checkout-boleta"
        );

        const facturaRadio = document.getElementById(
            "checkout-factura"
        );

        const boletaPanel = document.getElementById(
            "checkout-boleta-panel"
        );

        const facturaPanel = document.getElementById(
            "checkout-factura-panel"
        );


        // ====================================================
        // ELEMENTOS DE BOLETA / DNI
        // ====================================================

        const dniInput = document.getElementById(
            "checkout-dni"
        );

        const verifyDniButton = document.getElementById(
            "checkout-verify-dni"
        );

        const dniMessage = document.getElementById(
            "checkout-dni-message"
        );

        const dniResult = document.getElementById(
            "checkout-dni-result"
        );

        const dniName = document.getElementById(
            "checkout-dni-name"
        );


        // ====================================================
        // ELEMENTOS DE FACTURA / RUC
        // ====================================================

        const rucInput = document.getElementById(
            "checkout-ruc"
        );

        const verifyRucButton = document.getElementById(
            "checkout-verify-ruc"
        );

        const rucMessage = document.getElementById(
            "checkout-ruc-message"
        );

        const rucResult = document.getElementById(
            "checkout-ruc-result"
        );

        const rucBusinessName = document.getElementById(
            "checkout-ruc-business-name"
        );

        const rucAddress = document.getElementById(
            "checkout-ruc-address"
        );

        const rucStatus = document.getElementById(
            "checkout-ruc-status"
        );

        const rucCondition = document.getElementById(
            "checkout-ruc-condition"
        );

        const rucLocation = document.getElementById(
            "checkout-ruc-location"
        );


        // ====================================================
        // SEGURIDAD
        // ====================================================

        if (
            !boletaRadio
            || !facturaRadio
            || !boletaPanel
            || !facturaPanel
        ) {
            return;
        }


        // ====================================================
        // NOTIFICAR CAMBIOS DE FACTURACIÓN
        // ====================================================
        //
        // checkout.js escucha este evento para actualizar
        // inmediatamente el estado del botón
        // "Confirmar pedido".
        // ====================================================

        function notifyBillingUpdated() {

            window.dispatchEvent(
                new CustomEvent(
                    "checkout:billing-updated"
                )
            );
        }


        // ====================================================
        // CAMBIAR TIPO DE COMPROBANTE
        // ====================================================

        function changeReceiptType() {

            if (boletaRadio.checked) {

                boletaPanel.hidden = false;
                facturaPanel.hidden = true;


                /*
                 * Al cambiar a BOLETA invalidamos cualquier
                 * verificación anterior del RUC.
                 */

                if (rucResult) {

                    rucResult.hidden = true;

                    delete (
                        rucResult.dataset
                            .documentoVerificado
                    );
                }


                if (rucMessage) {

                    rucMessage.textContent = "";
                }


            } else if (
                facturaRadio.checked
            ) {

                boletaPanel.hidden = true;
                facturaPanel.hidden = false;


                /*
                 * Al cambiar a FACTURA invalidamos cualquier
                 * verificación anterior del DNI.
                 */

                if (dniResult) {

                    dniResult.hidden = true;

                    delete (
                        dniResult.dataset
                            .documentoVerificado
                    );
                }


                if (dniMessage) {

                    dniMessage.textContent = "";
                }


            } else {

                boletaPanel.hidden = true;
                facturaPanel.hidden = true;


                if (dniResult) {

                    dniResult.hidden = true;

                    delete (
                        dniResult.dataset
                            .documentoVerificado
                    );
                }


                if (rucResult) {

                    rucResult.hidden = true;

                    delete (
                        rucResult.dataset
                            .documentoVerificado
                    );
                }
            }


            notifyBillingUpdated();
        }


        boletaRadio.addEventListener(
            "change",
            changeReceiptType
        );


        facturaRadio.addEventListener(
            "change",
            changeReceiptType
        );


        changeReceiptType();


        // ====================================================
        // INVALIDAR DNI SI CAMBIA EL DOCUMENTO
        // ====================================================
        //
        // La validación deja de ser válida inmediatamente si
        // el usuario modifica cualquier dígito del DNI.
        // ====================================================

        if (dniInput) {

            dniInput.addEventListener(
                "input",
                () => {

                    dniInput.value =
                        dniInput.value
                            .replace(
                                /\D/g,
                                ""
                            )
                            .slice(
                                0,
                                8
                            );


                    if (dniResult) {

                        dniResult.hidden = true;

                        delete (
                            dniResult.dataset
                                .documentoVerificado
                        );
                    }


                    if (dniMessage) {

                        dniMessage.textContent =
                            "";
                    }


                    notifyBillingUpdated();
                }
            );
        }


        // ====================================================
        // INVALIDAR RUC SI CAMBIA EL DOCUMENTO
        // ====================================================

        if (rucInput) {

            rucInput.addEventListener(
                "input",
                () => {

                    rucInput.value =
                        rucInput.value
                            .replace(
                                /\D/g,
                                ""
                            )
                            .slice(
                                0,
                                11
                            );


                    if (rucResult) {

                        rucResult.hidden = true;

                        delete (
                            rucResult.dataset
                                .documentoVerificado
                        );
                    }


                    if (rucMessage) {

                        rucMessage.textContent =
                            "";
                    }


                    notifyBillingUpdated();
                }
            );
        }


        // ====================================================
        // FACTURACIÓN DEFINITIVA
        // ====================================================
        //
        // Este archivo SOLO verifica DNI/RUC para la
        // experiencia del usuario.
        //
        // La confirmación final del checkout vuelve a
        // verificar el documento en backend y recién allí
        // guarda datos_facturacion.
        //
        // De esta forma evitamos:
        //
        // - registros duplicados;
        // - facturación de pedidos no confirmados;
        // - confiar únicamente en JavaScript.
        // ====================================================


        // ====================================================
        // VERIFICAR DNI
        // ====================================================

        if (
            dniInput
            && verifyDniButton
            && dniMessage
            && dniResult
            && dniName
        ) {

            verifyDniButton.addEventListener(
                "click",
                async () => {

                    // ----------------------------------------
                    // 1. NORMALIZAR DNI
                    // ----------------------------------------

                    const dni =
                        dniInput.value
                            .replace(
                                /\D/g,
                                ""
                            )
                            .slice(
                                0,
                                8
                            );


                    dniInput.value = dni;


                    // ----------------------------------------
                    // 2. INVALIDAR VERIFICACIÓN ANTERIOR
                    // ----------------------------------------

                    dniMessage.textContent = "";

                    dniResult.hidden = true;

                    delete (
                        dniResult.dataset
                            .documentoVerificado
                    );


                    notifyBillingUpdated();


                    // ----------------------------------------
                    // 3. VALIDAR FORMATO
                    // ----------------------------------------

                    if (dni.length !== 8) {

                        dniMessage.textContent =
                            "El DNI debe tener 8 dígitos.";


                        dniInput.focus();


                        return;
                    }


                    // ----------------------------------------
                    // 4. ESTADO DEL BOTÓN
                    // ----------------------------------------

                    const originalText =
                        verifyDniButton
                            .textContent;


                    verifyDniButton.disabled =
                        true;


                    verifyDniButton.textContent =
                        "Verificando...";


                    try {

                        // ------------------------------------
                        // 5. VERIFICAR DNI EN BACKEND
                        // ------------------------------------

                        const response =
                            await fetch(
                                "/identidad/api/facturacion/verificar-dni",
                                {
                                    method:
                                        "POST",

                                    credentials:
                                        "same-origin",

                                    headers: {
                                        "Content-Type":
                                            "application/json"
                                    },

                                    body:
                                        JSON.stringify(
                                            {
                                                dni:
                                                    dni
                                            }
                                        )
                                }
                            );


                        const data =
                            await response.json();


                        if (!response.ok) {

                            throw new Error(
                                data.mensaje
                                || (
                                    "No se pudo " +
                                    "verificar el DNI."
                                )
                            );
                        }


                        const persona =
                            data.persona;


                        // ------------------------------------
                        // 6. VALIDAR RESPUESTA
                        // ------------------------------------

                        if (!persona) {

                            throw new Error(
                                "No se recibieron los datos del titular."
                            );
                        }


                        // ------------------------------------
                        // 7. MOSTRAR TITULAR VERIFICADO
                        // ------------------------------------

                        dniName.textContent = [
                            persona.nombres,
                            persona.apellido_paterno,
                            persona.apellido_materno
                        ]
                            .filter(
                                Boolean
                            )
                            .join(
                                " "
                            );


                        // ------------------------------------
                        // 8. MARCAR DNI COMO VERIFICADO
                        // ------------------------------------
                        //
                        // NO guardamos datos_facturacion aquí.
                        //
                        // El backend final volverá a validar
                        // este documento cuando se confirme
                        // realmente el pedido.
                        // ------------------------------------

                        dniResult.dataset
                            .documentoVerificado =
                                dni;


                        dniMessage.textContent =
                            data.mensaje
                            || (
                                "DNI verificado " +
                                "correctamente."
                            );


                        dniResult.hidden =
                            false;


                        notifyBillingUpdated();


                    } catch (error) {

                        // ------------------------------------
                        // ERROR DE VERIFICACIÓN
                        // ------------------------------------

                        dniMessage.textContent =
                            error.message;


                        dniResult.hidden =
                            true;


                        delete (
                            dniResult.dataset
                                .documentoVerificado
                        );


                        notifyBillingUpdated();


                    } finally {

                        verifyDniButton.disabled =
                            false;


                        verifyDniButton.textContent =
                            originalText;
                    }
                }
            );
        }


        // ====================================================
        // VERIFICAR RUC
        // Implementación rama: serna
        //
        // El token de APIsPERU permanece exclusivamente
        // en backend y nunca se expone al navegador.
        // ====================================================

        if (
            rucInput
            && verifyRucButton
            && rucMessage
            && rucResult
            && rucBusinessName
            && rucAddress
            && rucStatus
            && rucCondition
            && rucLocation
        ) {

            verifyRucButton.addEventListener(
                "click",
                async () => {

                    // ----------------------------------------
                    // 1. NORMALIZAR RUC
                    // ----------------------------------------

                    const ruc =
                        rucInput.value
                            .replace(
                                /\D/g,
                                ""
                            )
                            .slice(
                                0,
                                11
                            );


                    rucInput.value = ruc;


                    // ----------------------------------------
                    // 2. INVALIDAR VERIFICACIÓN ANTERIOR
                    // ----------------------------------------

                    rucMessage.textContent = "";

                    rucResult.hidden = true;


                    delete (
                        rucResult.dataset
                            .documentoVerificado
                    );


                    notifyBillingUpdated();


                    // ----------------------------------------
                    // 3. VALIDAR FORMATO
                    // ----------------------------------------

                    if (ruc.length !== 11) {

                        rucMessage.textContent =
                            "El RUC debe tener 11 dígitos.";


                        rucInput.focus();


                        return;
                    }


                    // ----------------------------------------
                    // 4. ESTADO DEL BOTÓN
                    // ----------------------------------------

                    const originalText =
                        verifyRucButton
                            .textContent;


                    verifyRucButton.disabled =
                        true;


                    verifyRucButton.textContent =
                        "Verificando...";


                    try {

                        // ------------------------------------
                        // 5. VERIFICAR RUC EN BACKEND
                        // ------------------------------------

                        const response =
                            await fetch(
                                "/identidad/api/facturacion/verificar-ruc",
                                {
                                    method:
                                        "POST",

                                    credentials:
                                        "same-origin",

                                    headers: {
                                        "Content-Type":
                                            "application/json"
                                    },

                                    body:
                                        JSON.stringify(
                                            {
                                                ruc:
                                                    ruc
                                            }
                                        )
                                }
                            );


                        const data =
                            await response.json();


                        if (!response.ok) {

                            throw new Error(
                                data.mensaje
                                || (
                                    "No se pudo " +
                                    "verificar el RUC."
                                )
                            );
                        }


                        const empresa =
                            data.empresa;


                        // ------------------------------------
                        // 6. VALIDAR RESPUESTA
                        // ------------------------------------

                        if (!empresa) {

                            throw new Error(
                                "No se recibieron los datos de la empresa."
                            );
                        }


                        // ------------------------------------
                        // 7. MOSTRAR EMPRESA VERIFICADA
                        // ------------------------------------

                        rucBusinessName.textContent =
                            empresa.razon_social
                            || "No disponible";


                        rucAddress.textContent =
                            empresa.direccion
                            || "No disponible";


                        rucStatus.textContent =
                            empresa.estado
                            || "No disponible";


                        rucCondition.textContent =
                            empresa.condicion
                            || "No disponible";


                        rucLocation.textContent = [
                            empresa.distrito,
                            empresa.provincia,
                            empresa.departamento
                        ]
                            .filter(
                                Boolean
                            )
                            .join(
                                " - "
                            )
                            || "No disponible";


                        // ------------------------------------
                        // 8. MARCAR RUC COMO VERIFICADO
                        // ------------------------------------
                        //
                        // Igual que con la boleta, la
                        // facturación todavía no se persiste.
                        //
                        // El backend definitivo la guardará
                        // solamente si el pedido se confirma.
                        // ------------------------------------

                        rucResult.dataset
                            .documentoVerificado =
                                ruc;


                        rucMessage.textContent =
                            data.mensaje
                            || (
                                "RUC verificado " +
                                "correctamente."
                            );


                        rucResult.hidden =
                            false;


                        notifyBillingUpdated();


                    } catch (error) {

                        // ------------------------------------
                        // ERROR DE VERIFICACIÓN
                        // ------------------------------------

                        rucMessage.textContent =
                            error.message;


                        rucResult.hidden =
                            true;


                        delete (
                            rucResult.dataset
                                .documentoVerificado
                        );


                        notifyBillingUpdated();


                    } finally {

                        verifyRucButton.disabled =
                            false;


                        verifyRucButton.textContent =
                            originalText;
                    }
                }
            );
        }
    }
);