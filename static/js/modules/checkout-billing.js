"use strict";


document.addEventListener(
    "DOMContentLoaded",
    () => {

        // ====================================================
        // ELEMENTOS DE COMPROBANTE
        // Implementación rama: serna
        //
        // Este módulo controla la selección entre
        // BOLETA y FACTURA, además de las verificaciones
        // de identidad y datos tributarios mediante backend.
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
        // CAMBIAR TIPO DE COMPROBANTE
        // ====================================================

        function changeReceiptType() {

            if (boletaRadio.checked) {

                boletaPanel.hidden = false;
                facturaPanel.hidden = true;

            } else {

                boletaPanel.hidden = true;
                facturaPanel.hidden = false;
            }
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

                    const dni = dniInput.value
                        .replace(/\D/g, "")
                        .slice(0, 8);

                    dniInput.value = dni;

                    dniMessage.textContent = "";
                    dniResult.hidden = true;


                    if (dni.length !== 8) {

                        dniMessage.textContent =
                            "El DNI debe tener 8 dígitos.";

                        dniInput.focus();

                        return;
                    }


                    const originalText =
                        verifyDniButton.textContent;

                    verifyDniButton.disabled = true;

                    verifyDniButton.textContent =
                        "Verificando...";


                    try {

                        const response = await fetch(
                            "/identidad/api/facturacion/verificar-dni",
                            {
                                method: "POST",

                                credentials: "same-origin",

                                headers: {
                                    "Content-Type":
                                        "application/json"
                                },

                                body: JSON.stringify({
                                    dni: dni
                                })
                            }
                        );


                        const data =
                            await response.json();


                        if (!response.ok) {

                            throw new Error(
                                data.mensaje
                                || "No se pudo verificar el DNI."
                            );
                        }


                        const persona =
                            data.persona;


                        dniName.textContent = [
                            persona.nombres,
                            persona.apellido_paterno,
                            persona.apellido_materno
                        ]
                            .filter(Boolean)
                            .join(" ");


                        dniMessage.textContent =
                            data.mensaje;

                        dniResult.hidden = false;


                    } catch (error) {

                        dniMessage.textContent =
                            error.message;

                    } finally {

                        verifyDniButton.disabled = false;

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
        // El navegador envía únicamente el RUC.
        // El backend realiza la consulta a APIsPERU
        // y devuelve los datos tributarios verificados.
        // El token privado nunca se expone al frontend.
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

                    const ruc = rucInput.value
                        .replace(/\D/g, "")
                        .slice(0, 11);

                    rucInput.value = ruc;

                    rucMessage.textContent = "";
                    rucResult.hidden = true;


                    if (ruc.length !== 11) {

                        rucMessage.textContent =
                            "El RUC debe tener 11 dígitos.";

                        rucInput.focus();

                        return;
                    }


                    const originalText =
                        verifyRucButton.textContent;

                    verifyRucButton.disabled = true;

                    verifyRucButton.textContent =
                        "Verificando...";


                    try {

                        const response = await fetch(
                            "/identidad/api/facturacion/verificar-ruc",
                            {
                                method: "POST",

                                credentials: "same-origin",

                                headers: {
                                    "Content-Type":
                                        "application/json"
                                },

                                body: JSON.stringify({
                                    ruc: ruc
                                })
                            }
                        );


                        const data =
                            await response.json();


                        if (!response.ok) {

                            throw new Error(
                                data.mensaje
                                || "No se pudo verificar el RUC."
                            );
                        }


                        const empresa =
                            data.empresa;


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
                            .filter(Boolean)
                            .join(" - ")
                            || "No disponible";


                        rucMessage.textContent =
                            data.mensaje;

                        rucResult.hidden = false;


                    } catch (error) {

                        rucMessage.textContent =
                            error.message;

                    } finally {

                        verifyRucButton.disabled = false;

                        verifyRucButton.textContent =
                            originalText;
                    }
                }
            );
        }
    }
);