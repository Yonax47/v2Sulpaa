# INFORME FINAL — SULPAA V2 (MÓDULO ADMINISTRATIVO)

Fecha de elaboración: 2026-10-16
Autor: trabajo asistido en el repositorio local `C:\Users\Acer\Documents\v2Sulpaa`
Base de datos: MariaDB 10.4.32 (localhost:3306), 4 esquemas.

> Alcance y honestidad del informe
>
> - Todo lo aquí descrito corresponde a cambios y verificaciones efectivamente
>   ejecutados en esta máquina (revisión de código, consultas SQL de SOLO LECTURA,
>   render de rutas con `Flask.test_client` y ejecución de la suite `unittest`).
> - NO se modificaron datos, esquemas ni el archivo `query`.
> - NO se hizo commit ni push.
> - Ninguna fase se marca como completada solo porque su ruta devuelva HTTP 200.
> - Las 8 "fases" corresponden al plan de trabajo seguido en esta sesión. No existe
>   en el repositorio un archivo de requisitos con la lista numerada de fases; la
>   numeración se reconstruye del trabajo realmente hecho.

---

## 1. Estado de las ocho fases

| Fase | Descripción | Estado | Sustento real | Lo que falta / salvedad |
|---|---|---|---|---|
| 1 | Diagnóstico de BD y flujos (dashboard/gerencial) | **COMPLETADA** | Informe previo `INFORME_DASHBOARD_AUDITORIA.md` + verificación real de las 4 BD (tablas y conteos, ver §9). | Es solo diagnóstico; no cambia comportamiento. |
| 2 | Módulo admin **Usuarios y Roles** | **COMPLETADA** | `app/admin/usuarios/` + plantillas + `tests/test_admin_usuarios.py` (6). Se creó un usuario real y se comprobó en MySQL `usuarios`+`perfiles`+`usuario_roles` (persistencia real, §4). | Sin CSRF; no hay edición de datos personales (solo estado y roles); no hay reseteo de contraseña. |
| 3 | Módulo admin **Auditoría del sistema** (solo lectura) | **COMPLETADA** | `app/admin/auditoria/` + `tests/test_auditoria_admin.py` (4). GERENTE=200, ADMINISTRADOR=403, REPARTIDOR=403; se insertó un evento real y se listó/detalló. | Solo **usuarios** y **delivery** emiten eventos (no es auditoría global de todos los módulos). |
| 4 | **Configuración de Delivery** | **PARCIAL** | `app/admin/delivery/` + `tests/test_delivery_config.py` (7). Consulta, simulador (misma fórmula del checkout), validación y permisos verificados. | La **escritura** de la tarifa (`POST /admin/delivery/tarifa`) NO se verificó ejecutándola: hacerlo modificaría datos reales (prohibido). Solo están verificados validación y permisos. |
| 5 | Gráfico de **flujo de caja** en `/admin/caja/` | **COMPLETADA** | Plantilla + `page_js`; se detectó y **corrigió** un bug real en `serie_flujo_mensual` (§2) tras el cual la ruta devuelve datos reales y la serie aparece. | El render de la gráfica se apoya en Chart.js local; no hay prueba automática de navegador (solo de datos y HTML). |
| 6 | Gráficos de **encuestas** | **COMPLETADA** | `estadisticas_encuestas()` (función pura) + sección de gráficos + `page_js`; `tests/test_admin_analitica.py` cubre la agregación. HTML verificado con `chart-encuestas-estado`. | No hay prueba de JS/navegador; el promedio depende de respuestas reales (hoy 2 respondidas). |
| 7 | Corrección del **desbordamiento visual** del dashboard | **COMPLETADA (estructural)** | Los 5 canvas gerenciales y su sección se movieron dentro del bloque `content` y el `page_js` quedó solo con `<script>`. Prueba estática `test_canvas_gerenciales_dentro_del_contenido`. | No se midió el overflow con un navegador real; la verificación es de estructura HTML, no visual/pixel. |
| 8 | **Pruebas de integración** de lo nuevo | **PARCIAL** | Nuevas suites: `test_admin_usuarios`, `test_auditoria_admin`, `test_delivery_config`, `test_admin_analitica`, `test_dashboard_charts`. | Faltan: prueba de escritura de delivery, pruebas de render JS, CSRF, y cobertura de auditoría en módulos distintos a usuarios/delivery. |

