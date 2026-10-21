# INFORME DE AUDITORIA DEL DASHBOARD ADMINISTRATIVO - SULPAA V2

Fecha: 2026-10-16 17:00:00

## 1. Arquitectura, rutas, servicios, repositorios, plantillas, CSS, JS y Chart.js

**Arquitectura:** Route→Service→Repository (Flask, monolito modular). Base única conexiones: app/config/database.py.

**Rutas (app/admin/routes.py):**
- GET /admin/dashboard -> dashboard() consume resumen_dashboard() y renderiza templates/admin/dashboard.html
- GET /admin/kpi/ -> indicadores() consume misma fuente resumen_dashboard() y renderiza templates/admin/kpi.html

**Servicios:** app/admin/services.py (resumen_dashboard, métricas), app/admin/caja/services.py (resumen_caja, serie_flujo_mensual)
**Repositorios:** app/admin/repositories.py (métricas KPI), app/admin/caja/repositories.py (serie_flujo_mensual, resumen_movimientos)
**Plantillas:** templates/admin/dashboard.html, templates/admin/kpi.html, templates/admin/components/sidebar.html
**CSS:** static/css/pages/admin.css (676 líneas)
**JS:** Inline en templates/admin/dashboard.html (después de chart.umd.min.js) - construye 2 gráficos
**Chart.js:** static/vendor/chart.umd.min.js (205419 bytes) - servido localmente

## 2. KPI existentes: cálculo correcto vs limitaciones

| KPI | Nombre | Fórmula (según código) | Valor actual (muestra) | Estado | Observaciones/Limitaciones |
|---|---|---|---|---|---|
| KPI-01 | Pedidos procesados correctamente | (pedidos COMPLETADO con entrega ENTREGADO y pago PAGADO) / (pedidos iniciados: estado EN_PREPARACION o COMPLETADO) * 100 | 50% (2/4) | no_cumple | Requiere fin extremo a extremo (entrega ENTREGADO + pago PAGADO). Solo considera pedidos en zona operativa. Correcto según definición, pero depende de coherencia entre tablas. |
| KPI-02 | Exactitud de inventario | verificaciones con coincidencia / total verificaciones físicas * 100 | 100% (1/1) | cumple | Usa datos de inventario/verificaciones. Limitado por volumen de verificaciones registradas. |
| KPI-03 | Acceso a información de producto | % con info completa | 100% (12/12) | cumple | Metrica basada en evidencia registrada. |
| KPI-04 | Disponibilidad de historial de pedidos | % pedidos con historial / total pedidos | 100% (12/12) | cumple | Basado en pedido_historial (comercio). |
| KPI-05 | Reportes gerenciales | solicitudes exitosas / total solicitudes reales * 100 | 75% (3/4) | no_cumple | Basado en operaciones.reportes_solicitudes (solo POST genera registro). Requiere solicitudes reales instrumentadas. |
| KPI-06 | Artículos favoritos del cliente | % con evidencia | 100% (7/7) | cumple | Correcto con datos existentes. |
| KPI-07 | Estados de pedido actualizados | pedidos cuyo estado coincide con último evento en pedido_historial / pedidos con historial * 100 | 100% (12/12) | cumple | Buena validación de consistencia entre estado actual e historial. |
| KPI-08 | Programación de entregas | programadas correctamente / total solicitudes | None | pendiente | Documentado como PENDIENTE - no existe entidad "solicitudes de programación" ni registro de rechazos en entregas. Evita sustituto silencioso. |
| KPI-09 | Encuesta de satisfacción | pedidos entregados con INVITACION_OK / pedidos entregados elegibles * 100 | 100% (2/2) | cumple | Usa DISTINCT por pedido. Satisfacción promedio separado (gerencial), no alimenta fórmula. |
| KPI-10 | Contenido educativo | % con evidencia | 100% (3/3) | cumple | Correcto con datos existentes. |

## 3. Pedidos completados, pagos confirmados e ingresos reales

**Hallazgos (datos reales):**
- Pedidos COMPLETADO: 2 (PED-20260910-33903F, PED-20261015-E32F52)
- Pagos PAGADO: 2, ambos asociados a esos pedidos con pagado_en registrado.
- Operativo.pedidos_completados = 2 (coincide con pedidos COMPLETADO que cumplen criterio extremo-a-extremo según KPI-01).
- Ingresos caja (resumen_caja/operativo.ingresos): 252.00 PEN, provenientes de movimientos caja con origen PAGO, estado ACTIVO (2 movimientos).

**Diferencia:**
- "Pedidos completados" (estado) no implica automáticamente ingreso contabilizado si no hay pago confirmado/movimiento de caja.
- Ingresos reales deben basarse en: pagos.estado=PAGADO con movimiento caja ACTIVO (origen PAGO) o en caja_movimientos tipo INGRESO estado ACTIVO. Evitar sumar totales de pedidos COMPLETADO sin validar pago.
- Caja usa pago_id único (UNI en caja_movimientos) - previene duplicados por pago.

**Recomendación:** Usar "ingresos reales" = SUM(caja_movimientos.monto) WHERE tipo=INGRESO AND estado=ACTIVO (filtrando origen PAGO si se quiere solo ventas). No duplicar con pedidos.total.

