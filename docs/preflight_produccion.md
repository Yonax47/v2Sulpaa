# Preflight local de producción — Fases 4.1–4.5

## Estado auditado

Base: rama `serna`, HEAD `1f2d81a350a6ed2de65746866ef87bdb33982369`;
`main` permanece en `a3195abf7d729d7a336e7d9256531eb8a842f5d4`.
Cambios de este preflight y su cierre exclusivamente locales. No se conectó a
Alwaysdata, no se creó TEST, no se consumió APIsPERU/Resend ni se aplicó SQL.

## Auditoría de migraciones y código

| Migración | Dependencia / condición | Resultado estático |
|---|---|---|
| 003 | `perfiles.dni`, sin duplicados, vacíos ni formato inválido | `UNIQUE` admite varios NULL; no repetir si el índice ya existe. Validar nombre, columnas completas y `SUB_PART IS NULL`. |
| 004 | `roles`, `usuario_roles`; CLIENTE único y ACTIVO | No reactiva inactivos ni migra vínculos históricos. `NOT EXISTS` no sustituye exclusión del operador: ejecutar en ventana controlada. |
| 005 | Identidad, InnoDB | Consumidor terminado, apagado por defecto. PK `(servicio, operacion, clave_hash)`, HMAC BINARY(32), contador SMALLINT, fechas DATETIME(6). |
| 006 | `usuarios.id`, `correo_verificado`, tablas base | Columna histórica DEFAULT 0; tokens con FK **local**, outbox con clave única y JSON_VALID, límites compartidos HMAC. |

Orden operativo: **003 → 004 → 005 → 006**. No hay dependencia SQL directa entre
005 y 006; ambas son necesarias para activar sus consumidores respectivos.
003 protege la carrera de registro por DNI y 004 habilita el rol del nuevo alta.
Login/sesiones/altas nuevos consultan la columna de 006 incluso con correo
desactivado: **no desplegar el código sin 006**. PDF no agrega estructura.

Las sentencias propuestas (`ADD COLUMN IF NOT EXISTS`, `DATETIME(6)`, ENUM,
CHECK, `JSON_VALID`, upsert y `FOR UPDATE SKIP LOCKED`) son compatibles con
MariaDB 11.4/InnoDB a nivel de diseño. No equivalen a una prueba real. Validar:

- El tipo, longitud y collation de `usuarios.id` deben ser compatibles con
  `tokens_verificacion.usuario_id CHAR(36) COLLATE utf8mb4_unicode_ci`. Si no
  coinciden, detener aplicación de 006; preparar una adaptación revisada, no
  convertir identificadores reales automáticamente.
- `CREATE TABLE IF NOT EXISTS` no comprueba una estructura preexistente.
  Comparar `SHOW CREATE TABLE`, columnas, PK, índices y restricciones.
- CHECK de vencimiento compara el reloj UTC del proceso con `NOW(6)` de BD:
  exigir sincronización horaria y sesión BD UTC. El contador usa reloj de BD.
- Todas las tablas de checkout deben ser InnoDB. Una conexión de
  `UnidadTrabajo` usa `select_db` y un commit; solo es atómica si todos los
  esquemas están en el mismo servidor y el usuario tiene permisos en los cuatro.
- Las migraciones no se ejecutan desde arranque, rutas ni worker. DDL de
  MariaDB puede realizar commit implícito: una migración no se revierte con un
  simple `ROLLBACK`.

## Rate limit compartido de APIsPERU

Ubicaciones:

- `app/config/apisperu.py`: configuración y guardas de activación.
- `app/identidad/apisperu_rate_limit.py`: transacción persistente.
- `app/identidad/apisperu.py`: protección justo antes de cada HTTP DNI/RUC.

La PK serializa por **IP canónica + operación**, compartida entre registro,
consulta previa y facturación. DNI y RUC tienen presupuestos independientes.
No incluye documento, correo, UUID de usuario, token ni respuestas del proveedor.
IP solo como HMAC-SHA256 con secreto dedicado; no se almacena en claro.
Se utiliza `remote_addr`, nunca X-Forwarded-For directamente. En production y
staging se exige proxy validado y saltos > 0. Asegurar que el contenedor no pueda
recibir tráfico que evite el proxy configurado.