---

## 2. Problemas encontrados y causas

1. **Bug real en `app/admin/caja/repositories.py::serie_flujo_mensual` (encontrado durante esta verificación).**
   - Causa: el SQL usa comodines literales `%Y-%m` de `DATE_FORMAT` junto a un parámetro ligado (`INTERVAL %s MONTH`). PyMySQL aplica formateo `%` cuando hay argumentos, por lo que `%Y` produce `ValueError: unsupported format character 'Y'`.
   - Efecto: el servicio `app/admin/caja/services.py::serie_flujo_mensual` envuelve la llamada en `try/except` y **silenciaba** el error devolviendo `[]`. Resultado: el gráfico de caja (Fase 5) y el **gráfico preexistente** de flujo de caja del dashboard (`graficos.flujo_caja`) nunca mostraban datos.
   - Corrección aplicada: escapar los `%` literales como `%%`. Verificado: la función ahora devuelve `[{'periodo':'2026-09','ingresos':126.00,...},{'periodo':'2026-10',...}]` y el canvas `chart-caja-flujo` aparece en el HTML. Se agregó prueba de regresión.
2. **`role_required` / `admin_required` definidos dos veces** en `app/shared/decorators.py`.
   - La **primera** definición de `role_required` (línea 121) está rota (`return funcion(...)` mal ubicado / no devuelve bien el decorador). La **segunda** (línea 215) es la correcta y es la que Python usa.
   - Causa: código duplicado. **No** es un bug funcional hoy, pero es deuda técnica y riesgo de edición futura.
3. **Columna `detalle` inexistente** en `auditoria_operaciones`.
   - Causa: el esquema real no tiene `detalle`; el detalle se guarda **dentro** del JSON `datos_nuevos`. Las consultas/pruebas/limpieza deben usar `datos_nuevos LIKE %s` (así se hizo en `test_admin_usuarios` y `test_auditoria_admin`).
4. **FK `usuario_roles.asignado_por_usuario_id` → `usuarios.id`.**
   - Causa: algunas pruebas usaban el **string de login** (`i2512609`) como actor; la FK exige un `usuarios.id` real. Se usó el UUID real del gerente.
5. **Faltantes detectados y resueltos durante el desarrollo:** `listar_roles()` en `app/admin/usuarios/repositories.py` y `obtener_top_productos_vendidos_cobrados()` en `app/admin/repositories.py`.
6. **Deuda de limpieza (no funcional):**
   - Comentarios residuales en `app/admin/repositories.py` (`# DASHGER` y cabecera duplicada "MÉTRICAS COMERCIALES...").
   - `f"""` innecesario en la consulta de `serie_flujo_mensual` (sin placeholders de f-string).
   - Archivos sueltos sin trackear: `add_fix.py` (script de apoyo) y `test.txt`.
7. **Sin protección CSRF.** `app/identidad/routes.py:396` reconoce que aún no se incorpora; los formularios POST nuevos (crear usuario, cambiar estado, asignar roles, guardar tarifa) no llevan token CSRF.

---

## 3. Archivos modificados y funciones implementadas

### 3.1 Nuevos módulos administrativos (untracked)

**`app/admin/usuarios/`**
- `repositories.py`: `listar_roles`, `listar_usuarios`, `contar_usuarios`, `obtener_usuario`, `correo_existe`, `dni_existe`, `crear_usuario_con_roles` (transacción única: `usuarios`+`perfiles`+`usuario_roles`), `actualizar_estado_usuario`, `reemplazar_roles` (baja lógica `INACTIVO` y reactivación).
- `services.py`: `listar_roles_admin`, `listar_usuarios_admin`, `obtener_usuario_admin`, `crear_usuario_admin` (validaciones + bcrypt + auditoría), `cambiar_estado_usuario_admin`, `asignar_roles_usuario_admin`.
- `routes.py`: `listado`, `nuevo`, `detalle`, `cambiar_estado`, `asignar_roles`.
- `__init__.py`: expone `admin_usuarios_bp`.