## 4. Relación entre movimientos de caja y pagos (evitar duplicados)

**Tablas (Operaciones):**
- pagos(id char(36), pedido_id, monto, estado, pagado_en, ...)
- caja_movimientos(id bigint autoinc, tipo enum(INGRESO,EGRESO), origen enum(PAGO,MANUAL), pago_id char(36) NULL UNIQUE, pedido_id char(36) NULL, monto decimal(12,2), estado enum(ACTIVO,ANULADO), fecha_movimiento datetime, ...)
- caja_categorias(id, codigo, tipo, estado)

**Relación:** movimiento de caja INGRESO con origen PAGO se vincula 1:1 con pago vía pago_id (UNIQUE). También referencia pedido_id.
**Prevención duplicados:**
- pagos_sin_movimiento_caja busca p.estado=PAGADO AND p.pagado_en NOT NULL AND m.id IS NULL (LEFT JOIN por pago_id) - identifica pagos aún sin ingreso de caja.
- serie_flujo_mensual suma solo m.estado=ACTIVO y agrupa por mes.
- resumen_movimientos filtra m.estado=ACTIVO.

**Reglas seguras para dashboard:**
1. Ingresos = SUM(m.monto) FROM caja_movimientos WHERE tipo=INGRESO AND estado=ACTIVO (y opcional origen=PAGO).
2. Nunca sumar montos de pagos PAGADO si ya existen movimientos caja para esos pagos.
3. Si se muestran "ventas cobradas", usar UNION lógico: solo lo que esté reflejado en caja ACTIVO con origen PAGO.
4. Egresos MANUAL/PAGO no aplica; usar tipo=EGRESO estado=ACTIVO.

## 5. Productos más vendidos: tablas, relaciones y cómo calcular por unidades e ingresos

**Tablas (Comercio):**
- pedidos(id, estado, total, ...)
- pedido_detalles(id, pedido_id, articulo_venta_id, nombre_articulo, cantidad, precio_unitario, subtotal_linea)
- pedido_composiciones(id, pedido_detalle_id, variante_id, nombre_variante, cantidad)

**Tablas (Comercio/Inventario):**
- variantes(id, producto_id, sabor_id, presentacion_id, sku, nombre_comercial, peso_gramos)
- productos(id, nombre, categoria_id, ...)
- sabores(id, nombre)
- presentaciones(id, nombre, tipo_unidad, cantidad)

**Relaciones clave:**
pedidos 1:N pedido_detalles (por pedido_id)
pedido_detalles 1:N pedido_composiciones (por pedido_detalle_id)
pedido_composiciones -> variantes (variante_id)
variantes -> productos/sabores/presentaciones

**Cálculo correcto (unidades vendidas):**
Unidades físicas vendidas = SUM(pd.cantidad * pc.cantidad)
Nota: pd.cantidad = cantidad de packs/artículos en detalle; pc.cantidad = unidades de variante por composición.

**Ingresos por variante:** SUM(pd.subtotal_linea) agrupado por variante (corresponde a línea de venta).

**Filtros recomendados para "ventas reales":**
Considerar pedidos con estado COMPLETADO. Para ingresos estrictamente "cobrados", cruzar con pagos.estado=PAGADO y/o existencia de movimiento caja ACTIVO origen PAGO. En datos actuales, pedidos COMPLETADO coinciden con pagos PAGADO.

**Permite agrupar por:** producto, sabor, presentacion, variante/SKU (dimensiones disponibles).

## 6. Ventas por sabor, presentación y producto

**Sí, posible.** Dimensiones via variantes -> productos/sabores/presentaciones.

**Ejemplos de agrupación válidos:**
- Por producto: GROUP BY p.id, p.nombre
- Por sabor: GROUP BY s.id, s.nombre (dentro de producto si aplica)
- Por presentación: GROUP BY pr.id, pr.nombre
- Por (producto, sabor): GROUP BY p.id,p.nombre,s.id,s.nombre
- Por (producto, sabor, presentación): GROUP BY p.id,p.nombre,s.id,s.nombre,pr.id,pr.nombre

**Métricas:** unidades_vendidas = SUM(pd.cantidad*pc.cantidad), ingresos = SUM(pd.subtotal_linea).
**Recomendación:** ofrecer selector de dimensión en dashboard (Producto/Sabor/Presentación/Variante) con mismo filtro de período y estado/pago.

## 7. Gráficos existentes: conservar/mejorar/reemplazar

**Actuales (templates/admin/dashboard.html):**
1. Flujo de caja mensual (bar) - usa graficos.flujo_caja desde caja.serie_flujo_mensual (últimos 6 meses, ingresos/egresos ACTIVO).
2. KPI-09 comparación (bar) - invitaciones OK vs pedidos entregados (COUNT DISTINCT).

