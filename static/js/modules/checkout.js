"use strict";

document.addEventListener("DOMContentLoaded", () => {
  // ====================================================
  // ESTADO GENERAL DEL CHECKOUT
  // ====================================================

  let deliveryType = null;
  let deliveryCost = 0;
  let selectedPaymentMethod = null;

  let map = null;
  let destinationMarker = null;
  let routeLayer = null;

  let originCoordinates = null;
  let destinationCoordinates = null;

  let pickupLocations = [];
  let carriers = [];
  let selectedPickupId = null;
  let deliveryQuote = null;
  let carrierQuote = null;
  let destinationVersion = 0;
  let deliveryTimer = null;
  const savedSelector = document.getElementById('checkout-saved-selector');
  const savedSelectorGroup = document.getElementById('checkout-saved-selector-group');
  const destinationSummary = document.getElementById('checkout-destination-summary');
  const savedAddresses = JSON.parse(document.getElementById('checkout-saved-addresses')?.textContent || '[]');

  function destinationPayload() {
    return {
      direccion_id: savedSelector?.value || null,
      distrito_id: districtSelect?.value || '',
      direccion: addressInput?.value.trim() || '',
      referencia: referenceInput?.value.trim() || '',
      latitud: latitudeInput?.value || null,
      longitud: longitudeInput?.value || null,
    };
  }

  function invalidateDestination() {
    destinationVersion += 1;
    deliveryQuote = null;
    carrierQuote = null;
    if (quoteInput) quoteInput.value = '';
    if (distanceInput) distanceInput.value = '';
    if (routeResult) routeResult.hidden = true;
    if (carrierResult) carrierResult.hidden = true;
    if (routeLayer && map) { map.removeLayer(routeLayer); routeLayer = null; }
    clearTimeout(deliveryTimer);
updateSummary(0);
    updateConfirmOrderButton();
  }

  function scheduleDeliveryQuote() {
    clearTimeout(deliveryTimer);
    if (deliveryType === 'DELIVERY_LOCAL' && addressInput?.value.trim().length >= 5) {
      deliveryTimer = setTimeout(() => confirmLocationButton?.click(), 500);
    }
  }

  function refreshAddressMode() {
    const service = carrierServiceSelect?.selectedOptions[0];
    const needsAddress = deliveryType === 'DELIVERY_LOCAL' ||
      (deliveryType === 'TRANSPORTISTA' && service?.dataset.modalidad?.endsWith('_DOMICILIO'));
    if (form) form.hidden = !needsAddress;
    if (savedSelectorGroup) savedSelectorGroup.hidden = !needsAddress;
    if (carrierAgencySelect) carrierAgencySelect.closest('.checkout-form-group')?.toggleAttribute('hidden',
      deliveryType === 'TRANSPORTISTA' && !!service?.dataset.modalidad?.endsWith('_DOMICILIO'));
    if (destinationSummary && needsAddress) destinationSummary.textContent = addressInput?.value || 'Selecciona o indica el destino.';
  }

  // ====================================================
  // ELEMENTOS - DIRECCIÓN
  // ====================================================

  const form = document.getElementById(
    "checkout-address-form",
  );

  const departmentSelect = document.getElementById(
    "checkout-department",
  );

  const provinceSelect = document.getElementById(
    "checkout-province",
  );

  const districtSelect = document.getElementById(
    "checkout-district",
  );

  const addressInput = document.getElementById(
    "checkout-address",
  );

  const referenceInput = document.getElementById(
    "checkout-reference",
  );

  const aliasInput = document.getElementById(
    "checkout-address-alias",
  );

  const addressMessage = document.getElementById(
    "checkout-address-message",
  );

  const saveButton = document.getElementById(
    "checkout-save-address",
  );

  // ====================================================
  // ELEMENTOS - ENTREGA
  // ====================================================

  const deliveryOptions = document.getElementById(
    "checkout-delivery-options",
  );

  const deliveryMessage = document.getElementById(
    "checkout-delivery-message",
  );

  const pickupPanel = document.getElementById(
    "checkout-pickup-panel",
  );

  const pickupLocationsContainer =
    document.getElementById(
      "checkout-pickup-locations",
    );

  const localDeliveryPanel =
    document.getElementById(
      "checkout-local-delivery-panel",
    );

  const carrierPanel = document.getElementById(
    "checkout-carrier-panel",
  );

  // ====================================================
  // ELEMENTOS - MAPA
  // ====================================================

  const mapContainer = document.getElementById(
    "checkout-delivery-map",
  );

  const savedAddress = document.getElementById(
    "checkout-saved-address",
  );

  const useLocationButton = document.getElementById(
    "checkout-use-location",
  );

  const confirmLocationButton =
    document.getElementById(
      "checkout-confirm-location",
    );

  const mapMessage = document.getElementById(
    "checkout-map-message",
  );

  const routeResult = document.getElementById(
    "checkout-route-result",
  );

  const routeDistance = document.getElementById(
    "checkout-route-distance",
  );

  const deliveryCostElement =
    document.getElementById(
      "checkout-delivery-cost",
    );

  const latitudeInput = document.getElementById(
    "checkout-delivery-latitude",
  );

  const longitudeInput = document.getElementById(
    "checkout-delivery-longitude",
  );

  const distanceInput = document.getElementById(
    "checkout-delivery-distance",
  );

  const quoteInput = document.getElementById(
    "checkout-delivery-quote",
  );

  // ====================================================
  // ELEMENTOS - TRANSPORTISTA
  // ====================================================

  const carrierSelect = document.getElementById(
    "checkout-carrier",
  );

  const carrierServiceSelect =
    document.getElementById(
      "checkout-carrier-service",
    );

  const carrierAgencySelect =
    document.getElementById(
      "checkout-carrier-agency",
    );

  const carrierMessage = document.getElementById(
    "checkout-carrier-message",
  );

  const carrierResult = document.getElementById(
    "checkout-carrier-result",
  );

  const carrierCostElement =
    document.getElementById(
      "checkout-carrier-cost",
    );

  // ====================================================
  // ELEMENTOS - RESUMEN
  // ====================================================

  const subtotalElement = document.getElementById(
    "checkout-summary-subtotal",
  );

  const deliveryRow = document.getElementById(
    "checkout-summary-delivery-row",
  );

  const summaryDelivery = document.getElementById(
    "checkout-summary-delivery",
  );

  const summaryTotal = document.getElementById(
    "checkout-summary-total",
  );

  // ====================================================
  // ELEMENTOS - MÉTODO DE PAGO
  // ====================================================

  const paymentOptions = document.getElementById(
    "checkout-payment-options",
  );

  const paymentMessage = document.getElementById(
    "checkout-payment-message",
  );

  const paymentMethodIdInput =
    document.getElementById(
      "checkout-payment-method-id",
    );

  const paymentCodeInput = document.getElementById(
    "checkout-payment-code",
  );

  const paymentModalityInput =
    document.getElementById(
      "checkout-payment-modality",
    );

  const paymentConfirmationTypeInput =
    document.getElementById(
      "checkout-payment-confirmation-type",
    );

    // ====================================================
    // ELEMENTOS - FACTURACIÓN
    // ====================================================

    const boletaRadio = document.getElementById(
    "checkout-boleta",
    );

    const facturaRadio = document.getElementById(
    "checkout-factura",
    );

    const dniInput = document.getElementById(
    "checkout-dni",
    );

    const rucInput = document.getElementById(
    "checkout-ruc",
    );

    const dniResult = document.getElementById(
    "checkout-dni-result",
    );

    const rucResult = document.getElementById(
    "checkout-ruc-result",
    );

  // ====================================================
  // ELEMENTOS - CONFIRMACIÓN DEL PEDIDO
  // ====================================================

  const confirmOrderButton =
    document.getElementById(
      "checkout-confirm-order",
    );

  const confirmHelp =
    document.getElementById(
      "checkout-confirm-help",
    );

  let checkoutProcessing = false;

  // ====================================================
  // PETICIONES HTTP
  // ====================================================

  async function getJSON(url) {
    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.mensaje ||
          "No se pudo obtener la información.",
      );
    }

    return data;
  }

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.mensaje ||
          "No se pudo completar la operación.",
      );
    }

    return data;
  }

  // ====================================================
  // MENSAJES
  // ====================================================

  function showMessage(
    element,
    text,
    type = "error",
  ) {
    if (!element) {
      return;
    }

    element.textContent = text;
    element.dataset.type = type;
  }

  function clearMessage(element) {
    if (!element) {
      return;
    }

    element.textContent = "";
    delete element.dataset.type;
  }

  // ====================================================
  // RESUMEN ECONÓMICO
  // ====================================================

  function getSubtotal() {
    if (!subtotalElement) {
      return 0;
    }

    const value = Number(
      subtotalElement.dataset.subtotal,
    );

    return Number.isFinite(value) ? value : 0;
  }

  function updateSummary(cost = 0) {
    deliveryCost = Number(cost) || 0;

    const subtotal = getSubtotal();
    const total = subtotal + deliveryCost;

    if (deliveryRow && summaryDelivery) {
      deliveryRow.hidden = false;

      summaryDelivery.textContent =
        `S/ ${deliveryCost.toFixed(2)}`;
    }

    if (summaryTotal) {
      summaryTotal.textContent =
        `S/ ${total.toFixed(2)}`;
    }
  }

  // ====================================================
  // DIRECCIÓN
  // ====================================================

  function initializeAddressForm() {
    /*
     * El formulario puede no existir cuando el usuario
     * ya tiene una dirección guardada.
     *
     * En ese caso solamente omitimos su inicialización.
     * El resto del checkout continúa funcionando.
     */

    if (!form) {
      return;
    }

    departmentSelect.addEventListener(
      "change",
      async () => {
        clearMessage(addressMessage);

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
            `/identidad/api/ubicacion/provincias/${departmentId}`,
          );

          data.provincias.forEach(
            (province) => {
              const option =
                document.createElement("option");

              option.value = province.id;
              option.textContent =
                province.nombre;

              provinceSelect.appendChild(
                option,
              );
            },
          );

          provinceSelect.disabled = false;
        } catch (error) {
          showMessage(
            addressMessage,
            error.message,
          );
        }
      },
    );

    provinceSelect.addEventListener(
      "change",
      async () => {
        clearMessage(addressMessage);

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
            `/identidad/api/ubicacion/distritos/${provinceId}`,
          );

          data.distritos.forEach(
            (district) => {
              const option =
                document.createElement("option");

              option.value = district.id;
              option.textContent =
                district.nombre;

              districtSelect.appendChild(
                option,
              );
            },
          );

          districtSelect.disabled = false;
        } catch (error) {
          showMessage(
            addressMessage,
            error.message,
          );
        }
      },
    );

    form.addEventListener(
      "submit",
      async (event) => {
        event.preventDefault();

        clearMessage(addressMessage);

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
            addressMessage,
            "Selecciona un distrito.",
          );

          return;
        }

        if (address.length < 5) {
          showMessage(
            addressMessage,
            "Ingresa una dirección válida.",
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
              distrito_id: districtId,
              direccion: address,
              referencia: reference,
              alias: alias,
              latitud: latitudeInput?.value || null,
              longitud: longitudeInput?.value || null,
            },
          );

          showMessage(
            addressMessage,
            data.mensaje,
            "success",
          );

          window.location.reload();
        } catch (error) {
          showMessage(
            addressMessage,
            error.message,
          );

          saveButton.disabled = false;

          saveButton.textContent =
            originalText;
        }
      },
    );
  }

  // ====================================================
  // OPCIONES DE ENTREGA
  // ====================================================

  async function loadDeliveryOptions() {
    if (!deliveryOptions) {
      return;
    }

    try {
      const data = await getJSON(
        "/operaciones/api/entregas/opciones",
      );
      originCoordinates = data.origen_delivery;

      deliveryOptions.innerHTML = "";

      if (
        !Array.isArray(data.opciones) ||
        data.opciones.length === 0
      ) {
        deliveryOptions.innerHTML = `
          <p>
            No hay opciones de entrega disponibles.
          </p>
        `;

        return;
      }

      data.opciones.forEach((option) => {
        const label =
          document.createElement("label");

        label.className =
          "checkout-delivery-option";

        const radio =
          document.createElement("input");

        radio.type = "radio";
        radio.name =
          "checkout_delivery_type";
        radio.value = option.tipo;

        const content =
          document.createElement("span");

        content.className =
          "checkout-delivery-option-content";

        const title =
          document.createElement("strong");

        title.textContent = option.nombre;

        const description =
          document.createElement("small");

        description.textContent =
          option.descripcion || "";

        content.appendChild(title);
        content.appendChild(description);

        label.appendChild(radio);
        label.appendChild(content);

        deliveryOptions.appendChild(label);

        if (
          option.tipo === "RECOJO_LOCAL"
        ) {
          pickupLocations =
            option.puntos_recojo || [];
        }

        if (
          option.tipo === "TRANSPORTISTA"
        ) {
          carriers =
            option.transportistas || [];
        }

        radio.addEventListener(
          "change",
          () => {
            selectDeliveryType(
              option.tipo,
            );
          },
        );
      });
    } catch (error) {
      deliveryOptions.innerHTML = "";

      showMessage(
        deliveryMessage,
        error.message,
      );
    }
  }

  // ====================================================
  // CAMBIO DE MODALIDAD
  // ====================================================

  function hideDeliveryPanels() {
    if (pickupPanel) {
      pickupPanel.hidden = true;
    }

    if (localDeliveryPanel) {
      localDeliveryPanel.hidden = true;
    }

    if (carrierPanel) {
      carrierPanel.hidden = true;
    }
  }

  function selectDeliveryType(type) {
    deliveryType = type;
    invalidateDestination();
    refreshAddressMode();

    hideDeliveryPanels();

    clearMessage(deliveryMessage);

    /*
     * Cada cambio de modalidad invalida:
     *
     * - la selección anterior de pago;
     * - la cotización anterior de entrega.
     */

    loadPaymentMethods(type);
    updateSummary(0);

    if (routeResult) {
      routeResult.hidden = true;
    }

    if (carrierResult) {
      carrierResult.hidden = true;
    }

    if (quoteInput) {
      quoteInput.value = "";
    }

    if (distanceInput) {
      distanceInput.value = "";
    }

    updateConfirmOrderButton();

    if (type === "RECOJO_LOCAL") {
      if (pickupPanel) {
        pickupPanel.hidden = false;
      }

      renderPickupLocations();

      return;
    }

    if (type === "DELIVERY_LOCAL") {
      if (localDeliveryPanel) {
        localDeliveryPanel.hidden = false;
      }

      initializeMap();

      /*
       * Leaflet necesita recalcular el tamaño
       * cuando el mapa estaba oculto.
       */

      setTimeout(() => {
        if (map) {
          map.invalidateSize();
        }
      }, 100);

      return;
    }

    if (type === "TRANSPORTISTA") {
      if (carrierPanel) {
        carrierPanel.hidden = false;
      }

      renderCarriers();
    }
  }

  // ====================================================
  // RECOJO EN LOCAL
  // ====================================================

  function renderPickupLocations() {
    if (!pickupLocationsContainer) {
      return;
    }

    pickupLocationsContainer.innerHTML = "";

    if (pickupLocations.length === 0) {
      pickupLocationsContainer.innerHTML = `
        <p>
          No hay puntos de recojo disponibles.
        </p>
      `;

      return;
    }

    if (!pickupLocations.some((p) => p.id === selectedPickupId)) {
      selectedPickupId = (pickupLocations.find((p) => p.codigo === 'SULPAA-EL-TAMBO') || pickupLocations[0]).id;
    }
    pickupLocations.forEach((location) => {
      const card =
        document.createElement("div");

      card.className = "checkout-field";
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'checkout_pickup_point';
      radio.value = location.id;
      radio.checked = location.id === selectedPickupId;
      radio.setAttribute('aria-label', location.nombre);
      const selectPoint = () => {
        selectedPickupId = location.id;
        destinationSummary.textContent = `${location.nombre} — ${location.direccion}`;
        updateConfirmOrderButton();
      };
      radio.addEventListener('change', selectPoint);
      card.appendChild(radio);
      if (radio.checked) selectPoint();

      const label =
        document.createElement("span");

      label.textContent =
        "Punto de recojo";

      const name =
        document.createElement("strong");

      name.textContent = location.nombre;

      const address =
        document.createElement("small");

      address.textContent =
        location.direccion || "";

      card.appendChild(label);
      card.appendChild(name);
      card.appendChild(address);

      pickupLocationsContainer.appendChild(
        card,
      );
    });
  }

  // ====================================================
  // GEOCODIFICACIÓN
  // ====================================================

  async function geocodeAddress(address) {
    const url =
      "https://nominatim.openstreetmap.org/search" +
      "?format=json" +
      "&limit=1" +
      "&countrycodes=pe" +
      `&q=${encodeURIComponent(address)}`;

    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(
        "No se pudo localizar la dirección en el mapa.",
      );
    }

    const results =
      await response.json();

    if (
      !Array.isArray(results) ||
      results.length === 0
    ) {
      throw new Error(
        "No encontramos esa dirección en el mapa.",
      );
    }

    return {
      latitude: Number(results[0].lat),
      longitude: Number(results[0].lon),
    };
  }

    // ====================================================
  // MAPA
  // ====================================================

  function initializeMap() {
    if (
      map ||
      !mapContainer ||
      typeof L === "undefined"
    ) {
      return;
    }

    /*
     * Vista inicial sobre Junín.
     *
     * Esto solo controla la cámara inicial.
     * NO representa el origen real del delivery.
     */

    map = L.map(
      "checkout-delivery-map",
    ).setView(
      [-12.065, -75.205],
      12,
    );

    L.tileLayer(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 19,
        attribution:
          "&copy; OpenStreetMap contributors",
      },
    ).addTo(map);

    /*
     * El cliente puede hacer clic en cualquier
     * punto para marcar exactamente el destino.
     */

    map.on("click", (event) => {
      setDestination(
        event.latlng.lat,
        event.latlng.lng,
      );
    });

    prepareOrigin();
    if (!destinationCoordinates && savedAddresses.length && savedSelector) {
      savedSelector.value = savedAddresses[0].id;
      savedSelector.dispatchEvent(new Event('change'));
    } else if (destinationCoordinates) {
      setDestination(destinationCoordinates.latitude, destinationCoordinates.longitude, true);
    }
  }

  // ====================================================
  // ORIGEN SULPAA
  // ====================================================

  async function prepareOrigin() {
    if (!originCoordinates) {
      showMessage(mapMessage, 'No hay un origen activo para delivery.');
      return;
    }

    if (map) {
      L.marker([
        originCoordinates.latitude,
        originCoordinates.longitude,
      ])
        .addTo(map)
        .bindPopup(`
          <strong>SULPAA</strong><br>
          Jr. Julio Sumar N.º 156<br>
          El Tambo, Huancayo
        `);
    }
  }

  // ====================================================
  // DIRECCIÓN GUARDADA DEL CLIENTE
  // ====================================================

  async function prepareSavedDestination() {
    if (!savedAddress || !map) {
      return;
    }

    const latitude = Number(
      savedAddress.dataset.latitude,
    );

    const longitude = Number(
      savedAddress.dataset.longitude,
    );

    if (
      Number.isFinite(latitude) &&
      Number.isFinite(longitude) &&
      latitude !== 0 &&
      longitude !== 0
    ) {
      setDestination(
        latitude,
        longitude,
      );

      map.setView(
        [latitude, longitude],
        16,
      );

      return;
    }

    const address =
      savedAddress.dataset.address;

    if (!address) {
      return;
    }

    /*
     * Intentamos ubicar la dirección escrita.
     * El cliente puede corregirla manualmente.
     */

    try {
      const coordinates =
        await geocodeAddress(
          `${address}, Junín, Perú`,
        );

      setDestination(
        coordinates.latitude,
        coordinates.longitude,
      );

      map.setView(
        [
          coordinates.latitude,
          coordinates.longitude,
        ],
        16,
      );
    } catch (error) {
      showMessage(
        mapMessage,
        "Selecciona en el mapa el punto exacto de entrega.",
      );
    }
  }

  // ====================================================
  // MARCADOR DESTINO
  // ====================================================

  function setDestination(
    latitude,
    longitude,
    preserveAddress = false,
  ) {
    invalidateDestination();
    const version = destinationVersion;
    if (!preserveAddress && savedSelector) savedSelector.value = '';
    destinationCoordinates = {
      latitude: Number(latitude),
      longitude: Number(longitude),
    };

    if (destinationMarker) {
      destinationMarker.setLatLng([
        latitude,
        longitude,
      ]);
    } else {
      destinationMarker = L.marker(
        [latitude, longitude],
        {
          draggable: true,
        },
      ).addTo(map);

      destinationMarker.on(
        "dragend",
        () => {
          const position =
            destinationMarker.getLatLng();

          setDestination(
            position.lat,
            position.lng,
          );
        },
      );
    }

    if (latitudeInput) {
      latitudeInput.value = latitude;
    }

    if (longitudeInput) {
      longitudeInput.value = longitude;
    }

    if (confirmLocationButton) {
      confirmLocationButton.disabled =
        false;
    }

    /*
     * Mover el punto invalida cualquier
     * cotización anterior.
     */

    if (routeResult) {
      routeResult.hidden = true;
    }

    if (quoteInput) {
      quoteInput.value = "";
    }

    if (distanceInput) {
      distanceInput.value = "";
    }

    if (
      deliveryType ===
      "DELIVERY_LOCAL"
    ) {
      updateSummary(0);
    }

    /*
     * Como la ubicación cambió, una cotización
     * anterior ya no puede habilitar la compra.
     */

    updateConfirmOrderButton();

    clearMessage(mapMessage);

    showMessage(
      mapMessage,
      "Ubicación seleccionada. Confírmala para calcular el delivery.",
      "success",
    );
    if (preserveAddress) {
      destinationSummary.textContent = addressInput.value;
      scheduleDeliveryQuote();
      return;
    }
    addressInput.value = '';
    referenceInput.value = '';
    destinationSummary.textContent = 'Buscando dirección del punto seleccionado…';
    fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}`,
      {headers: {Accept: 'application/json'}})
      .then((response) => { if (!response.ok) throw new Error(); return response.json(); })
      .then((data) => {
        if (version !== destinationVersion) return;
        if (!data.display_name || data.error) throw new Error();
        const a = data.address || {};
        const concise = [a.road, a.house_number, a.suburb, a.city || a.town || a.village].filter(Boolean).join(', ');
        addressInput.value = (concise.length >= 5 ? concise : data.display_name).slice(0, 255);
        destinationSummary.textContent = addressInput.value;
        showMessage(mapMessage, 'Dirección encontrada. Verifica el distrito y la referencia.', 'success');
        scheduleDeliveryQuote();
      }).catch(() => {
        if (version !== destinationVersion) return;
        destinationSummary.textContent = 'Completa la dirección del punto seleccionado.';
        showMessage(mapMessage, 'No se pudo obtener la dirección. Escríbela y confirma el distrito para cotizar.');
      });
  }

  // ====================================================
  // GEOLOCALIZACIÓN DEL NAVEGADOR
  // ====================================================

  if (useLocationButton) {
    useLocationButton.addEventListener(
      "click",
      () => {
        if (!navigator.geolocation) {
          showMessage(
            mapMessage,
            "Tu navegador no permite obtener la ubicación.",
          );

          return;
        }

        showMessage(
          mapMessage,
          "Obteniendo tu ubicación...",
          "info",
        );

        navigator.geolocation.getCurrentPosition(
          (position) => {
            const latitude =
              position.coords.latitude;

            const longitude =
              position.coords.longitude;

            setDestination(
              latitude,
              longitude,
            );

            map.setView(
              [latitude, longitude],
              17,
            );
          },

          () => {
            showMessage(
              mapMessage,
              "No pudimos obtener tu ubicación. Puedes marcarla directamente en el mapa.",
            );
          },

          {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 30000,
          },
        );
      },
    );
  }

  // ====================================================
  // RUTA POR CALLES
  // ====================================================

  async function calculateRoute() {
    if (!originCoordinates) {
      throw new Error(
        "Todavía no se pudo determinar la ubicación del local SULPAA.",
      );
    }

    if (!destinationCoordinates) {
      throw new Error(
        "Selecciona primero la ubicación de entrega.",
      );
    }

    const version = destinationVersion;

    // --------------------------------------------------------
    // Ruta por calles (mapa). La distancia se envía al backend;
    // el backend valida cobertura y calcula el costo real.
    // --------------------------------------------------------

    const origin =
      `${originCoordinates.longitude},` +
      `${originCoordinates.latitude}`;

    const destination =
      `${destinationCoordinates.longitude},` +
      `${destinationCoordinates.latitude}`;

    const url =
      "https://router.project-osrm.org/route/v1/driving/" +
      origin +
      ";" +
      destination +
      "?overview=full&geometries=geojson";

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(
        "No se pudo calcular la ruta de entrega.",
      );
    }

    const data = await response.json();

    if (
      data.code !== "Ok" ||
      !data.routes ||
      data.routes.length === 0
    ) {
      throw new Error(
        "No encontramos una ruta disponible.",
      );
    }

    const route = data.routes[0];

    const distanceKm = Number(
      (route.distance / 1000).toFixed(2),
    );

    drawRoute(route.geometry);

    const quote = await postJSON(
      "/operaciones/api/entregas/delivery/cotizar",
      {
        ...destinationPayload(),
        distancia_km: distanceKm,
      },
    );

    if (version !== destinationVersion || deliveryType !== 'DELIVERY_LOCAL') {
      throw new Error('El destino cambió. Confirma la nueva ubicación.');
    }
    deliveryQuote = quote;
    if (quote.direccion_entrega) {
      destinationSummary.textContent = quote.direccion_entrega;
    }
    return distanceKm;
  }

  // ====================================================
  // DIBUJAR RUTA
  // ====================================================

  function drawRoute(geometry) {
    if (routeLayer) {
      map.removeLayer(routeLayer);
    }

    routeLayer =
      L.geoJSON(geometry).addTo(map);

    map.fitBounds(
      routeLayer.getBounds(),
      {
        padding: [35, 35],
      },
    );
  }

  // ====================================================
  // CONFIRMAR UBICACIÓN Y COTIZAR
  // ====================================================

  if (confirmLocationButton) {
    confirmLocationButton.addEventListener(
      "click",
      async () => {
        confirmLocationButton.disabled =
          true;

        const originalText =
          confirmLocationButton.textContent;

        confirmLocationButton.textContent =
          "Calculando...";

        clearMessage(mapMessage);

        try {
          const distance =
            await calculateRoute();

          const roundedDistance =
            Number(
              distance.toFixed(2),
            );

          if (distanceInput) {
            distanceInput.value =
              roundedDistance;
          }

          /*
           * SEGURIDAD:
           *
           * JavaScript envía el destino. La distancia por calles
           * y la cotización provienen del backend.
           *
           * El backend vuelve a obtener:
           *
           * - carrito;
           * - peso;
           * - subtotal;
           * - tarifa vigente.
           */

          const quote = deliveryQuote;

          if (quoteInput) {
            quoteInput.value =
              quote.costo_entrega;
          }

          if (routeDistance) {
            routeDistance.textContent =
              `${roundedDistance.toFixed(2)} km`;
          }

          if (deliveryCostElement) {
            deliveryCostElement.textContent =
              `S/ ${Number(
                quote.costo_entrega,
              ).toFixed(2)}`;
          }

          if (routeResult) {
            routeResult.hidden = false;
          }

          updateSummary(
            quote.costo_entrega,
          );

          /*
           * La cotización ya es válida.
           * Revisamos si el checkout puede
           * habilitar la confirmación.
           */

          updateConfirmOrderButton();

          showMessage(
            mapMessage,
            "Ubicación confirmada y delivery calculado.",
            "success",
          );
        } catch (error) {
          /*
           * Si falla el cálculo, cualquier
           * cotización previa deja de ser válida.
           */

          if (routeResult) {
            routeResult.hidden = true;
          }

          if (quoteInput) {
            quoteInput.value = "";
          }

          updateSummary(0);
          updateConfirmOrderButton();

          showMessage(
            mapMessage,
            error.message,
          );
        } finally {
          confirmLocationButton.disabled =
            false;

          confirmLocationButton.textContent =
            originalText;
        }
      },
    );
  }

  // ====================================================
  // TRANSPORTISTAS
  // ====================================================

  function renderCarriers() {
    if (!carrierSelect) {
      return;
    }

    carrierSelect.innerHTML = `
      <option value="">
        Selecciona un transportista
      </option>
    `;

    carriers.forEach((carrier) => {
      const option =
        document.createElement("option");

      option.value = carrier.id;
      option.textContent =
        carrier.nombre;

      carrierSelect.appendChild(option);
    });

    carrierSelect.disabled =
      carriers.length === 0;
  }

  // ====================================================
  // SERVICIOS DEL TRANSPORTISTA
  // ====================================================

  if (carrierSelect) {
    carrierSelect.addEventListener(
      "change",
      async () => {
        clearMessage(carrierMessage);

        if (carrierResult) {
          carrierResult.hidden = true;
        }

        updateSummary(0);
        updateConfirmOrderButton();

        const carrierId =
          carrierSelect.value;

        carrierServiceSelect.innerHTML = `
          <option value="">
            Selecciona un servicio
          </option>
        `;

        carrierAgencySelect.innerHTML = `
          <option value="">
            Selecciona una agencia
          </option>
        `;

        carrierServiceSelect.disabled =
          true;

        carrierAgencySelect.disabled =
          true;

        if (!carrierId) {
          return;
        }

        try {
          const data = await getJSON(
            `/operaciones/api/transportistas/${carrierId}/servicios`,
          );

          data.servicios.forEach(
            (service) => {
              const option =
                document.createElement(
                  "option",
                );

              option.value = service.id;
              option.dataset.modalidad = service.modalidad;

              option.textContent =
                service.nombre;

              carrierServiceSelect.appendChild(
                option,
              );
            },
          );

          carrierServiceSelect.disabled =
            false;
        } catch (error) {
          showMessage(
            carrierMessage,
            error.message,
          );
        }
      },
    );
  }

  // ====================================================
  // AGENCIAS DEL TRANSPORTISTA
  // ====================================================

  if (carrierServiceSelect) {
    carrierServiceSelect.addEventListener(
      "change",
      async () => {
        const carrierId =
          carrierSelect.value;
        invalidateDestination();
        refreshAddressMode();

        if (carrierResult) {
          carrierResult.hidden = true;
        }

        updateSummary(0);
        updateConfirmOrderButton();

        if (!carrierId) {
          return;
        }

        carrierAgencySelect.innerHTML = `
          <option value="">
            Selecciona una agencia
          </option>
        `;

        carrierAgencySelect.disabled =
          true;

        try {
          const data = await getJSON(
            `/operaciones/api/transportistas/${carrierId}/agencias`,
          );

          data.sucursales.forEach(
            (agency) => {
              const option =
                document.createElement(
                  "option",
                );

              option.value = agency.id;

              option.textContent =
                `${agency.nombre} - ${agency.direccion}`;

              option.dataset.district =
                agency.distrito_id;
              option.dataset.address = agency.direccion;

              carrierAgencySelect.appendChild(
                option,
              );
            },
          );

          carrierAgencySelect.disabled =
            false;
        } catch (error) {
          showMessage(
            carrierMessage,
            error.message,
          );
        }
      },
    );
  }

  // ====================================================
  // COTIZACIÓN DEL TRANSPORTISTA
  // ====================================================

  if (carrierAgencySelect) {
    carrierAgencySelect.addEventListener(
      "change",
      async () => {
        const selectedOption =
          carrierAgencySelect.options[
            carrierAgencySelect.selectedIndex
          ];

        const carrierId =
          carrierSelect.value;

        const serviceId =
          carrierServiceSelect.value;

        const agencyId =
          carrierAgencySelect.value;

        const districtId =
          selectedOption?.dataset?.district;

        if (
          !carrierId ||
          !serviceId ||
          !agencyId ||
          !districtId
        ) {
          if (carrierResult) {
            carrierResult.hidden = true;
          }

          updateSummary(0);
          updateConfirmOrderButton();

          return;
        }

        clearMessage(carrierMessage);

        try {
           const quote =
             await postJSON(
               "/operaciones/api/entregas/transportista/cotizar",
               {
                 ...destinationPayload(),
                 tipo_entrega: "TRANSPORTISTA",
                 transportista_id: carrierId,
                 servicio_transportista_id: serviceId,
                 distrito_destino_id: districtId,
                 sucursal_destino_id: agencyId,
               },
             );

           carrierQuote = quote;
           const cost = Number(
             quote.costo_entrega,
           );

           if (carrierCostElement) {
             carrierCostElement.textContent =
               `S/ ${cost.toFixed(2)}`;
           }

           if (carrierResult) {
             carrierResult.hidden = false;
           }

           updateSummary(cost);
           updateConfirmOrderButton();

           showMessage(
             carrierMessage,
             "Envío calculado correctamente.",
             "success",
           );
         } catch (error) {
          if (carrierResult) {
            carrierResult.hidden = true;
          }

          updateSummary(0);
          updateConfirmOrderButton();

          showMessage(
            carrierMessage,
            error.message,
          );
        }
      },
    );
  }
    // ====================================================
  // ESTADO DEL BOTÓN CONFIRMAR PEDIDO
  // ====================================================

  function updateConfirmOrderButton() {
  if (!confirmOrderButton) {
    return;
  }

  let ready = true;
  let message =
    "Revisa tu pedido y confirma la compra.";

  // --------------------------------------------------
  // FACTURACIÓN OBLIGATORIA
  // --------------------------------------------------

  const boletaSeleccionada =
    Boolean(boletaRadio?.checked);

  const facturaSeleccionada =
    Boolean(facturaRadio?.checked);

  const dniVerificado =
    Boolean(
      boletaSeleccionada &&
      dniInput?.value.trim().length === 8 &&
      dniResult &&
      !dniResult.hidden
    );

  const rucVerificado =
    Boolean(
      facturaSeleccionada &&
      rucInput?.value.trim().length === 11 &&
      rucResult &&
      !rucResult.hidden
    );

  if (
    !boletaSeleccionada &&
    !facturaSeleccionada
  ) {
    ready = false;
    message =
      "Selecciona Boleta o Factura.";
  } else if (
    boletaSeleccionada &&
    !dniVerificado
  ) {
    ready = false;
    message =
      "Verifica tu DNI para continuar.";
  } else if (
    facturaSeleccionada &&
    !rucVerificado
  ) {
    ready = false;
    message =
      "Verifica el RUC para continuar.";
  } else if (!deliveryType) {
    ready = false;
    message =
      "Selecciona una modalidad de entrega.";
  } else if (!selectedPaymentMethod) {
    ready = false;
    message =
      "Selecciona un método de pago.";
  } else if (
    deliveryType === "DELIVERY_LOCAL" &&
    (
      !distanceInput?.value ||
      !quoteInput?.value
    )
  ) {
    ready = false;
    message =
      "Confirma la ubicación y calcula el delivery.";
  } else if (
    deliveryType === "TRANSPORTISTA" &&
    (
      !carrierSelect?.value ||
      !carrierServiceSelect?.value ||
      !carrierAgencySelect?.value ||
      !carrierResult ||
      carrierResult.hidden
    )
  ) {
    ready = false;
    message =
      "Selecciona transportista, servicio y agencia.";
  }

  confirmOrderButton.disabled =
    !ready || checkoutProcessing;

  if (confirmHelp) {
    confirmHelp.textContent = message;
  }
}

  // ====================================================
  // MÉTODOS DE PAGO
  // ====================================================

  function resetPaymentSelection() {
    selectedPaymentMethod = null;

    if (paymentMethodIdInput) {
      paymentMethodIdInput.value = "";
    }

    if (paymentCodeInput) {
      paymentCodeInput.value = "";
    }

    if (paymentModalityInput) {
      paymentModalityInput.value = "";
    }

    if (paymentConfirmationTypeInput) {
      paymentConfirmationTypeInput.value =
        "";
    }

    updateConfirmOrderButton();
  }

  function getPaymentBadge(method) {
    if (method.codigo === "EFECTIVO") {
      if (
        method.modalidad ===
        "PAGO_EN_LOCAL"
      ) {
        return "PAGO EN LOCAL";
      }

      return "PAGO AL RECIBIR";
    }

    return "PAGO ANTICIPADO";
  }

  function selectPaymentMethod(method) {
    selectedPaymentMethod = method;

    if (paymentMethodIdInput) {
      paymentMethodIdInput.value =
        method.id;
    }

    if (paymentCodeInput) {
      paymentCodeInput.value =
        method.codigo;
    }

    if (paymentModalityInput) {
      paymentModalityInput.value =
        method.modalidad;
    }

    if (paymentConfirmationTypeInput) {
      paymentConfirmationTypeInput.value =
        method.tipo_confirmacion;
    }

    clearMessage(paymentMessage);

    showMessage(
      paymentMessage,
      `${method.nombre} seleccionado correctamente.`,
      "success",
    );

    updateConfirmOrderButton();
  }

  function renderPaymentMethods(methods) {
    if (!paymentOptions) {
      return;
    }

    paymentOptions.innerHTML = "";

    if (
      !Array.isArray(methods) ||
      methods.length === 0
    ) {
      paymentOptions.innerHTML = `
        <p>
          No hay métodos de pago disponibles.
        </p>
      `;

      return;
    }

    methods.forEach((method) => {
      const label =
        document.createElement("label");

      label.className =
        "checkout-payment-option";

      const radio =
        document.createElement("input");

      radio.type = "radio";
      radio.name =
        "checkout_payment_method";
      radio.value = method.id;

      const content =
        document.createElement("span");

      content.className =
        "checkout-payment-option-content";

      const title =
        document.createElement("strong");

      title.textContent = method.nombre;

      const description =
        document.createElement("small");

      description.textContent =
        method.descripcion || "";

      const badge =
        document.createElement("span");

      badge.className =
        "checkout-payment-badge";

      badge.textContent =
        getPaymentBadge(method);

      content.appendChild(title);
      content.appendChild(description);
      content.appendChild(badge);

      label.appendChild(radio);
      label.appendChild(content);

      paymentOptions.appendChild(label);

      radio.addEventListener(
        "change",
        () => {
          selectPaymentMethod(method);
        },
      );
    });
  }

  async function loadPaymentMethods(type) {
    if (!paymentOptions) {
      return;
    }

    resetPaymentSelection();
    clearMessage(paymentMessage);

    paymentOptions.innerHTML = `
      <p>
        Cargando métodos de pago...
      </p>
    `;

    if (!type) {
      paymentOptions.innerHTML = `
        <p>
          Selecciona una modalidad de entrega
          para continuar.
        </p>
      `;

      return;
    }

    try {
      const data = await getJSON(
        "/operaciones/api/metodos-pago" +
          `?tipo_entrega=${encodeURIComponent(
            type,
          )}`,
      );

      renderPaymentMethods(
        data.metodos_pago || [],
      );
    } catch (error) {
      paymentOptions.innerHTML = "";

      showMessage(
        paymentMessage,
        error.message,
      );

      updateConfirmOrderButton();
    }
  }

  // ====================================================
  // CONSTRUCCIÓN DEL PAYLOAD FINAL
  // ====================================================

  function buildCheckoutPayload() {
    const boletaSeleccionada =
  Boolean(boletaRadio?.checked);

    const facturaSeleccionada =
    Boolean(facturaRadio?.checked);

    let tipoComprobante = "";
    let documentoFacturacion = "";

    if (boletaSeleccionada) {
    tipoComprobante = "BOLETA";

    documentoFacturacion =
        dniInput?.value
        .replace(/\D/g, "")
        .slice(0, 8) || "";

    if (
        documentoFacturacion.length !== 8 ||
        !dniResult ||
        dniResult.hidden
    ) {
        throw new Error(
        "Debes verificar tu DNI antes de confirmar la compra.",
        );
    }
    } else if (facturaSeleccionada) {
    tipoComprobante = "FACTURA";

    documentoFacturacion =
        rucInput?.value
        .replace(/\D/g, "")
        .slice(0, 11) || "";

    if (
        documentoFacturacion.length !== 11 ||
        !rucResult ||
        rucResult.hidden
    ) {
        throw new Error(
        "Debes verificar el RUC antes de confirmar la compra.",
        );
    }
    } else {
    throw new Error(
        "Debes seleccionar Boleta o Factura.",
    );
    }
    if (!deliveryType) {
      throw new Error(
        "Selecciona una modalidad de entrega.",
      );
    }

    if (!selectedPaymentMethod) {
      throw new Error(
        "Selecciona un método de pago.",
      );
    }

    const payload = {
        tipo_comprobante:
            tipoComprobante,

        documento_facturacion:
            documentoFacturacion,

        tipo_entrega:
            deliveryType,

        metodo_pago_id:
            selectedPaymentMethod.id,
        };

    // --------------------------------------------------
    // RECOJO LOCAL
    // --------------------------------------------------

    if (
      deliveryType === "RECOJO_LOCAL"
    ) {
      return payload;
    }

    // --------------------------------------------------
    // DELIVERY LOCAL
    // --------------------------------------------------

    if (
      deliveryType === "DELIVERY_LOCAL"
    ) {
      if (!deliveryQuote) {
        throw new Error(
          "Primero debes cotizar el delivery con tu dirección.",
        );
      }

      return {
        ...payload,
        ...destinationPayload(),
        tipo_entrega: "DELIVERY_LOCAL",
        distancia_km: deliveryQuote.distancia_km,
        cotizacion_token: deliveryQuote.cotizacion_token,
      };
    }

    // --------------------------------------------------
    // TRANSPORTISTA
    // --------------------------------------------------

    if (
      deliveryType === "TRANSPORTISTA"
    ) {
      const carrierId =
        carrierSelect?.value;

      const serviceId =
        carrierServiceSelect?.value;

      const agencyId =
        carrierAgencySelect?.value;

      const selectedAgency =
        carrierAgencySelect?.options[
          carrierAgencySelect.selectedIndex
        ];

      const districtId =
        selectedAgency?.dataset?.district;

      if (!carrierId) {
        throw new Error(
          "Selecciona un transportista.",
        );
      }

      if (!serviceId) {
        throw new Error(
          "Selecciona un servicio de envío.",
        );
      }

      if (!agencyId) {
        throw new Error(
          "Selecciona una agencia de destino.",
        );
      }

      if (!districtId) {
        throw new Error(
          "No se pudo determinar el distrito de destino.",
        );
      }

      if (
        !carrierResult ||
        carrierResult.hidden
      ) {
        throw new Error(
          "Primero calcula el costo del envío.",
        );
      }

      if (!carrierQuote) {
        throw new Error(
          "Primero debes cotizar el envío.",
        );
      }

      return {
        ...payload,
        ...destinationPayload(),
        tipo_entrega: "TRANSPORTISTA",
        transportista_id: carrierId,
        servicio_transportista_id: serviceId,
        distrito_destino_id: districtId,
        sucursal_destino_id: agencyId,
        cotizacion_token: carrierQuote.cotizacion_token,
      };
    }

    throw new Error(
      "La modalidad de entrega no es válida.",
    );
  }

  // ====================================================
  // CONFIRMACIÓN FINAL DEL CHECKOUT
  // ====================================================

  async function confirmCheckoutOrder() {
    if (checkoutProcessing) {
      return;
    }

    let originalText =
      "Confirmar pedido";

    try {
      const payload =
        buildCheckoutPayload();

      console.log("CHECKOUT PAYLOAD:", payload);

      checkoutProcessing = true;

      if (confirmOrderButton) {
        originalText =
          confirmOrderButton.textContent;

        confirmOrderButton.disabled =
          true;

        confirmOrderButton.textContent =
          "Procesando pedido...";
      }

      if (confirmHelp) {
        confirmHelp.textContent =
          "Estamos confirmando tu pedido...";
      }

      /*
       * SEGURIDAD:
       *
       * El navegador NO envía como valores
       * confiables:
       *
       * - subtotal;
       * - precio de productos;
       * - peso;
       * - total;
       * - costo de entrega.
       *
       * El backend vuelve a reconstruir y
       * validar toda esa información.
       */

      const data = await postJSON(
        "/api/checkout/confirmar",
        payload,
      );

      if (!data.ok) {
        throw new Error(
          data.mensaje ||
            "No se pudo confirmar el pedido.",
        );
      }

      if (confirmHelp) {
        confirmHelp.textContent =
          `Pedido ${data.numero_pedido} confirmado correctamente.`;
      }

      alert(
        "¡Pedido confirmado correctamente!\n\n" +
          `Pedido: ${data.numero_pedido}\n` +
          `Subtotal: S/ ${Number(
            data.subtotal,
          ).toFixed(2)}\n` +
          `Entrega: S/ ${Number(
            data.costo_entrega,
          ).toFixed(2)}\n` +
          `Total: S/ ${Number(
            data.total,
          ).toFixed(2)}`,
      );

      /*
       * El carrito ya quedó CONVERTIDO.
       * Regresamos a la tienda.
       */

      window.location.href = "/tienda";
    } catch (error) {
      console.error(
        "Error al confirmar checkout:",
        error,
      );

      checkoutProcessing = false;

      if (confirmOrderButton) {
        confirmOrderButton.textContent =
          originalText;
      }

      if (confirmHelp) {
        confirmHelp.textContent =
          error.message ||
          "No se pudo confirmar el pedido.";
      }

      alert(
        error.message ||
          "No se pudo confirmar el pedido.",
      );

      updateConfirmOrderButton();
    }
  }

  // ====================================================
  // EVENTO - CONFIRMAR PEDIDO
  // ====================================================

  if (confirmOrderButton) {
    confirmOrderButton.addEventListener(
      "click",
      confirmCheckoutOrder,
    );
  }


  // ====================================================
  // CAMBIOS EN FACTURACIÓN
    // ====================================================
    //
    // checkout-billing.js informa a este módulo cuando:
    //
    // - se selecciona Boleta o Factura;
    // - se verifica correctamente un DNI o RUC;
    // - se modifica un documento previamente verificado.
    //
    // De esta forma el botón "Confirmar pedido" siempre
    // refleja el estado real de la facturación.
    // ====================================================

  window.addEventListener(
  "checkout:billing-updated",
  () => {
      updateConfirmOrderButton();
  },
  );

  // ====================================================
  // INICIALIZACIÓN
  // ====================================================

  initializeAddressForm();
  loadDeliveryOptions();
  updateConfirmOrderButton();
});