**`app/admin/auditoria/`**
- `repositories.py`: `insertar_evento`, `listar_eventos`, `contar_eventos`, `obtener_evento`, `listar_modulos`, `listar_acciones`; `_serializar`/`_limpiar` filtran claves sensibles (password, token, secret, cookie…).
- `services.py`: `registrar_evento` (no rompe la operación original), `listar_eventos_admin`, `obtener_evento_admin`, `opciones_filtros`, `_enriquecer`.
- `routes.py`: `listado`, `detalle`. `__init__.py`: expone el blueprint.

**`app/admin/delivery/`**
- `repositories.py`: `obtener_tarifa_delivery_activa`, `listar_tarifas_delivery`, `actualizar_tarifa_delivery`, `listar_transportistas`, `listar_tarifarios_transportista`, `listar_reglas_tarifa`, `listar_coberturas_activas`.
- `services.py`: `obtener_configuracion_delivery`, `validar_datos_tarifa`, `actualizar_tarifa_delivery_admin`, `simular_cotizacion`, `_a_decimal`.
- `routes.py`: `configuracion`, `actualizar_tarifa`, `simular`. `__init__.py`: expone el blueprint.

**Plantillas nuevas:** `templates/admin/usuarios/{lista,formulario}.html`,
`templates/admin/auditoria/{lista,detalle}.html`,
`templates/admin/delivery/configuracion.html`.

**Pruebas nuevas:** `tests/test_admin_usuarios.py`, `tests/test_auditoria_admin.py`,
`tests/test_delivery_config.py`, `tests/test_admin_analitica.py`, `tests/test_dashboard_charts.py`.

### 3.2 Archivos modificados (tracked)

- **`app/__init__.py`**: import/registro de `admin_usuarios_bp`, `admin_auditoria_bp`, `admin_delivery_bp`; global Jinja `imagen_producto` (fuera del alcance admin).
- **`app/admin/routes.py`**: importa `obtener_resumen_gerencial`; `dashboard()` la llama en `try/except` y pasa `gerencial=` a la plantilla.
- **`app/admin/services.py`**: nueva `obtener_resumen_gerencial(desde, hasta)` (agrega ventas cobradas, top productos, top cobrados, ingresos por producto, evolución y ventas por día, pedidos/entregas por estado, resumen de caja; cada bloque con `try/except`).
- **`app/admin/repositories.py`**: +9 funciones: `obtener_ventas_cobradas`, `obtener_top_productos_vendidos`, `obtener_top_productos_vendidos_cobrados`, `obtener_caja_movimientos_resumen`, `obtener_evolucion_ventas_diarias`, `obtener_entregas_por_estado`, `obtener_ventas_cobradas_por_dia`, `obtener_ingresos_por_producto_cobrado`, `obtener_pedidos_por_estado_agrupado`.
- **`app/admin/caja/routes.py`**: `listado()` importa y pasa `serie_flujo=serie_flujo_mensual()`.
- **`app/admin/caja/repositories.py`**: **corrección del bug** de `serie_flujo_mensual` (`%%`).
- **`app/admin/encuestas/services.py`**: nueva `estadisticas_encuestas(encuestas)` (conteo por estado, promedio de `calificacion_general`, nº de `recomendaria`).
- **`app/admin/encuestas/routes.py`**: importa y pasa `estadisticas`.
- **`app/operaciones/services.py`**: extracción de la **fórmula pura** `calcular_costo_delivery_local(tarifa, distancia_km, peso_kg, subtotal)` y refactor de `cotizar_delivery_local(...)` para reutilizarla (una sola fuente de verdad; checkout y admin comparten fórmula).
- **Templates**: `templates/admin/dashboard.html` (sección gerencial + 5 canvas dentro de `content`; `page_js` solo scripts), `templates/admin/caja/lista.html` (sección flujo + `page_js`), `templates/admin/encuestas/lista.html` (sección + `page_js`), `templates/admin/components/sidebar.html` (enlaces "Configuración de Delivery", "Usuarios y roles" y "Auditoría").
- **`tests/test_integracion_lecturas.py`**: pruebas de carrito lateral/favoritos/ficha (fuera del alcance estrictamente admin).