**Evaluación:**
- Conservar: flujo de caja mensual (útil, datos reales). Mejorar: mostrar valores en S/, leyendas claras, tooltip con moneda, eje Y con separadores.
- Conservar: KPI-09 (contexto cumplimiento). Mejorar: etiquetas más descriptivas, colores coherentes con marca.
- Faltante crítico: "Top productos más vendidos" (unidades e ingresos). No existe en dashboard actual.
- Faltante útil: Ventas por día/semana (últimos 7-30 días), distribución por estado (torta/barra), entregas por tipo, top sabores/presentaciones.

**Recomendados a añadir:**
- Gráfico Top 5-10 productos por unidades vendidas (horizontal bar) - usa composición.
- Gráfico Top por ingresos (horizontal bar).
- Evolución de ventas diarias últimos 30 días (line/bar).

**Notas:** Chart.js ya disponible localmente. Mantener sin CDN.

## 8. Propuesta visual profesional y priorización (Alta/Media/Baja)

**Distribución propuesta:**
1. Cabecera: título + filtros globales (fecha desde/hasta, vendedor/tienda si aplica).
2. Tarjetas KPI funcionales (KPI-01..10) con código, valor %, estado (cumple/no_cumple/pendiente), numerador/denominador tooltip.
3. Tarjetas operativas: Pedidos iniciados/completados, Entregas, Stock bajo, Ingresos/Egresos/Flujo neto, Encuestas, Satisfacción promedio.
4. Gráficos fila 1: Flujo caja mensual + KPI-09 (conservar/mejorar)
5. Gráficos fila 2: Top productos por unidades + Top productos por ingresos (NUEVOS)
6. Tablas: Top 10 detallado (SKU, Producto, Sabor, Presentación, Unidades, Ingresos) + Ventas recientes
7. Sección analítica: selector dimensión (Producto/Sabor/Presentación) con gráfico dinámico.

**Priorización:**

| Mejora | Prioridad | Justificación |
|---|---|---|
| Añadir "Top productos más vendidos" (unidades + ingresos) con datos reales | ALTA | Solicitud directa; usa composición existente; alto valor gerencial |
| Unificar ingresos con caja_movimientos (evitar ambigüedad entre "total pedidos" vs "ingresos reales") | ALTA | Consistencia con flujo caja ya implementado |
| Mejorar tooltips/labels en gráficos existentes (Chart.js) | ALTA | Mejora UX sin riesgo |
| Añadir selector dimensión (sabor/presentación/producto) para ventas | MEDIA | Útil, requiere nuevo repo/service |
| Añadir evolución ventas diarias 30 días | MEDIA | Complementa flujo mensual |
| Mejoras CSS para tarjetas/gráficas responsivas | MEDIA | Visual profesional |
| Añadir filtros globales fecha (desde/hasta) al dashboard | BAJA | Ya existen en otros módulos; evaluar consistencia |
| Exportar CSV/PNG desde gráficos | BAJA | Nice-to-have

## 9. Plan de implementación por bloques (archivos, fórmulas, riesgos, pruebas)

### BLOQUE A: Top productos más vendidos (ALTA)
**Archivos:**
- app/admin/repositories.py: añadir obtener_top_productos_vendidos(desde,hasta,limit=10,dimension="variante")
- app/admin/services.py: exponer top_productos_vendidos() reutilizando repos
- app/admin/routes.py: pasar top_productos a dashboard vía resumen o nuevo dato
- templates/admin/dashboard.html: añadir 2 tarjetas/gráficos (unidades e ingresos) + tabla
- static/js/modules/admin_dashboard.js (opcional) o inline JS ampliado

**Fórmula:** unidades = SUM(pd.cantidad*pc.cantidad), ingresos = SUM(pd.subtotal_linea). Filtro: pe.estado="COMPLETADO" (y opcional join pagos si queremos solo cobrados).
**Riesgo:** JOIN con composiciones asume pc.variante_id existe (datos muestran que sí).
**Pruebas:** unittest con datos mockeados; verificar unidades correctas (pack 6 -> 6 unidades).

### BLOQUE B: Unificar ingresos reales con caja (ALTA)
**Archivos:** app/admin/services.py (operativo.ingresos), revisar uso en templates
**Cambio:** operativo.ingresos usar caja_movimientos tipo=INGRESO estado=ACTIVO (origen PAGO) - ya hecho parcialmente vía resumen_caja; documentar criterio.
**Riesgo:** bajo (ya existe lógica caja).
**Pruebas:** validar coherencia con movimientos existentes.

### BLOQUE C: Mejorar gráficos existentes (ALTA)
**Archivos:** templates/admin/dashboard.html (inline JS) + CSS
**Mejoras:** tooltips con formato moneda, colores, responsive, sin cambios en datos.
**Riesgo:** mínimo.
**Pruebas:** visual/regresión (no rompe tests).

### BLOQUE D: Selector dimensión + evolución diaria (MEDIA)
**Archivos:** repositories/services/routes/template/JS
**Riesgo:** requiere nuevas consultas parametrizadas.
**Pruebas:** unit tests para queries.

**Notas generales:**
- No modificar datos/esquemas/query. Mantener arquitectura Route→Service→Repository.
- No commit/push. Ejecutar tests focalizados y suite completa tras cambios.
- Chart.js local. Comentarios en español.
---
FIN DEL INFORME
