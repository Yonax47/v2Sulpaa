"use strict";


document.addEventListener(
    "DOMContentLoaded",
    () => {

        // ====================================================
        // ELEMENTOS
        // ====================================================

        const form = document.getElementById(
            "checkout-address-form"
        );

        if (!form) {
            return;
        }

        const departmentSelect = document.getElementById(
            "checkout-department"
        );

        const provinceSelect = document.getElementById(
            "checkout-province"
        );

        const districtSelect = document.getElementById(
            "checkout-district"
        );

        const addressInput = document.getElementById(
            "checkout-address"
        );

        const referenceInput = document.getElementById(
            "checkout-reference"
        );

        const aliasInput = document.getElementById(
            "checkout-address-alias"
        );

        const message = document.getElementById(
            "checkout-address-message"
        );

        const saveButton = document.getElementById(
            "checkout-save-address"
        );


        // ====================================================
        // MENSAJES
        // ====================================================

        function showMessage(
            text,
            type = "error"
        ) {

            message.textContent = text;

            message.dataset.type = type;
        }


        function clearMessage() {

            message.textContent = "";

            delete message.dataset.type;
        }


        // ====================================================
        // PETICIONES
        // ====================================================

        async function getJSON(url) {

            const response = await fetch(
                url,
                {
                    method: "GET",
                    credentials: "same-origin"
                }
            );

            const data = await response.json();

            if (!response.ok) {

                throw new Error(
                    data.mensaje
                    || "No se pudo obtener la información."
                );
            }

            return data;
        }


        async function postJSON(
            url,
            body
        ) {

            const response = await fetch(
                url,
                {
                    method: "POST",

                    credentials: "same-origin",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify(
                        body
                    )
                }
            );

            const data = await response.json();

            if (!response.ok) {

                throw new Error(
                    data.mensaje
                    || "No se pudo guardar la dirección."
                );
            }

            return data;
        }


        // ====================================================
        // SELECTOR DE PROVINCIAS
        // ====================================================

        departmentSelect.addEventListener(
            "change",
            async () => {

                clearMessage();

                const departmentId =
                    departmentSelect.value;

                provinceSelect.innerHTML = `
                    <option value="">
                        Selecciona una provincia
                    </option>
                `;

                districtSelect.innerHTML = `
                    <option value="">
                        Primero selecciona una provincia
                    </option>
                `;

                provinceSelect.disabled = true;
                districtSelect.disabled = true;


                if (!departmentId) {
                    return;
                }


                try {

                    const data = await getJSON(
                        `/identidad/api/ubicacion/provincias/${departmentId}`
                    );


                    data.provincias.forEach(
                        (province) => {

                            const option =
                                document.createElement(
                                    "option"
                                );

                            option.value =
                                province.id;

                            option.textContent =
                                province.nombre;

                            provinceSelect.appendChild(
                                option
                            );
                        }
                    );


                    provinceSelect.disabled = false;

                } catch (error) {

                    showMessage(
                        error.message
                    );
                }
            }
        );


        // ====================================================
        // SELECTOR DE DISTRITOS
        // ====================================================

        provinceSelect.addEventListener(
            "change",
            async () => {

                clearMessage();

                const provinceId =
                    provinceSelect.value;


                districtSelect.innerHTML = `
                    <option value="">
                        Selecciona un distrito
                    </option>
                `;

                districtSelect.disabled = true;


                if (!provinceId) {
                    return;
                }


                try {

                    const data = await getJSON(
                        `/identidad/api/ubicacion/distritos/${provinceId}`
                    );


                    data.distritos.forEach(
                        (district) => {

                            const option =
                                document.createElement(
                                    "option"
                                );

                            option.value =
                                district.id;

                            option.textContent =
                                district.nombre;

                            districtSelect.appendChild(
                                option
                            );
                        }
                    );


                    districtSelect.disabled = false;

                } catch (error) {

                    showMessage(
                        error.message
                    );
                }
            }
        );


        // ====================================================
        // GUARDAR DIRECCIÓN
        // ====================================================

        form.addEventListener(
            "submit",
            async (event) => {

                event.preventDefault();

                clearMessage();


                const districtId =
                    districtSelect.value;

                const address =
                    addressInput.value.trim();

                const reference =
                    referenceInput.value.trim();

                const alias =
                    aliasInput.value.trim();


                if (!districtId) {

                    showMessage(
                        "Selecciona un distrito."
                    );

                    return;
                }


                if (address.length < 5) {

                    showMessage(
                        "Ingresa una dirección válida."
                    );

                    addressInput.focus();

                    return;
                }


                saveButton.disabled = true;

                const originalText =
                    saveButton.textContent;

                saveButton.textContent =
                    "Guardando...";


                try {

                    const data = await postJSON(
                        "/identidad/api/direcciones",
                        {
                            distrito_id:
                                districtId,

                            direccion:
                                address,

                            referencia:
                                reference,

                            alias:
                                alias
                        }
                    );


                    showMessage(
                        data.mensaje,
                        "success"
                    );


                    /*
                     * Recargamos para que Flask vuelva a
                     * consultar Identidad y muestre la
                     * dirección que acabamos de guardar.
                     */
                    window.location.reload();

                } catch (error) {

                    showMessage(
                        error.message
                    );

                    saveButton.disabled = false;

                    saveButton.textContent =
                        originalText;
                }
            }
        );
      
    }
);