> Nota de alcance: el árbol de trabajo contiene además cambios sin commitear en tienda/checkout/favoritos/carrito/imágenes (p. ej. `app/comercio/*`, `static/js/modules/*`, `templates/cliente/*`, `templates/components/*`). NO forman parte de este informe de administración y no se analizan aquí.

---

## 4. Estado real del registro de usuarios y persistencia de roles (MySQL)

- **Rutas:** `GET /admin/usuarios/` (listado paginado con filtros texto/estado/rol),
  `GET|POST /admin/usuarios/nuevo`, `GET /admin/usuarios/<uuid>`,
  `POST /admin/usuarios/<id>/estado`, `POST /admin/usuarios/<id>/roles`.
- **Esquema real usado (`v2sulpaa_identidad_db`):** `usuarios` (id char(36), correo, password_hash,
  estado, correo_verificado), `perfiles` (datos personales, `usuario_id`), `roles` (catálogo),
  `usuario_roles` (N:M con `estado`, `asignado_por_usuario_id`).
- **Persistencia:** `crear_usuario_con_roles` inserta **cuenta + perfil + roles en una sola
  transacción**; si algo falla, hace `rollback` (nunca se guarda "a medias"). La contraseña se
  guarda con **bcrypt**. `reemplazar_roles` desactiva (`INACTIVO`) los vínculos previos y
  reactiva/crea los solicitados (conserva histórico; no borra).
- **Verificación real (no solo HTTP 200):** `tests/test_admin_usuarios.py::test_crear_usuario_guarda_de_verdad`
  creó un usuario real y comprobó por SQL: 1 fila en `usuarios` (estado `ACTIVO`), 1 en `perfiles`,
  y `INVENTARIO` en `usuario_roles`; `test_creacion_deja_evento_de_auditoria` comprobó el evento
  en `auditoria_operaciones`; `test_correo_duplicado_no_crea_nada` comprobó que no se duplica.
  Los datos de prueba se eliminan en `tearDown`.
- **Estado real de la BD ahora:** `usuarios`=5, `perfiles`=5, `roles`=5, `usuario_roles`=2.
  Asignaciones existentes: `i2512609@continental.edu.pe → GERENTE` y
  `televisionchupaca04@gmail.com → REPARTIDOR`. **3 usuarios no tienen rol** (dato preexistente,
  no generado por este trabajo). No quedó basura de pruebas.
- **Acceso:** solo `GERENTE`/`ADMINISTRADOR`. `GERENTE` es el único que puede conceder/retirar el
  rol `GERENTE` o desactivar cuentas ajenas; un usuario no puede desactivarse ni quitarse su
  propio `GERENTE`.
- **Inicio de sesión de las cuentas creadas:** `app/identidad/services.py::autenticar_usuario` exige
  `estado='ACTIVO'` y valida bcrypt; **no** exige `correo_verificado`. Los roles se cargan a la
  sesión con `obtener_roles_usuario`. (No se ejecutó una prueba de login end-to-end de un usuario
  recién creado; ver §11.)

---

## 4-5. Estado del módulo de auditoría

- **Dónde se almacena:** tabla **`auditoria_operaciones`** en `v2sulpaa_operaciones_db` (append-only).
  Columnas: `id`, `usuario_id`, `modulo`, `entidad`, `entidad_id`, `accion`, `datos_anteriores`,
  `datos_nuevos`, `direccion_ip`, `creado_en`. **No existe columna `detalle`**: el detalle,
  `resultado`, `tipo_operacion` y `actor_rol` se guardan dentro del JSON `datos_nuevos`.
