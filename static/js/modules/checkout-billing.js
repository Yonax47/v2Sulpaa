"use strict";


document.addEventListener(
    "DOMContentLoaded",
    () => {

        // ====================================================
        // ELEMENTOS DE COMPROBANTE
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
            !dniInput
            || !verifyDniButton
            || !dniMessage
            || !dniResult
            || !dniName
        ) {
            return;
        }


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
);