Algoritmo: conexión **independiente**, begin, upsert sin cambio, SELECT FOR
UPDATE, reloj de BD después del bloqueo, reinicio de ventana si venció,
incremento/commit; cierre físico en finally. Solo después puede hacerse HTTP.
Un error SQL/commit/timeout/deadlock provoca rechazo genérico; **sin fallback al
contador local** cuando el compartido está habilitado. Un fallo de red del
proveedor consume el intento ya confirmado, evitando reintentos ilimitados.
No hay reintentos SQL automáticos. Los limitadores locales anteriores se
conservan como protección adicional, no como garantía distribuida.

| Variable | Inicial / significado |
|---|---|
| `APISPERU_RATE_LIMIT_ENABLED` | `0`; solicitar activación solo después de TEST y aprobación |
| `APISPERU_RATE_LIMIT_MIGRATION_APPROVED` | `0`; poner `1` únicamente después de aplicar y verificar 005 |
| `APISPERU_RATE_LIMIT_KEY` | Secreto dedicado aleatorio >=32 caracteres, mismo en todos los workers |
| `APISPERU_RATE_LIMIT_MAX_DNI` | `5` por IP y ventana |
| `APISPERU_RATE_LIMIT_MAX_RUC` | `5` por IP y ventana |
| `APISPERU_RATE_LIMIT_WINDOW_SECONDS` | `600`; rango permitido 30–86400 |

Activar sin aprobación o sin clave válida impide el arranque, sin intentar SQL.
La aprobación es una confirmación operativa, no una detección automática del
esquema. Si alguien la declara incorrectamente, las consultas fallan cerradas.
En un contexto Flask habilitado sin petición tampoco se consulta al proveedor.
Consumidores nuevos deben usar este cliente dentro del contexto de aplicación;
no crear scripts que llamen HTTP por fuera del adaptador.

429 para límite y 503 para contador no disponible en endpoints de verificación
y guardado de facturación; el checkout conserva su contrato de error existente.
Registro con formulario muestra mensaje genérico. La cuenta no se crea si no
puede verificarse el DNI. No se expone SQL ni la excepción.

Retención propuesta: limpiar ventanas >2 días con tarea explícitamente
autorizada, nunca desde arranque ni en este preflight. La ventana máxima es un
día; no borrar filas activas. Rotar la clave reinicia de facto presupuestos:
coordinar el cambio en todos los workers y nunca hacerlo durante un abuso.
El alcance por IP comparte cuota entre usuarios tras NAT; revisar métricas antes
de aumentar límites. No constituye una cuota contractual global de APIsPERU.

## Hallazgos que impiden afirmar preparación total para producción

1. Faltan pruebas reales MariaDB de migraciones, locks, FK, DDL y rollback.
2. Sin conexión al servidor no se conoce el estado de DNI, CLIENTE, InnoDB,
   collations, UTC, permisos o cupos reales: deben verificarse con autorización.
3. **Resuelto localmente:** checkout ejecuta `preparar_facturacion_checkout`
   antes de abrir UnidadTrabajo. Su resultado es un objeto interno inmutable,
   asociado al usuario, nunca un valor aceptado del navegador/sesión. Después
   `guardar_facturacion_preparada` escribe sin HTTP en la misma conexión del
   pedido/pago/inventario/entrega/outbox. Se liberan lecturas cacheadas previas
   y la lectura de perfil usa conexión independiente con cierre real. Un fallo
   del proveedor no abre UnidadTrabajo ni realiza escrituras. Faltan las pruebas
   reales de rollback multiesquema y concurrencia en TEST.
4. `DB_MAX_CONEXIONES_CACHE` no es un pool global ni un límite duro: las
   conexiones independientes y fallback también cuentan. Medir web + cron +
   contador antes de autorizar múltiples workers.
5. Resend/dominio/DNS/Cron y prueba autorizada de entrega siguen pendientes.

## Consultas listas para revisión

`docs/sql/preflight_003_006_solo_lectura.sql` incluye únicamente SELECT/SHOW:
conteos de problemas de DNI sin revelar documentos, índices, rol CLIENTE,
columnas, constraints/FK, InnoDB, versión, UTC y capacidad de conexiones.
Seleccionar Identidad en el cliente y sustituir los cuatro marcadores de esquema
en las secciones multiesquema. No ejecutar fragmentos POST antes de crear tablas.
Las consultas no corrigen datos ni constituyen una comprobación automática.