- **Qué acciones registra (hoy):**
  - `modulo='USUARIOS'`: `CREAR_USUARIO`, `CAMBIAR_ESTADO`, `ASIGNAR_ROLES` (con `resultado`
    `EXITO`/`EXITO`/error según el caso).
  - `modulo='DELIVERY'`: `ACTUALIZAR_TARIFA` (con `datos_anteriores` y `datos_nuevos`).
  - Los datos sensibles (`password`, `token`, `secret`, etc.) se filtran antes de serializar.
  - **Límite:** los módulos de pedidos, caja, inventario, contenido, etc. **no** emiten eventos
    aquí; solo usuarios y delivery lo hacen.
- **Quién puede consultarla:** **solo `GERENTE`**. Doble control: `@role_required("GERENTE")` en las
  rutas y `ROLES_AUDITORIA=("GERENTE",)` en el servicio (`_permitido`). Verificado:
  `GERENTE=200`, `ADMINISTRADOR=403`, `REPARTIDOR=403`; y el servicio lanza `PermissionError`
  para no-gerentes.
- **Rutas:** `GET /admin/auditoria/` (paginado, filtros por usuario/módulo/acción/entidad/fecha) y
  `GET /admin/auditoria/<id>` (detalle). Sin rutas de edición/borrado.
- **Verificación real:** `test_auditoria_admin` registró un evento real, lo contó por SQL y lo
  listó; el evento se elimina en `tearDown`. En la BD quedan **2** eventos reales.

---

## 6. Estado de la "configuración de combustible" y de Delivery

> Aclaración factual: **NO existe** una variable ni tabla de "combustible" en el sistema. No se
> encontró `combustible`/`fuel` en el código. El costo de transporte por distancia se expresa como
> **`precio_km_adicional`** (recargo por km), que es lo más cercano a un recargo de combustible.
> Lo que sí existe son **recargos de tarifarios de transportista** (`recargo_hora_pico`,
> `recargo_feriado`, `recargo_fijo`) en las tablas de transportista, **solo lectura** y que
> **NO** se suman automáticamente (documentado en el propio código y en la plantilla).

- **Variables reales y editables (tabla `tarifas_delivery`, operaciones; 8 campos):**
  `tarifa_base`, `km_incluidos`, `precio_km_adicional`, `peso_incluido_kg`, `precio_kg_adicional`,
  `distancia_maxima_km`, `peso_maximo_kg`, `monto_envio_gratis` (más `nombre`).
- **Fórmula única** (`app/operaciones/services.py::calcular_costo_delivery_local`), reutilizada por el
  checkout y por el simulador admin:
  `costo = tarifa_base + (distancia − km_incluidos)*precio_km_adicional + (peso - peso_incluido_kg)*precio_kg_adicional`,
  con reglas: fuera de `distancia_maxima_km` → no cotizable; sobre `peso_maximo_kg` → no se puede
  cotizar; `subtotal >= monto_envio_gratis` → costo 0.
- **Persistencia:** `tarifas_delivery` (operaciones). Tarifa ACTIVA real hoy:
  `id=57141018-a0d6-11f1-b084-088fc316d95e`, `tarifa_base=6.00`, `km_incluidos=4.50`,
  `precio_km_adicional=1.40`, `peso_incluido_kg=5.00`, `precio_kg_adicional=1.00`,
  `distancia_maxima_km=25.00`, `peso_maximo_kg=12.00`, `monto_envio_gratis=NULL`, `estado=ACTIVA`,
  `vigente_hasta=NULL`.
- **Permisos:** **GERENTE y ADMINISTRADOR** consultan (`GET /admin/delivery/`); **solo GERENTE**
  edita (`POST /admin/delivery/tarifa`). El simulador (`POST /admin/delivery/simular`) exige
  GERENTE/ADMINISTRADOR.
- **Verificación real:** `test_delivery_config` confirmó permisos (REPARTIDOR=403;
  GERENTE/ADMINISTRADOR=200), que el simulador usa **la misma** `calcular_costo_delivery_local`
  del checkout, y la validación (rechaza negativos, acepta válidos). Simulación de muestra
  (6 km, 3 kg, S/50) coincide con la fórmula.
