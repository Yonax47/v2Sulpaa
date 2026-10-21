/*
============================================================
SULPAA V2 - TIENDA
============================================================

Responsabilidades:

- Animaciones.
- Búsqueda y filtros.
- Packs fijos.
- Pack personalizado.
- Botella 1 L.
- Barriles 30 L / 50 L.
- Cantidades según stock.
- Carrito persistente.
- Comunicación segura con Flask.

IMPORTANTE:

El frontend NUNCA decide si una compra es válida.

JavaScript solamente mejora la experiencia.

El backend vuelve a validar:
- artículo;
- cantidad;
- stock;
- composición;
- reglas del pack.

============================================================
*/


document.addEventListener("DOMContentLoaded", () => {


    /* ========================================================
       1. CONFIGURACIÓN
       ======================================================== */

    const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;


    /* ========================================================
       2. UTILIDADES
       ======================================================== */

    function toNumber(value, fallback = 0) {

        const number = Number(value);

        return Number.isFinite(number)
            ? number
            : fallback;
    }


    function money(value) {

        return `S/ ${toNumber(value).toFixed(2)}`;
    }


    function normalizeText(value) {

        return String(value || "")
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim();
    }


    async function requestJSON(url, options = {}) {

        const response = await fetch(
            url,
            {
                credentials: "same-origin",
                ...options,
                headers: {
                    "Content-Type": "application/json",
                    ...(options.headers || {})
                }
            }
        );


        let data = {};

        try {

            data = await response.json();

        } catch {

            data = {
                ok: false,
                mensaje:
                    "El servidor devolvió una respuesta inválida."
            };
        }


        if (!response.ok) {

            throw new Error(
                data.mensaje
                || "No se pudo completar la operación."
            );
        }


        return data;
    }


    /* ========================================================
       3. NOTIFICACIONES
       ========================================================
       Reutilizamos el aviso (toast) que ya vive en cart.js
       (window.SulpaaToast) para no tener dos versiones distintas
       de la misma función en el proyecto. */

    function showToast(message, type = "success") {

        if (window.SulpaaToast) {

            window.SulpaaToast.show(message, type);

            return;
        }


        /*
        Si por algún motivo cart.js no estuviera cargado, no
        rompemos la tienda: simplemente mostramos el aviso en
        la consola.
        */

        window.console?.warn(
            `[SULPAA] ${message}`
        );
    }


    /* ========================================================
       4. ANIMACIONES REVEAL
       ======================================================== */

    const revealElements =
        document.querySelectorAll(".reveal");


    if (reduceMotion) {

        revealElements.forEach((element) => {

            element.classList.add(
                "is-visible"
            );

        });

    } else {

        const observer =
            new IntersectionObserver(

                (entries, revealObserver) => {

                    entries.forEach((entry) => {

                        if (!entry.isIntersecting) {
                            return;
                        }


                        entry.target.classList.add(
                            "is-visible"
                        );


                        revealObserver.unobserve(
                            entry.target
                        );

                    });

                },

                {
                    threshold: 0.10,
                    rootMargin:
                        "0px 0px -35px 0px"
                }

            );


        revealElements.forEach((element) => {

            observer.observe(element);

        });
    }


    /* ========================================================
       5. ANIMACIÓN HERO
       ======================================================== */

    const heroBottles =
        document.querySelectorAll(
            ".store-hero-bottle"
        );


    if (!reduceMotion) {

        heroBottles.forEach(
            (bottle, index) => {

                bottle.animate(

                    [
                        {
                            translate: "0 0"
                        },

                        {
                            translate:
                                index % 2 === 0
                                    ? "0 -8px"
                                    : "0 -5px"
                        },

                        {
                            translate: "0 0"
                        }
                    ],

                    {
                        duration:
                            3800 + (index * 320),

                        iterations:
                            Infinity,

                        easing:
                            "ease-in-out"
                    }

                );

            }
        );
    }


    /* ========================================================
       6. BÚSQUEDA Y FILTROS
       ======================================================== */

    const searchInput =
        document.querySelector(
            "[data-store-search]"
        );

    const filterButtons =
        document.querySelectorAll(
            "[data-filter]"
        );

    const productWrappers =
        Array.from(
            document.querySelectorAll(
                "[data-product-wrapper]"
            )
        );

    const resultsCount =
        document.querySelector(
            "[data-results-count]"
        );

    const clearFiltersButton =
        document.querySelector(
            "[data-clear-filters]"
        );

    const emptyState =
        document.querySelector(
            "[data-empty-state]"
        );

    const emptyClearButton =
        document.querySelector(
            "[data-empty-clear]"
        );


    let activeFlavor = "all";


    function applyFilters() {

        const searchValue =
            searchInput
                ? normalizeText(
                    searchInput.value
                )
                : "";


        let visibleProducts = 0;


        productWrappers.forEach(
            (wrapper) => {

                const name =
                    normalizeText(
                        wrapper.dataset.name
                    );


                const flavor =
                    wrapper.dataset.flavor || "";


                const matchesSearch =
                    name.includes(
                        searchValue
                    );


                const matchesFlavor =
                    activeFlavor === "all"
                    || flavor === activeFlavor;


                const visible =
                    matchesSearch
                    && matchesFlavor;


                wrapper.hidden = !visible;


                if (visible) {
                    visibleProducts += 1;
                }
            }
        );


        if (resultsCount) {

            resultsCount.textContent =
                visibleProducts === 1
                    ? "1 sabor para descubrir"
                    : `${visibleProducts} sabores para descubrir`;
        }


        if (emptyState) {

            emptyState.hidden =
                visibleProducts !== 0;
        }
    }


    function clearFilters() {

        activeFlavor = "all";


        if (searchInput) {

            searchInput.value = "";
        }


        filterButtons.forEach(
            (button) => {

                button.classList.toggle(
                    "is-active",
                    button.dataset.filter === "all"
                );

            }
        );


        applyFilters();
    }


    if (searchInput) {

        searchInput.addEventListener(
            "input",
            applyFilters
        );
    }


    filterButtons.forEach((button) => {

        button.addEventListener(
            "click",
            () => {

                activeFlavor =
                    button.dataset.filter
                    || "all";


                filterButtons.forEach(
                    (item) => {

                        item.classList.remove(
                            "is-active"
                        );

                    }
                );


                button.classList.add(
                    "is-active"
                );


                applyFilters();
            }
        );

    });


    clearFiltersButton?.addEventListener(
        "click",
        clearFilters
    );


    emptyClearButton?.addEventListener(
        "click",
        clearFilters
    );


    /* ========================================================
       7. SCROLL
       ======================================================== */

    function scrollToElement(element) {

        if (!element) {
            return;
        }


        const navbar =
            document.querySelector(
                ".site-header"
            );


        const navbarHeight =
            navbar
                ? navbar.offsetHeight
                : 0;


        const top =
            element.getBoundingClientRect().top
            + window.scrollY
            - navbarHeight
            - 18;


        window.scrollTo({

            top,

            behavior:
                reduceMotion
                    ? "auto"
                    : "smooth"

        });
    }


    const internalLinks =
        document.querySelectorAll(
            'a[href^="#"]:not([href="#"])'
        );


    internalLinks.forEach((link) => {

        link.addEventListener(
            "click",
            (event) => {

                const selector =
                    link.getAttribute("href");


                let target = null;


                try {

                    target =
                        document.querySelector(
                            selector
                        );

                } catch {

                    return;
                }


                if (!target) {
                    return;
                }


                event.preventDefault();

                scrollToElement(target);
            }
        );

    });


    /* ========================================================
       8. DESCUBRIR SEGÚN PERFIL
       ======================================================== */

    const discoverButtons =
        document.querySelectorAll(
            "[data-discover-filter]"
        );


    discoverButtons.forEach((button) => {

        button.addEventListener(
            "click",
            () => {

                const flavor =
                    button.dataset.discoverFilter;


                activeFlavor = flavor;


                if (searchInput) {

                    searchInput.value = "";
                }


                filterButtons.forEach(
                    (filterButton) => {

                        filterButton.classList.toggle(
                            "is-active",
                            filterButton.dataset.filter
                                === flavor
                        );

                    }
                );


                applyFilters();


                scrollToElement(
                    document.querySelector(
                        "#sabores"
                    )
                );
            }
        );

    });


    /* ========================================================
       9. CARRITO
       ========================================================
       Toda la lógica del carrito (abrir y cerrar el panel,
       dibujar los productos, actualizar cantidades y eliminar)
       vive ahora en un solo archivo reutilizable:
       static/js/modules/cart.js (window.SulpaaCart).

       El panel se muestra con el componente
       components/cart_drawer.html, incluido en el navbar.

       Aquí dejamos solo una función corta que delega en ese
       módulo, para que el resto de la tienda siga llamando a
       addToCart sin duplicar código. */

    function addToCart({
        articleId,
        quantity,
        composition = null,
        button = null
    }) {

        return window.SulpaaCart.add({

            articleId,
            quantity,
            composition,
            button
        });
    }


    /* ========================================================
       10. PACKS FIJOS
       ======================================================== */

    const packCards =
        document.querySelectorAll(
            "[data-pack-card]"
        );


    packCards.forEach((card) => {

        const sizeButtons =
            Array.from(
                card.querySelectorAll(
                    "[data-pack-size]"
                )
            );


        const priceElement =
            card.querySelector(
                "[data-pack-price]"
            );

        const stockElement =
            card.querySelector(
                "[data-pack-stock]"
            );

        const quantityElement =
            card.querySelector(
                "[data-pack-quantity]"
            );

        const totalElement =
            card.querySelector(
                "[data-pack-total]"
            );

        const minusButton =
            card.querySelector(
                "[data-pack-minus]"
            );

        const plusButton =
            card.querySelector(
                "[data-pack-plus]"
            );

        const addButton =
            card.querySelector(
                "[data-pack-add]"
            );


        let quantity = 1;


        function activePack() {

            return card.querySelector(
                "[data-pack-size].is-active"
            );
        }


        function updatePack() {

            const selected =
                activePack();


            if (!selected) {

                if (priceElement) {
                    priceElement.textContent =
                        "No disponible";
                }

                if (stockElement) {
                    stockElement.textContent =
                        "Sin configuración comercial";
                }

                if (addButton) {
                    addButton.disabled = true;
                }

                return;
            }


            const size =
                toNumber(
                    selected.dataset.packSize
                );


            const price =
                toNumber(
                    selected.dataset.price
                );


            const stock =
                toNumber(
                    selected.dataset.stock
                );


            quantity =
                Math.max(
                    1,
                    Math.min(
                        quantity,
                        Math.max(stock, 1)
                    )
                );


            if (priceElement) {

                priceElement.textContent =
                    money(price);
            }


            if (stockElement) {

                if (stock > 0) {

                    stockElement.textContent =
                        `${stock} packs disponibles`;

                    stockElement.classList.remove(
                        "is-out"
                    );

                } else {

                    stockElement.textContent =
                        "Agotado";

                    stockElement.classList.add(
                        "is-out"
                    );
                }
            }


            if (quantityElement) {

                quantityElement.textContent =
                    String(quantity);
            }


            if (totalElement) {

                const bottles =
                    size * quantity;


                totalElement.textContent =
                    quantity === 1
                        ? `1 pack × ${size} botellas = ${bottles} botellas`
                        : `${quantity} packs × ${size} botellas = ${bottles} botellas`;
            }


            if (minusButton) {

                minusButton.disabled =
                    quantity <= 1;
            }


            if (plusButton) {

                plusButton.disabled =
                    stock <= 0
                    || quantity >= stock;
            }


            if (addButton) {

                addButton.disabled =
                    stock <= 0;
            }
        }


        sizeButtons.forEach((button) => {

            button.addEventListener(
                "click",
                () => {

                    sizeButtons.forEach(
                        (item) => {

                            item.classList.remove(
                                "is-active"
                            );

                        }
                    );


                    button.classList.add(
                        "is-active"
                    );


                    quantity = 1;

                    updatePack();
                }
            );

        });


        minusButton?.addEventListener(
            "click",
            () => {

                if (quantity <= 1) {
                    return;
                }


                quantity -= 1;

                updatePack();
            }
        );


        plusButton?.addEventListener(
            "click",
            () => {

                const selected =
                    activePack();


                if (!selected) {
                    return;
                }


                const stock =
                    toNumber(
                        selected.dataset.stock
                    );


                if (
                    stock <= 0
                    || quantity >= stock
                ) {
                    return;
                }


                quantity += 1;

                updatePack();
            }
        );


        addButton?.addEventListener(
            "click",
            async () => {

                const selected =
                    activePack();


                if (!selected) {

                    showToast(
                        "Selecciona un pack disponible.",
                        "error"
                    );

                    return;
                }


                const success =
                    await addToCart({

                        articleId:
                            selected.dataset.articleId,

                        quantity,

                        button:
                            addButton

                    });


                if (success) {

                    /*
                    Volvemos a consultar la página
                    únicamente cuando sea necesario
                    en una fase posterior.

                    El backend ya impide superar stock
                    considerando el contenido del carrito.
                    */

                    quantity = 1;

                    updatePack();
                }
            }
        );


        /*
        Si por alguna razón el primer botón no
        quedó activo desde Jinja, activamos el primero.
        */

        if (
            sizeButtons.length > 0
            && !activePack()
        ) {

            sizeButtons[0].classList.add(
                "is-active"
            );
        }


        updatePack();
    });


    /* ========================================================
       11. FORMATOS GRANDES
       ======================================================== */

    const largeCards =
        document.querySelectorAll(
            "[data-large-card]"
        );


    largeCards.forEach((card) => {

        const quantityElement =
            card.querySelector(
                "[data-large-quantity]"
            );

        const minusButton =
            card.querySelector(
                "[data-large-minus]"
            );

        const plusButton =
            card.querySelector(
                "[data-large-plus]"
            );

        const addButton =
            card.querySelector(
                "[data-large-add]"
            );

        const priceElement =
            card.querySelector(
                "[data-large-price]"
            );

        const stockElement =
            card.querySelector(
                "[data-large-stock]"
            );


        let quantity = 1;

        let currentItem = null;


        function updateLargeCommerce() {

            if (!currentItem) {

                if (priceElement) {
                    priceElement.textContent =
                        "No disponible";
                }

                if (stockElement) {
                    stockElement.textContent =
                        "Sin disponibilidad";
                }

                if (addButton) {
                    addButton.disabled = true;
                }

                return;
            }


            const stock =
                toNumber(
                    currentItem.stock
                );


            quantity =
                Math.max(
                    1,
                    Math.min(
                        quantity,
                        Math.max(stock, 1)
                    )
                );


            if (quantityElement) {

                quantityElement.textContent =
                    String(quantity);
            }


            if (priceElement) {

                priceElement.textContent =
                    money(
                        currentItem.price
                    );
            }


            if (stockElement) {

                if (stock > 0) {

                    stockElement.textContent =
                        `${stock} unidades disponibles`;

                    stockElement.classList.remove(
                        "is-out"
                    );

                } else {

                    stockElement.textContent =
                        "Agotado";

                    stockElement.classList.add(
                        "is-out"
                    );
                }
            }


            if (minusButton) {

                minusButton.disabled =
                    quantity <= 1;
            }


            if (plusButton) {

                plusButton.disabled =
                    stock <= 0
                    || quantity >= stock;
            }


            if (addButton) {

                addButton.disabled =
                    stock <= 0;
            }
        }


        /* ----------------------------------------------------
           BOTELLA 1 L
           ---------------------------------------------------- */

        const literSelect =
            card.querySelector(
                '[data-large-select="Botella 1 L"]'
            );


        function selectLiter() {

            if (!literSelect) {
                return;
            }


            const option =
                literSelect.options[
                    literSelect.selectedIndex
                ];


            if (!option) {

                currentItem = null;

            } else {

                currentItem = {

                    variantId:
                        option.value,

                    articleId:
                        option.dataset.article,

                    price:
                        toNumber(
                            option.dataset.price
                        ),

                    stock:
                        toNumber(
                            option.dataset.stock
                        )
                };
            }


            quantity = 1;

            updateLargeCommerce();
        }


        literSelect?.addEventListener(
            "change",
            selectLiter
        );


        /* ----------------------------------------------------
           BARRILES
           ---------------------------------------------------- */

        const barrelSizeButtons =
            Array.from(
                card.querySelectorAll(
                    "[data-barrel-size]"
                )
            );

        const barrelFlavor =
            card.querySelector(
                "[data-barrel-flavor]"
            );

        const barrelItems =
            Array.from(
                card.querySelectorAll(
                    "[data-barrel-item]"
                )
            );


        function selectBarrel() {

            if (
                barrelItems.length === 0
                || !barrelFlavor
            ) {
                return;
            }


            const activeSize =
                card.querySelector(
                    "[data-barrel-size].is-active"
                );


            const presentation =
                activeSize
                    ?.dataset
                    ?.barrelSize;


            const flavor =
                barrelFlavor.value;


            const item =
                barrelItems.find(
                    (element) => {

                        return (
                            element.dataset.presentation
                                === presentation
                            &&
                            element.dataset.flavor
                                === flavor
                        );
                    }
                );


            if (!item) {

                currentItem = null;

            } else {

                currentItem = {

                    variantId:
                        item.dataset.variant,

                    articleId:
                        item.dataset.article,

                    price:
                        toNumber(
                            item.dataset.price
                        ),

                    stock:
                        toNumber(
                            item.dataset.stock
                        )
                };
            }


            quantity = 1;

            updateLargeCommerce();
        }


        barrelSizeButtons.forEach(
            (button) => {

                button.addEventListener(
                    "click",
                    () => {

                        barrelSizeButtons.forEach(
                            (item) => {

                                item.classList.remove(
                                    "is-active"
                                );

                            }
                        );


                        button.classList.add(
                            "is-active"
                        );


                        selectBarrel();
                    }
                );

            }
        );


        barrelFlavor?.addEventListener(
            "change",
            selectBarrel
        );


        /* ----------------------------------------------------
           CANTIDAD
           ---------------------------------------------------- */

        minusButton?.addEventListener(
            "click",
            () => {

                if (quantity <= 1) {
                    return;
                }


                quantity -= 1;

                updateLargeCommerce();
            }
        );


        plusButton?.addEventListener(
            "click",
            () => {

                if (!currentItem) {
                    return;
                }


                const stock =
                    toNumber(
                        currentItem.stock
                    );


                if (
                    stock <= 0
                    || quantity >= stock
                ) {
                    return;
                }


                quantity += 1;

                updateLargeCommerce();
            }
        );


        /* ----------------------------------------------------
           AGREGAR
           ---------------------------------------------------- */

        addButton?.addEventListener(
            "click",
            async () => {

                if (!currentItem) {

                    showToast(
                        "Selecciona una presentación disponible.",
                        "error"
                    );

                    return;
                }


                const success =
                    await addToCart({

                        articleId:
                            currentItem.articleId,

                        quantity,

                        button:
                            addButton

                    });


                if (success) {

                    quantity = 1;

                    updateLargeCommerce();
                }
            }
        );


        /* ----------------------------------------------------
           INICIALIZACIÓN
           ---------------------------------------------------- */

        if (literSelect) {

            selectLiter();

        } else if (
            barrelItems.length > 0
        ) {

            selectBarrel();
        }
    });


    /* ========================================================
       12. PACK PERSONALIZADO
       ======================================================== */

    const mixBuilder =
        document.querySelector(
            "[data-mix-builder]"
        );

    const customPackDataElement =
        document.getElementById(
            "store-custom-pack-data"
        );


    if (
        mixBuilder
        && customPackDataElement
    ) {

        let customPacks = [];


        try {

            customPacks =
                JSON.parse(
                    customPackDataElement.textContent
                );

        } catch {

            customPacks = [];
        }


        const sizeButtons =
            Array.from(
                mixBuilder.querySelectorAll(
                    "[data-mix-size]"
                )
            );

        const flavorRows =
            Array.from(
                mixBuilder.querySelectorAll(
                    "[data-mix-flavor]"
                )
            );

        const counter =
            mixBuilder.querySelector(
                "[data-mix-counter]"
            );

        const progress =
            mixBuilder.querySelector(
                "[data-mix-progress]"
            );

        const status =
            mixBuilder.querySelector(
                "[data-mix-status]"
            );

        const ruleText =
            mixBuilder.querySelector(
                "[data-mix-rule]"
            );

        const priceDisplay =
            mixBuilder.querySelector(
                "[data-mix-price-display]"
            );

        const addButton =
            mixBuilder.querySelector(
                "[data-mix-add]"
            );


        const quantities = new Map();

        const maxFlavorsByPackSize = {
            6: 3,
            12: 4,
            24: 6
        };


        flavorRows.forEach((row) => {

            quantities.set(
                row.dataset.mixVariant,
                0
            );

        });


        function activeMixButton() {

            return mixBuilder.querySelector(
                "[data-mix-size].is-active"
            );
        }


        function currentPack() {

            const button =
                activeMixButton();


            if (!button) {
                return null;
            }


            return customPacks.find(
                (pack) => {

                    return (
                        String(pack.pack_id)
                        === String(
                            button.dataset.mixPackId
                        )
                    );
                }
            ) || null;
        }


        function resetMix() {

            quantities.forEach(
                (_, key) => {

                    quantities.set(
                        key,
                        0
                    );

                }
            );


            flavorRows.forEach((row) => {

                const value =
                    row.querySelector(
                        "[data-mix-value]"
                    );


                if (value) {
                    value.textContent = "0";
                }
            });
        }


        function selectedTotal() {

            let total = 0;


            quantities.forEach((value) => {

                total += value;

            });


            return total;
        }


        function selectedFlavors() {

            let total = 0;


            quantities.forEach((value) => {

                if (value > 0) {
                    total += 1;
                }
            });


            return total;
        }


        function allowedVariants(pack) {

            if (!pack) {
                return new Set();
            }


            return new Set(
                (pack.variantes_permitidas || [])
                    .map(
                        (item) =>
                            String(
                                item.variante_id
                            )
                    )
            );
        }


        function maxFlavorsForPack(pack) {

            if (!pack) {
                return 0;
            }


            const size =
                toNumber(
                    pack.cantidad_unidades
                );


            return maxFlavorsByPackSize[size] || 0;
        }


        function ruleDescription(pack) {

            if (!pack) {
                return "Selecciona un tamaño de pack.";
            }


            const target =
                toNumber(
                    pack.cantidad_unidades
                );


            const maxFlavors =
                maxFlavorsForPack(pack);


            if (target <= 0 || maxFlavors <= 0) {

                return "Este tamaño no tiene una regla comercial válida.";
            }


            return (
                `Completa exactamente ${target} botellas `
                + `usando hasta ${maxFlavors} sabores. `
                + "La distribución entre sabores es libre."
            );
        }


        function compositionIsValid(pack) {

            if (!pack) {
                return false;
            }


            const target =
                toNumber(
                    pack.cantidad_unidades
                );


            const maxFlavors =
                maxFlavorsForPack(pack);


            const total =
                selectedTotal();


            const flavors =
                selectedFlavors();


            return (
                target > 0
                && maxFlavors > 0
                && total === target
                && flavors >= 1
                && flavors <= maxFlavors
            );
        }


        function updateMix() {

            const button =
                activeMixButton();


            const pack =
                currentPack();


            if (!button || !pack) {

                addButton.disabled = true;

                return;
            }


            const target =
                toNumber(
                    pack.cantidad_unidades
                );


            const total =
                selectedTotal();


            const flavors =
                selectedFlavors();


            const permitted =
                allowedVariants(pack);


            flavorRows.forEach((row) => {

                const variantId =
                    String(
                        row.dataset.mixVariant
                    );


                const allowed =
                    permitted.has(
                        variantId
                    );


                row.hidden = !allowed;


                const quantity =
                    quantities.get(
                        variantId
                    ) || 0;


                const value =
                    row.querySelector(
                        "[data-mix-value]"
                    );


                if (value) {

                    value.textContent =
                        String(quantity);
                }


                const stock =
                    toNumber(
                        row.dataset.mixStock
                    );


                const minus =
                    row.querySelector(
                        "[data-mix-minus]"
                    );


                const plus =
                    row.querySelector(
                        "[data-mix-plus]"
                    );


                if (minus) {

                    minus.disabled =
                        !allowed
                        || quantity <= 0;
                }


                if (plus) {

                    const maxFlavors =
                        maxFlavorsForPack(
                            pack
                        );

                    const wouldAddNewFlavor =
                        quantity === 0;

                    plus.disabled =
                        !allowed
                        || total >= target
                        || quantity >= stock
                        || (
                            wouldAddNewFlavor
                            && flavors >= maxFlavors
                        );
                }
            });


            if (counter) {

                counter.textContent =
                    `${total} / ${target}`;
            }


            if (progress) {

                const percentage =
                    target > 0
                        ? Math.min(
                            (total / target) * 100,
                            100
                        )
                        : 0;


                progress.style.width =
                    `${percentage}%`;
            }


            if (priceDisplay) {

                priceDisplay.textContent =
                    money(
                        pack.precio
                    );
            }


            if (ruleText) {

                ruleText.textContent =
                    ruleDescription(pack);
            }


            const complete =
                total === target;


            const ruleValid =
                compositionIsValid(
                    pack
                );


            const maxFlavors =
                maxFlavorsForPack(
                    pack
                );


            if (status) {

                if (total < target) {

                    status.textContent =
                        `Te faltan ${target - total} botellas.`;

                } else if (
                    total > target
                ) {

                    status.textContent =
                        "Has superado el tamaño del pack.";

                } else if (
                    flavors > maxFlavors
                ) {

                    status.textContent =
                        `Puedes usar como máximo ${maxFlavors} sabores.`;

                } else if (
                    !ruleValid
                ) {

                    status.textContent =
                        "La composición todavía no cumple las reglas del pack.";

                } else {

                    status.textContent =
                        `Pack completo con ${flavors} sabor${flavors === 1 ? "" : "es"}.`;
                }
            }


            if (addButton) {

                addButton.disabled =
                    !complete
                    || !ruleValid;
            }
        }


        sizeButtons.forEach((button) => {

            button.addEventListener(
                "click",
                () => {

                    sizeButtons.forEach(
                        (item) => {

                            item.classList.remove(
                                "is-active"
                            );

                        }
                    );


                    button.classList.add(
                        "is-active"
                    );


                    resetMix();

                    updateMix();
                }
            );

        });


        flavorRows.forEach((row) => {

            const variantId =
                row.dataset.mixVariant;


            const minus =
                row.querySelector(
                    "[data-mix-minus]"
                );


            const plus =
                row.querySelector(
                    "[data-mix-plus]"
                );


            minus?.addEventListener(
                "click",
                () => {

                    const current =
                        quantities.get(
                            variantId
                        ) || 0;


                    if (current <= 0) {
                        return;
                    }


                    quantities.set(
                        variantId,
                        current - 1
                    );


                    updateMix();
                }
            );


            plus?.addEventListener(
                "click",
                () => {

                    const pack =
                        currentPack();


                    if (!pack) {
                        return;
                    }


                    const permitted =
                        allowedVariants(
                            pack
                        );


                    if (
                        !permitted.has(
                            String(variantId)
                        )
                    ) {
                        return;
                    }


                    const target =
                        toNumber(
                            pack.cantidad_unidades
                        );


                    const total =
                        selectedTotal();


                    if (total >= target) {
                        return;
                    }


                    const current =
                        quantities.get(
                            variantId
                        ) || 0;


                    const stock =
                        toNumber(
                            row.dataset.mixStock
                        );


                    if (current >= stock) {
                        return;
                    }


                    const maxFlavors =
                        maxFlavorsForPack(
                            pack
                        );


                    if (
                        current === 0
                        && selectedFlavors() >= maxFlavors
                    ) {

                        showToast(
                            `Este pack permite como máximo ${maxFlavors} sabores.`,
                            "error"
                        );

                        return;
                    }


                    quantities.set(
                        variantId,
                        current + 1
                    );


                    updateMix();
                }
            );

        });


        addButton?.addEventListener(
            "click",
            async () => {

                const button =
                    activeMixButton();


                const pack =
                    currentPack();


                if (!button || !pack) {

                    showToast(
                        "Selecciona un tamaño de pack.",
                        "error"
                    );

                    return;
                }


                if (
                    !compositionIsValid(
                        pack
                    )
                ) {

                    showToast(
                        "Completa el pack respetando el total y el máximo de sabores.",
                        "error"
                    );

                    return;
                }


                const composition = [];


                quantities.forEach(
                    (quantity, variantId) => {

                        if (quantity <= 0) {
                            return;
                        }


                        composition.push({
                            variante_id:
                                variantId,

                            cantidad:
                                quantity
                        });

                    }
                );


                const success =
                    await addToCart({

                        articleId:
                            button.dataset.mixArticleId,

                        quantity: 1,

                        composition,

                        button:
                            addButton

                    });


                if (success) {

                    resetMix();

                    updateMix();
                }
            }
        );


        if (
            sizeButtons.length > 0
            && !activeMixButton()
        ) {

            sizeButtons[0].classList.add(
                "is-active"
            );
        }


        updateMix();
    }


    /* ========================================================
       13. CARRITO INICIAL
       ========================================================
       El dibujado inicial del carrito (usando los datos que ya
       trae la página) lo hace ahora cart.js cuando arranca.
       Por eso aquí ya no hace falta repetir esa lógica. */


    /* ========================================================
       14. ESTADO INICIAL
       ======================================================== */

    applyFilters();

});