## Matriz exacta de configuración pendiente

### Railway web (no aplicada)

- Entorno `ENTORNO`, `SECRET_KEY` existente, HTTPS, configuración CSRF/cookie
  existente. No generar ni rotar SECRET_KEY en esta entrega.
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_IDENTIDAD`, `DB_COMERCIO`,
  `DB_INVENTARIO`, `DB_OPERACIONES`; mismo servidor y permisos multiesquema.
- `DB_MAX_CONEXIONES_CACHE`: ajustar junto al número de workers/concurrencia.
- `RAILWAY_PROXY_VALIDADO`, `TRUSTED_PROXY_HOPS`: medir la topología real, no
  adivinar el número de saltos.
- `APISPERU_TOKEN` existente, exclusivamente backend; seis variables de rate
  limit de la tabla anterior. Mantener ambas banderas nuevas en 0 inicialmente.
- `APP_PUBLIC_URL`: origen confiable HTTPS, nunca Host suministrado por cliente.
- `MAIL_ENABLED=0`, `RESEND_API_KEY`, `MAIL_FROM`, `MAIL_FROM_NAME`.
- `MAIL_PAYLOAD_ENCRYPTION_KEY`: Fernet dedicada; `MAIL_RATE_LIMIT_KEY`:
  secreto dedicado >=32 caracteres. No reutilizar la clave de APIsPERU.
- `EMAIL_VERIFICATION_TTL_HOURS=24`, `EMAIL_RESEND_MIN_SECONDS=120`,
  `EMAIL_RESEND_MAX_WINDOW=5`, `MAIL_OUTBOX_MAX_ATTEMPTS=5`,
  `MAIL_OUTBOX_LEASE_SECONDS=300` como valores iniciales a revisar.
- `EMAIL_EXISTING_GRACE_END` vacío para conservar transición histórica.
- Preservar variables y almacenamiento persistente del catálogo existentes.

### Resend y Cron (no aplicados)

1. Dominio/subdominio autorizado, registros SPF/DKIM indicados por proveedor,
   DMARC revisado, estado Verified y remitente permitido.
2. API key de envío restringida, solo en secretos backend/worker.
3. Worker con mismo código, URL, claves y acceso BD; comando
   `flask procesar-correos --limite 10`, fuera de Gunicorn. Comenzar con un solo
   cron y sin solapamientos, ajustar periodicidad según límites medidos.
4. Primero validar un lote 1 a destinatario autorizado; la bandera MAIL_ENABLED
   debe ser 1 en **ese worker** para que reclame. Mantener cron detenido hasta
   aprobar el ensayo. Después habilitar configuración coordinada web/worker.
5. Medir el lote y lease: no debe vencer mientras todavía se envían filas del
   lote; la idempotencia de Resend reduce duplicados, no promete exactly-once.

## Validaciones locales ejecutadas

Suite consolidada de cierre: **475 pruebas OK** (469 del preflight +6 nuevas),
cero fallos. `compileall` OK, 69 plantillas Jinja OK, Flask con 151 rutas OK,
contador desactivado confirmado y `git diff --check` sin errores.
Las pruebas nuevas simulan 40 solicitudes/8 hilos, ventana, clientes aislados,
errores/rollback/cierre, HMAC sin cabecera falsificada, DNI/RUC, fail-closed y
guardas de activación. Simulación no certifica concurrencia SQL real.
No se ejecutaron suites que requieren escrituras o lecturas de MariaDB TEST.
El procedimiento autorizado futuro está en `docs/validacion_mariadb_test.md`.

## Corrección posterior del checkout

La API de `registrar_facturacion_checkout` se conserva para usos autónomos
(Mi perfil y endpoint de facturación). Checkout ya no usa ese orquestador dentro
de UnidadTrabajo, sino preparación y escritura separadas. Si un consumidor
futuro ya tiene una transacción, debe usar la preparación **antes** de abrirla;
no llamar al orquestador autónomo con bloqueos activos.

No se adelantó la persistencia de facturación: continúa atómica con la compra.
No se movieron los cálculos, snapshots, reservas, pagos, entregas ni outbox.
La evidencia preparada es efímera y se usa solo en esa invocación; no se acepta
por JSON ni se almacena como comprobante de autorización reutilizable.