- **No verificado:** el `UPDATE` real de la tarifa (habría modificado datos reales). La ruta y la
  transacción están implementadas, pero no se ejecutaron contra MySQL.

---

## 7. Gráficos de caja, encuestas y dashboard

- **Dashboard** (`templates/admin/dashboard.html`, Chart.js local `static/vendor/chart.umd.min.js`):
  - Operativos (preexistentes): `chart-flujo-caja` (serie mensual), `chart-kpi09` (invitaciones vs entregados).
  - Gerenciales (nuevos, datos de `obtener_resumen_gerencial`): `chart-top-cobrados`
    (Top 10 cobrados), `chart-ingresos-producto` (ingresos por producto cobrado),
    `chart-evol-ventas` (ventas cobradas por día), `chart-flujo-caja-2` (flujo del período),
    `chart-estados-pedidos` (pedidos por estado). Cada gráfico tiene estado vacío explícito
    ("Sin ventas cobradas todavía", etc.) cuando no hay datos: **no se inventan datos**.
- **Caja (`/admin/caja/`):** `chart-caja-flujo` (barras Ingresos vs Egresos por mes) alimentado por
  `serie_flujo_mensual()` (movimientos `ACTIVO`, últimos 6 meses). *Tras la corrección del bug de
  §2, la serie devuelve datos reales (sep-2026: S/ 126.00; oct-2026: S/ 126.00).*
- **Encuestas (`/admin/encuestas/`):** `chart-encuestas-estado` (dona por estado, calculada sobre la
  lista filtrada) y `chart-encuestas-satisfaccion` (barra del promedio de `calificacion_general`,
  escala 0–5), más tarjetas de "Respuestas recibidas" y "Recomendarían".

---

## 7-8. Corrección del desbordamiento visual del dashboard

- **Problema:** la sección "Resumen Gerencial" y sus 5 `<canvas>` estaban **dentro del bloque
  `page_js`**, mezclados con el JavaScript (incluso con un `<script>` mal anidado), lo que producía
  contenido renderizado fuera del flujo normal y desbordaba el pie del dashboard.
- **Corrección:** se movieron el `<section>` y los 5 `<canvas>` al bloque `content` (antes del
  `<footer class="admin-data-note">`) y el bloque `page_js` se dejó **solo con scripts**
  (`<script src=...>` + un `<script>` IIFE con guardas `if (!window.Chart) return;`).
- **Verificación:** prueba estática `test_canvas_gerenciales_dentro_del_contenido` (los 5 ids de
  canvas aparecen antes de `{% block page_js %}`) y render `GET /admin/dashboard` = 200.
  La verificación es **estructural**, no una medición de pixel/overflow en navegador.

---

## 9. Tablas y conexiones verificadas en las cuatro bases de datos

Conexión única: `app/config/database.py` (`conexion_identidad/comercio/inventario/operaciones`,
`DictCursor`, `autocommit=False`). Verificación de SOLO LECTURA (MariaDB 10.4.32):

**`v2sulpaa_identidad_db` (12 tablas)** — relevantes verificadas con filas:
`usuarios`=5, `perfiles`=5, `roles`=5, `usuario_roles`=2. (También: `direcciones`, `distritos`,
`departamentos`, `provincias`, `datos_facturacion`, `partners`, `sesiones`, `auditoria_accesos`.)

**`v2sulpaa_comercio_db` (36 tablas)** — verificadas: `pedidos`=12, `pedido_detalles`=15,
`pedido_composiciones`=15, `variantes`=60, `productos`=1, `sabores`=12, `presentaciones`=5.
(Usadas por las métricas: `pedidos`, `pedido_detalles`, `pedido_composiciones`, `articulos_venta`,
`variantes`→`productos`/`sabores`/`presentaciones`.)

**`v2sulpaa_inventario_db` (9 tablas)** — `movimientos_inventario`=14 verificado. **Corrección de
suposición:** NO existen `stock` ni `verificaciones_inventario`; las tablas reales son
`existencias`, `lotes`, `movimiento_lotes`, `verificaciones_fisicas`, `reservas`, `reserva_detalles`,
`almacenes`, `motivos_movimiento`.

