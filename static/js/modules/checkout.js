"use strict";

document.addEventListener("DOMContentLoaded", () => {
  // ====================================================
  // ESTADO GENERAL DEL CHECKOUT
  // ====================================================

  let deliveryType = null;
  let deliveryCost = 0;

  let map = null;
  let destinationMarker = null;
  let routeLayer = null;

  let originCoordinates = null;
  let destinationCoordinates = null;

  let pickupLocations = [];
  let carriers = [];

  // ====================================================
  // ELEMENTOS - DIRECCIÓN
  // ====================================================

  const form = document.getElementById("checkout-address-form");

  const departmentSelect = document.getElementById("checkout-department");

  const provinceSelect = document.getElementById("checkout-province");

  const districtSelect = document.getElementById("checkout-district");

  const addressInput = document.getElementById("checkout-address");

  const referenceInput = document.getElementById("checkout-reference");

  const aliasInput = document.getElementById("checkout-address-alias");

  const addressMessage = document.getElementById("checkout-address-message");

  const saveButton = document.getElementById("checkout-save-address");

  // ====================================================
  // ELEMENTOS - ENTREGA
  // ====================================================

  const deliveryOptions = document.getElementById("checkout-delivery-options");

  const deliveryMessage = document.getElementById("checkout-delivery-message");

  const pickupPanel = document.getElementById("checkout-pickup-panel");

  const pickupLocationsContainer = document.getElementById(
    "checkout-pickup-locations",
  );

  const localDeliveryPanel = document.getElementById(
    "checkout-local-delivery-panel",
  );

  const carrierPanel = document.getElementById("checkout-carrier-panel");

  // ====================================================
  // ELEMENTOS - MAPA
  // ====================================================

  const mapContainer = document.getElementById("checkout-delivery-map");

  const deliveryOrigin = document.getElementById("checkout-delivery-origin");

  const savedAddress = document.getElementById("checkout-saved-address");

  const useLocationButton = document.getElementById("checkout-use-location");

  const confirmLocationButton = document.getElementById(
    "checkout-confirm-location",
  );

  const mapMessage = document.getElementById("checkout-map-message");

  const routeResult = document.getElementById("checkout-route-result");

  const routeDistance = document.getElementById("checkout-route-distance");

  const deliveryCostElement = document.getElementById("checkout-delivery-cost");

  const latitudeInput = document.getElementById("checkout-delivery-latitude");

  const longitudeInput = document.getElementById("checkout-delivery-longitude");

  const distanceInput = document.getElementById("checkout-delivery-distance");

  const quoteInput = document.getElementById("checkout-delivery-quote");

  // ====================================================
  // ELEMENTOS - TRANSPORTISTA
  // ====================================================

  const carrierSelect = document.getElementById("checkout-carrier");

  const carrierServiceSelect = document.getElementById(
    "checkout-carrier-service",
  );

  const carrierAgencySelect = document.getElementById(
    "checkout-carrier-agency",
  );

  const carrierMessage = document.getElementById("checkout-carrier-message");

  const carrierResult = document.getElementById("checkout-carrier-result");

  const carrierCostElement = document.getElementById("checkout-carrier-cost");

  // ====================================================
  // ELEMENTOS - RESUMEN
  // ====================================================

  const subtotalElement = document.getElementById("checkout-summary-subtotal");

  const deliveryRow = document.getElementById("checkout-summary-delivery-row");

  const summaryDelivery = document.getElementById("checkout-summary-delivery");

  const summaryTotal = document.getElementById("checkout-summary-total");

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
      throw new Error(data.mensaje || "No se pudo obtener la información.");
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
      throw new Error(data.mensaje || "No se pudo completar la operación.");
    }

    return data;
  }

  // ====================================================
  // MENSAJES
  // ====================================================

  function showMessage(element, text, type = "error") {
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

    const value = Number(subtotalElement.dataset.subtotal);

    return Number.isFinite(value) ? value : 0;
  }

  function updateSummary(cost = 0) {
    deliveryCost = Number(cost) || 0;

    const subtotal = getSubtotal();

    const total = subtotal + deliveryCost;

    if (deliveryRow && summaryDelivery) {
      deliveryRow.hidden = false;

      summaryDelivery.textContent = `S/ ${deliveryCost.toFixed(2)}`;
    }

    if (summaryTotal) {
      summaryTotal.textContent = `S/ ${total.toFixed(2)}`;
    }
  }

  // ====================================================
  // DIRECCIÓN
  // ====================================================

  function initializeAddressForm() {
    /*
     * Importante:
     *
     * Antes este archivo terminaba completamente si el
     * formulario no existía.
     *
     * Eso impedía ejecutar entrega y mapa cuando el
     * usuario ya tenía una dirección guardada.
     */

    if (!form) {
      return;
    }

    departmentSelect.addEventListener("change", async () => {
      clearMessage(addressMessage);

      const departmentId = departmentSelect.value;

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

        data.provincias.forEach((province) => {
          const option = document.createElement("option");

          option.value = province.id;

          option.textContent = province.nombre;

          provinceSelect.appendChild(option);
        });

        provinceSelect.disabled = false;
      } catch (error) {
        showMessage(addressMessage, error.message);
      }
    });

    provinceSelect.addEventListener("change", async () => {
      clearMessage(addressMessage);

      const provinceId = provinceSelect.value;

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

        data.distritos.forEach((district) => {
          const option = document.createElement("option");

          option.value = district.id;

          option.textContent = district.nombre;

          districtSelect.appendChild(option);
        });

        districtSelect.disabled = false;
      } catch (error) {
        showMessage(addressMessage, error.message);
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      clearMessage(addressMessage);

      const districtId = districtSelect.value;

      const address = addressInput.value.trim();

      const reference = referenceInput.value.trim();

      const alias = aliasInput.value.trim();

      if (!districtId) {
        showMessage(addressMessage, "Selecciona un distrito.");

        return;
      }

      if (address.length < 5) {
        showMessage(addressMessage, "Ingresa una dirección válida.");

        addressInput.focus();

        return;
      }

      saveButton.disabled = true;

      const originalText = saveButton.textContent;

      saveButton.textContent = "Guardando...";

      try {
        const data = await postJSON("/identidad/api/direcciones", {
          distrito_id: districtId,

          direccion: address,

          referencia: reference,

          alias: alias,
        });

        showMessage(addressMessage, data.mensaje, "success");

        window.location.reload();
      } catch (error) {
        showMessage(addressMessage, error.message);

        saveButton.disabled = false;

        saveButton.textContent = originalText;
      }
    });
  }

  // ====================================================
  // OPCIONES DE ENTREGA
  // ====================================================

  async function loadDeliveryOptions() {
    if (!deliveryOptions) {
      return;
    }

    try {
      const data = await getJSON("/operaciones/api/entregas/opciones");

      deliveryOptions.innerHTML = "";

      if (!Array.isArray(data.opciones) || data.opciones.length === 0) {
        deliveryOptions.innerHTML = `
                        <p>
                            No hay opciones de entrega disponibles.
                        </p>
                    `;

        return;
      }

      data.opciones.forEach((option) => {
        const label = document.createElement("label");

        label.className = "checkout-delivery-option";

        const radio = document.createElement("input");

        radio.type = "radio";

        radio.name = "checkout_delivery_type";

        radio.value = option.tipo;

        const content = document.createElement("span");

        content.className = "checkout-delivery-option-content";

        const title = document.createElement("strong");

        title.textContent = option.nombre;

        const description = document.createElement("small");

        description.textContent = option.descripcion || "";

        content.appendChild(title);

        content.appendChild(description);

        label.appendChild(radio);

        label.appendChild(content);

        deliveryOptions.appendChild(label);

        if (option.tipo === "RECOJO_LOCAL") {
          pickupLocations = option.puntos_recojo || [];
        }

        if (option.tipo === "TRANSPORTISTA") {
          carriers = option.transportistas || [];
        }

        radio.addEventListener("change", () => {
          selectDeliveryType(option.tipo);
        });
      });
    } catch (error) {
      deliveryOptions.innerHTML = "";

      showMessage(deliveryMessage, error.message);
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

    hideDeliveryPanels();

    clearMessage(deliveryMessage);

    if (routeResult) {
      routeResult.hidden = true;
    }

    if (carrierResult) {
      carrierResult.hidden = true;
    }

    if (type === "RECOJO_LOCAL") {
      pickupPanel.hidden = false;

      renderPickupLocations();

      updateSummary(0);

      return;
    }

    if (type === "DELIVERY_LOCAL") {
      localDeliveryPanel.hidden = false;

      initializeMap();

      /*
       * Leaflet necesita recalcular el tamaño
       * cuando un mapa estaba dentro de un
       * elemento oculto.
       */

      setTimeout(() => {
        if (map) {
          map.invalidateSize();
        }
      }, 100);

      return;
    }

    if (type === "TRANSPORTISTA") {
      carrierPanel.hidden = false;

      renderCarriers();

      return;
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

    pickupLocations.forEach((location) => {
      const card = document.createElement("div");

      card.className = "checkout-field";

      const label = document.createElement("span");

      label.textContent = "Punto de recojo";

      const name = document.createElement("strong");

      name.textContent = location.nombre;

      const address = document.createElement("small");

      address.textContent = location.direccion || "";

      card.appendChild(label);

      card.appendChild(name);

      card.appendChild(address);

      pickupLocationsContainer.appendChild(card);
    });
  }

  // ====================================================
  // GEOCODIFICACIÓN
  // ====================================================

  async function geocodeAddress(address) {
    const url =
      "https://nominatim.openstreetmap.org/search" +
      `?format=json` +
      `&limit=1` +
      `&countrycodes=pe` +
      `&q=${encodeURIComponent(address)}`;

    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      throw new Error("No se pudo localizar la dirección en el mapa.");
    }

    const results = await response.json();

    if (!Array.isArray(results) || results.length === 0) {
      throw new Error("No encontramos esa dirección en el mapa.");
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
    if (map || !mapContainer || typeof L === "undefined") {
      return;
    }

    /*
     * Vista inicial sobre Junín.
     *
     * Esto solo controla la cámara inicial.
     * NO representa el origen real del delivery.
     */

    map = L.map("checkout-delivery-map").setView([-12.065, -75.205], 12);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,

      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    /*
     * El cliente puede hacer clic en cualquier
     * punto para marcar exactamente el destino.
     */

    map.on("click", (event) => {
      setDestination(event.latlng.lat, event.latlng.lng);
    });

    prepareOrigin();

    prepareSavedDestination();
  }

  // ====================================================
  // ORIGEN SULPAA
  // ====================================================

  async function prepareOrigin() {
    originCoordinates = {
      latitude: -12.049141052234061,
      longitude: -75.22147546622413,
    };

    if (map) {
      L.marker([originCoordinates.latitude, originCoordinates.longitude])
        .addTo(map)
        .bindPopup(
          `
            <strong>SULPAA</strong><br>
            Jr. Julio Sumar N.º 156<br>
            El Tambo, Huancayo
            `,
        );
    }
  }

  // ====================================================
  // DIRECCIÓN GUARDADA DEL CLIENTE
  // ====================================================

  async function prepareSavedDestination() {
    if (!savedAddress) {
      return;
    }

    const latitude = Number(savedAddress.dataset.latitude);

    const longitude = Number(savedAddress.dataset.longitude);

    if (
      Number.isFinite(latitude) &&
      Number.isFinite(longitude) &&
      latitude !== 0 &&
      longitude !== 0
    ) {
      setDestination(latitude, longitude);

      map.setView([latitude, longitude], 16);

      return;
    }

    const address = savedAddress.dataset.address;

    if (!address) {
      return;
    }

    /*
     * Intentamos ubicar la dirección escrita.
     *
     * El usuario siempre podrá corregir la posición
     * haciendo clic sobre el mapa.
     */

    try {
      const coordinates = await geocodeAddress(`${address}, Junín, Perú`);

      setDestination(coordinates.latitude, coordinates.longitude);

      map.setView([coordinates.latitude, coordinates.longitude], 16);
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

  function setDestination(latitude, longitude) {
    destinationCoordinates = {
      latitude: Number(latitude),

      longitude: Number(longitude),
    };

    if (destinationMarker) {
      destinationMarker.setLatLng([latitude, longitude]);
    } else {
      destinationMarker = L.marker([latitude, longitude], {
        draggable: true,
      }).addTo(map);

      destinationMarker.on("dragend", () => {
        const position = destinationMarker.getLatLng();

        setDestination(position.lat, position.lng);
      });
    }

    latitudeInput.value = latitude;

    longitudeInput.value = longitude;

    confirmLocationButton.disabled = false;

    clearMessage(mapMessage);

    showMessage(
      mapMessage,
      "Ubicación seleccionada. Confírmala para calcular el delivery.",
      "success",
    );
  }

  // ====================================================
  // GEOLOCALIZACIÓN DEL NAVEGADOR
  // ====================================================

  if (useLocationButton) {
    useLocationButton.addEventListener("click", () => {
      if (!navigator.geolocation) {
        showMessage(
          mapMessage,
          "Tu navegador no permite obtener la ubicación.",
        );

        return;
      }

      showMessage(mapMessage, "Obteniendo tu ubicación...", "info");

      navigator.geolocation.getCurrentPosition(
        (position) => {
          const latitude = position.coords.latitude;

          const longitude = position.coords.longitude;

          setDestination(latitude, longitude);

          map.setView([latitude, longitude], 17);
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
    });
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
      throw new Error("Selecciona primero la ubicación de entrega.");
    }

    const origin = `${originCoordinates.longitude},${originCoordinates.latitude}`;

    const destination = `${destinationCoordinates.longitude},${destinationCoordinates.latitude}`;

    const url =
      "https://router.project-osrm.org/route/v1/driving/" +
      origin +
      ";" +
      destination +
      "?overview=full&geometries=geojson";

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error("No se pudo calcular la ruta de entrega.");
    }

    const data = await response.json();

    if (data.code !== "Ok" || !data.routes || data.routes.length === 0) {
      throw new Error("No encontramos una ruta disponible.");
    }

    const route = data.routes[0];

    const distanceKm = route.distance / 1000;

    drawRoute(route.geometry);

    return distanceKm;
  }

  // ====================================================
  // DIBUJAR RUTA
  // ====================================================

  function drawRoute(geometry) {
    if (routeLayer) {
      map.removeLayer(routeLayer);
    }

    routeLayer = L.geoJSON(geometry).addTo(map);

    map.fitBounds(routeLayer.getBounds(), {
      padding: [35, 35],
    });
  }

  // ====================================================
  // CONFIRMAR UBICACIÓN Y COTIZAR
  // ====================================================

  if (confirmLocationButton) {
    confirmLocationButton.addEventListener("click", async () => {
      confirmLocationButton.disabled = true;

      const originalText = confirmLocationButton.textContent;

      confirmLocationButton.textContent = "Calculando...";

      clearMessage(mapMessage);

      try {
        const distance = await calculateRoute();

        const roundedDistance = Number(distance.toFixed(2));

        distanceInput.value = roundedDistance;

        /*
         * Seguridad:
         *
         * JavaScript únicamente envía distancia.
         *
         * El backend debe obtener nuevamente:
         *
         * - peso del carrito;
         * - subtotal;
         * - tarifa activa.
         */

        const quote = await postJSON(
          "/operaciones/api/entregas/delivery/cotizar",
          {
            distancia_km: roundedDistance,
          },
        );

        quoteInput.value = quote.costo_entrega;

        routeDistance.textContent = `${roundedDistance.toFixed(2)} km`;

        deliveryCostElement.textContent = `S/ ${Number(
          quote.costo_entrega,
        ).toFixed(2)}`;

        routeResult.hidden = false;

        updateSummary(quote.costo_entrega);

        showMessage(
          mapMessage,
          "Ubicación confirmada y delivery calculado.",
          "success",
        );
      } catch (error) {
        showMessage(mapMessage, error.message);
      } finally {
        confirmLocationButton.disabled = false;

        confirmLocationButton.textContent = originalText;
      }
    });
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
      const option = document.createElement("option");

      option.value = carrier.id;

      option.textContent = carrier.nombre;

      carrierSelect.appendChild(option);
    });

    carrierSelect.disabled = carriers.length === 0;
  }

  // ====================================================
  // SERVICIOS DEL TRANSPORTISTA
  // ====================================================

  if (carrierSelect) {
    carrierSelect.addEventListener("change", async () => {
      clearMessage(carrierMessage);

      const carrierId = carrierSelect.value;

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

      carrierServiceSelect.disabled = true;
      carrierAgencySelect.disabled = true;

      if (!carrierId) {
        return;
      }

      try {
        const data = await getJSON(
          `/operaciones/api/transportistas/${carrierId}/servicios`,
        );

        data.servicios.forEach((service) => {
          const option = document.createElement("option");

          option.value = service.id;

          option.textContent = service.nombre;

          carrierServiceSelect.appendChild(option);
        });

        carrierServiceSelect.disabled = false;
      } catch (error) {
        showMessage(carrierMessage, error.message);
      }
    });
  }

  // ====================================================
  // AGENCIAS DEL TRANSPORTISTA
  // ====================================================

  if (carrierServiceSelect) {
    carrierServiceSelect.addEventListener("change", async () => {
      const carrierId = carrierSelect.value;

      if (!carrierId) {
        return;
      }

      carrierAgencySelect.innerHTML = `
                        <option value="">
                            Selecciona una agencia
                        </option>
                    `;

      carrierAgencySelect.disabled = true;

      try {
        const data = await getJSON(
          `/operaciones/api/transportistas/${carrierId}/agencias`,
        );

        data.sucursales.forEach((agency) => {
          const option = document.createElement("option");

          option.value = agency.id;

          option.textContent = `${agency.nombre} - ${agency.direccion}`;

          option.dataset.district = agency.distrito_id;

          carrierAgencySelect.appendChild(option);
        });

        carrierAgencySelect.disabled = false;
      } catch (error) {
        showMessage(carrierMessage, error.message);
      }
    });
  }

  // ====================================================
  // COTIZACIÓN DEL TRANSPORTISTA
  // ====================================================

  if (carrierAgencySelect) {
    carrierAgencySelect.addEventListener("change", async () => {
      const selectedOption =
        carrierAgencySelect.options[carrierAgencySelect.selectedIndex];

      const carrierId = carrierSelect.value;

      const serviceId = carrierServiceSelect.value;

      const agencyId = carrierAgencySelect.value;

      const districtId = selectedOption?.dataset?.district;

      if (!carrierId || !serviceId || !agencyId || !districtId) {
        return;
      }

      try {
        const quote = await postJSON(
          "/operaciones/api/entregas/transportista/cotizar",
          {
            transportista_id: carrierId,

            servicio_transportista_id: serviceId,

            distrito_destino_id: districtId,

            sucursal_destino_id: agencyId,
          },
        );

        const cost = Number(quote.costo_entrega);

        carrierCostElement.textContent = `S/ ${cost.toFixed(2)}`;

        carrierResult.hidden = false;

        updateSummary(cost);

        showMessage(
          carrierMessage,
          "Envío calculado correctamente.",
          "success",
        );
      } catch (error) {
        carrierResult.hidden = true;

        showMessage(carrierMessage, error.message);
      }
    });
  }

  // ====================================================
  // INICIALIZACIÓN
  // ====================================================

  initializeAddressForm();

  loadDeliveryOptions();
});