**`v2sulpaa_operaciones_db` (34 tablas)** — verificadas: `auditoria_operaciones`=2,
`tarifas_delivery`=1, `transportistas`=2, `tarifarios_transportista`=2,
`reglas_tarifa_transportista`=3, `rangos_tarifa_transportista`=11, `coberturas_transportista`=3,
`servicios_transportista`=3, `encuestas`=2, `encuesta_respuestas`=2, `caja_movimientos`=2
(2 ingresos `ACTIVO` de S/126.00, 2026-09-23 y 2026-10-15), `pagos`=11. Otras relevantes:
`entregas`, `entregas_delivery`, `entregas_recojo`, `cotizaciones_delivery`, `delivery_destinos`,
`repartidores`, `encuesta_eventos`, `caja_categorias`, `reportes_solicitudes`, `comprobantes`,
`metodos_pago`, `pago_historial`, `reembolsos`, etc.

---

## 10. Pruebas realizadas (clasificación) y resultado de la suite

Comando: `& ".\venv\Scripts\python.exe" -m unittest discover -s tests`.

**Resultado real: `Ran 273 tests` → `OK (skipped=1)`.**
(La suite estaba en 272 al momento del pedido; pasó a **273** porque agregué **1 prueba de
regresión** del bug de `serie_flujo_mensual` — §2. La cifra 272, por tanto, ya no aplica.)

**Omitida (1):** `test_bloque2_integracion.FlujoEntregaIntegracionTest.test_flujo_completo_delivery_se_revierte`
— `skipped 'No existe una entrega DELIVERY_LOCAL no entregada'` (dato de prueba inexistente).

### 10.1 Unitarias (sin base de datos)
- `test_admin_analitica.py::EstadisticasEncuestasTest` (2): agregación pura de encuestas.
- `test_admin_analitica.py::DashboardLayoutTest` (1): comprobación estática del template.
- `test_delivery_config.py` (2 de 7): `validar_datos_tarifa` (rechaza negativos / acepta válidos).

### 10.2 Integración (HTTP y/o servicios leyendo BD real, sin escribir)
- `test_admin_usuarios.py` (6): control de acceso, renders, **y persistencia real** (ver 10.3).
- `test_auditoria_admin.py` (4): permisos, registro real de evento, listado.
- `test_delivery_config.py` (5 de 7): acceso, render, simulador con la fórmula real, fuera de
  cobertura, edición restringida a gerente (rechazo).
- `test_admin_analitica.py::CajaFlujoSerieTest` (1): regresión de `serie_flujo_mensual`.
- `test_dashboard_charts.py` (2): ids de canvas en HTML + `obtener_resumen_gerencial()` con claves.
- (Suites preexistentes/ajenas al alcance admin: `test_admin_pedidos` 9, `test_bloque2_entregas` 26,
  `test_bloque2_integracion` 9, `test_bloque2_operaciones` 13, `test_bloque3` 43, `test_bloque4` 66,
  `test_carrito_favoritos_contract` 25, `test_checkout_contract` 20, `test_etapa3_coberturas` 14,
  `test_imagenes_producto` 12, `test_integracion_lecturas` 11, `test_pedido_states` 2.)

### 10.3 Persistencia real (escriben y limpian en MySQL)
- `test_admin_usuarios.py` (6): crea usuario+perfil+roles y **verifica por SQL**; prueba el no-duplicado;
  verifica el evento de auditoría; `tearDown` elimina lo creado. (Aunque verifican HTTP también,
  su valor distintivo es la persistencia real.)
- `test_auditoria_admin.py` (4): inserta un evento real en `auditoria_operaciones` y lo elimina.

### 10.4 Funcionalidad NO cubierta por pruebas (explícito)
- **JS/navegador:** ninguna prueba verifica el render real de Chart.js (colores, tooltips, overflow).
- **Escritura de delivery:** `POST /admin/delivery/tarifa` no se ejecutó (modificaría datos reales);
  sin prueba de persistencia del cambio de tarifa.
- **Login end-to-end de un usuario creado** (autenticación real con la contraseña creada).
- **CSRF:** no existe prueba (ni control) de token en los POST nuevos.
- **Auditoría de otros módulos** (pedidos, caja, inventario): no implementada ni probada.
- **Gráfico de encuestas/caja en navegador:** solo se validan datos/HTML, no el JS.
- **Casos borde de permisos** de usuarios (p. ej. auto-desactivación, auto-retiro de GERENTE) están
  implementados pero **no** tienen prueba dedicada.
- **Rendimiento/paginación** en volúmenes altos.

---

## 11. Problemas pendientes, limitaciones y cambios que requieren autorización

**Requieren autorización o decisión previa (no ejecutados):**
1. **Probar la escritura de la tarifa de delivery** (`POST /admin/delivery/tarifa`) contra la BD real:
   modificaría datos reales → requiere autorización explícita o un entorno/stub.
2. **Ampliar la auditoría a otros módulos** (pedidos, caja, inventario, etc.): hoy solo usuarios y
   delivery emiten eventos. Instrumentar el resto cambia el comportamiento de otros módulos.
3. **Incorporar protección CSRF** en los formularios POST administrativos (cambio transversal de
   seguridad; hoy reconocido como pendiente en `app/identidad/routes.py`).
4. **Asignar roles a los 3 usuarios que no tienen ninguno** (estado de datos; decide el negocio).

**Deuda técnica / limpieza (cambios de código menores, no aplicados):**
5. Eliminar la **primera definición duplicada** de `role_required`/`admin_required` en
   `app/shared/decorators.py` (código muerto).
6. Quitar comentarios residuales (`# DASHGER`, cabecera duplicada) en `app/admin/repositories.py` y
   el `f"""` innecesario en `serie_flujo_mensual`.
7. Borrar archivos sueltos sin trackear `add_fix.py` y `test.txt`.

**Limitaciones conocidas del trabajo entregado:**
8. No hay pruebas de navegador (JS/Chart.js); las gráficas se validan por datos + HTML.
9. No hay prueba end-to-end de login de un usuario recién creado (aunque la lógica lo permite:
   login no exige `correo_verificado`).
10. El cambio de roles en `usuario_roles` es **lógico** (estado `INACTIVO`), no borrado físico:
    correcto para histórico, pero deja filas.
11. La suite depende de la BD local (muchas pruebas de integración leen/escriben MariaDB); no hay
    mocks ni base efímera, por lo que el resultado depende del estado de los datos.
12. No hay linter/typecheck configurado (solo `unittest`); `requirements.txt` no incluye
    herramientas de calidad.
13. El árbol de trabajo contiene cambios **fuera del alcance admin** (tienda/checkout/favoritos/
    carrito/imágenes) sin commitear; no fueron evaluados aquí.

---

## Resumen ejecutivo (para producción/exposición)

**Qué quedó sólido:** módulos admin de Usuarios/Roles, Auditoría (solo GERENTE) y Configuración de
Delivery funcionan con persistencia real sobre las tablas existentes; la fórmula de delivery es
única (checkout = simulador admin); gráficos de caja y encuestas construidos sobre datos reales; se
corrigió un bug real que dejaba sin datos los gráficos de flujo de caja; el desborde del dashboard
quedó resuelto a nivel estructural. Suite: **273 OK, 1 omitida**.

**Qué falta corregir antes de producción/exposición:**
- **CSRF** en formularios POST administrativos (seguridad).
- **Verificar la escritura de la tarifa de delivery** (hoy no probada; requiere autorización por
  ser dato real).
- **Ampliar la auditoría** más allá de usuarios/delivery (decisión de alcance).
- **Pruebas de navegador** para Chart.js y una **prueba de login** de usuario recién creado.
- **Limpieza**: código muerto en `decorators.py`, comentarios residuales y archivos sueltos.
- Decidir el estado de los **3 usuarios sin rol**.
