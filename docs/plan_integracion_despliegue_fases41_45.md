# Plan único de integración y despliegue — Fases 4.1 a 4.5

**Decisión posterior:** el primer despliegue será sin correo ni Resend. Aplicar
`docs/despliegue_sin_correo.md` para la configuración inicial: ambas banderas
EMAIL_VERIFICATION_REQUIRED y MAIL_ENABLED en 0, sin claves de correo y sin
worker. 006 sigue requerida por su columna de política. Las instrucciones de
activación de correo de este documento quedan para una fase futura.

> Documento operativo. Preparado localmente; ninguna acción sobre Railway,
> Alwaysdata, Resend, DNS o datos reales ha sido ejecutada.

## Alcance del despliegue

- Fase 4.1: gráficos, notificaciones y logout.
- Fase 4.2: analítica y paginación.
- Fase 4.3: registro con DNI, rol CLIENTE y Mi perfil.
- Fase 4.4: verificación de correo, Resend y outbox.
- Fase 4.5: constancia PDF informativa bajo demanda.

La constancia PDF no crea comprobantes tributarios ni requiere migración.

## Decisiones y condiciones previas

No iniciar producción hasta contar con:

1. Autorización expresa para una ventana controlada y para ejecutar 003–006.
2. Respaldo verificable de Identidad y procedimiento de restauración probado.
3. MariaDB TEST aislada para ejecutar migraciones y pruebas de concurrencia.
4. Confirmación de MariaDB 11.4, InnoDB y transacciones entre los cuatro
   esquemas con las mismas credenciales y servidor.
5. Dominio remitente verificado en Resend mediante SPF/DKIM y política DMARC
   revisada.
6. Remitente, URL pública y secretos dedicados aprobados.
7. Validar el nuevo consumidor compartido de APIsPERU en TEST; mantener
   `APISPERU_RATE_LIMIT_ENABLED=0` y
   `APISPERU_RATE_LIMIT_MIGRATION_APPROVED=0` hasta aplicar/verificar 005.
   Revisar los hallazgos y condiciones de `docs/preflight_produccion.md`.
8. `EMAIL_EXISTING_GRACE_END` vacío durante el primer despliegue.

## A. Operaciones que pueden prepararse localmente

1. Revisar commits y verificar árbol limpio en `serna`.
2. Ejecutar las suites unitarias/mocks, `compileall`, compilación Jinja,
   arranque Flask y `git diff --check`.
3. Revisar 003–006 y preparar copias sin `USE` para el mecanismo autorizado de
   migración, manteniendo los prechecks separados de las escrituras.
4. Generar localmente, sin publicarlas, dos claves distintas:
   - `MAIL_PAYLOAD_ENCRYPTION_KEY`: Fernet.
   - `MAIL_RATE_LIMIT_KEY`: secreto aleatorio de al menos 32 caracteres.
5. Preparar una matriz de smoke tests con cuentas exclusivamente ficticias.
6. Validar PDF con productos múltiples, Unicode y datos opcionales ausentes.
7. Preparar consultas de monitoreo de solo lectura para outbox y límites.
8. Preparar el comando del worker sin ejecutarlo contra datos reales:

   ```bash
   flask procesar-correos --limite 10
   ```

## B. Operaciones que requieren autorización de producción

Todas las operaciones siguientes están pendientes y no deben ejecutarse desde
este plan sin autorización específica.

### B.1 Prechecks de infraestructura y datos

1. Confirmar destino con `SELECT DATABASE()` y versión con `SELECT VERSION()`.
2. Verificar que las tablas involucradas son InnoDB y que no existen tablas o
   índices con los nombres propuestos por 003–006.
3. Obtener conteos de respaldo para:
   - usuarios y perfiles;
   - roles y vínculos activos;
   - pedidos recientes por estado;
   - usuarios con `correo_verificado = 0`;
   - GERENTE/ADMINISTRADOR no verificados.
4. Ejecutar los prechecks de 003:
   - DNI duplicados;
   - cadenas vacías;
   - valores que no cumplen ocho dígitos;
   - índices existentes sobre `perfiles.dni`.
5. Si hay DNI duplicados o malformados, detener el despliegue. No corregir,
   borrar ni fusionar cuentas automáticamente.
6. Ejecutar el precheck de 004. Debe existir cero o una fila `CLIENTE`:
   - si no existe, 004 puede crearla;
   - si existe ACTIVA, omitir la inserción y verificar unicidad;
   - si existe INACTIVA o duplicada, detenerse y decidir manualmente.
7. Verificar que 005 no colisione con `limites_consulta_externa`.
8. Ejecutar los prechecks de 006 y revisar tipos reales de `usuarios.id`,
   `correo`, `correo_verificado` y `creado_en`.

### B.2 Variables Railway antes de desplegar código

Configurar como secretos, sin imprimir valores:

- `APP_PUBLIC_URL=https://<origen-publico-confiable>`
- `MAIL_ENABLED=0`
- `RESEND_API_KEY`
- `MAIL_FROM`
- `MAIL_FROM_NAME`
- `MAIL_PAYLOAD_ENCRYPTION_KEY`
- `MAIL_RATE_LIMIT_KEY`
- `EMAIL_VERIFICATION_TTL_HOURS`
- `EMAIL_RESEND_MIN_SECONDS`
- `EMAIL_RESEND_MAX_WINDOW`
- `MAIL_OUTBOX_MAX_ATTEMPTS`
- `MAIL_OUTBOX_LEASE_SECONDS`
- `EMAIL_EXISTING_GRACE_END` sin valor
- `APISPERU_RATE_LIMIT_ENABLED=0`
- `APISPERU_RATE_LIMIT_MIGRATION_APPROVED=0`
- `APISPERU_RATE_LIMIT_KEY` dedicada, aleatoria, >=32 caracteres
- `APISPERU_RATE_LIMIT_MAX_DNI=5`, `APISPERU_RATE_LIMIT_MAX_RUC=5`
- `APISPERU_RATE_LIMIT_WINDOW_SECONDS=600`

Conservar también las variables existentes de Flask, bases, proxy, APIsPERU y
almacenamiento. No rotar `SECRET_KEY` durante este despliegue.

Aunque `MAIL_ENABLED=0` impide que el worker reclame eventos, el registro nuevo
necesita desde el primer arranque `APP_PUBLIC_URL` y la clave Fernet para crear
la solicitud cifrada. El reenvío necesita `MAIL_RATE_LIMIT_KEY`.

### B.3 Orden de migraciones

Aplicar exclusivamente en Identidad y en este orden:

1. **003** — índice único `uq_perfiles_dni`.
2. **004** — rol CLIENTE, solo cuando el precheck autorice la inserción.
3. **005** — tabla para límite compartido de APIsPERU; consumidor implementado
   pero desactivado. Aprobar migración y activar únicamente después de TEST.
4. **006** — columna de transición, tokens, outbox y límites de correo.

Después de cada paso, ejecutar sus verificaciones. No continuar si una
estructura, conteo o restricción difiere de lo esperado.

No desplegar el código nuevo antes de 006: login, sesiones y altas consultan la
columna `requiere_verificacion_correo`. Usar ventana de mantenimiento o una
estrategia equivalente que impida servir una combinación incompatible.

### B.4 Despliegue de aplicación con correo detenido

1. Desplegar los commits aprobados de `serna`, sin mezclar cambios adicionales.
2. Mantener `MAIL_ENABLED=0` y no iniciar Cron todavía.
3. Confirmar arranque web, healthcheck, rutas y conexiones.
4. Verificar una cuenta histórica cliente y una administrativa:
   - mantienen acceso;
   - muestran aviso de verificación;
   - no fueron marcadas como verificadas automáticamente.
5. Crear una cuenta ficticia autorizada y comprobar atómicamente:
   - usuario, perfil y rol CLIENTE;
   - `requiere_verificacion_correo = 1`;
   - token con solo hash;
   - evento outbox pendiente con secreto cifrado.
6. Verificar que una cuenta nueva pendiente no confirme checkout ni use rutas
   administrativas/operativas sensibles mediante llamadas directas.

### B.5 Validación de checkout y PDF

Con una cuenta ficticia verificada y productos autorizados:

1. Confirmar precios recalculados exclusivamente por backend.
2. Completar una compra controlada y verificar un único commit lógico para
   pedido, pago, inventario, entrega y evento outbox.
3. Comprobar la clave `PEDIDO_CONFIRMADO:<pedido_id>` y ausencia de duplicados.
4. Descargar la constancia desde confirmación, Mis pedidos y detalle.
5. Verificar `application/pdf`, nombre seguro, `Content-Disposition` attachment
   y `Cache-Control: private, no-store`.
6. Confirmar que un usuario distinto obtiene 404 y que no se guardó ningún PDF.
7. Confirmar el aviso SUNAT y ausencia de DNI, tokens y referencias privadas.

### B.6 Activación controlada de correo

1. Confirmar dominio Resend verificado y remitente permitido.
2. Con Cron detenido, habilitar MAIL_ENABLED=1 solo en el worker del ensayo y
   ejecutar un lote de tamaño 1 a un destinatario expresamente autorizado.
3. Verificar HTML, texto plano, enlace con fragmento, confirmación POST+CSRF y
   limpieza del secreto cifrado tras el envío.
4. Comprobar en Resend el ID e `Idempotency-Key` sin registrar cuerpos o tokens.
5. Configurar Railway Cron con lotes pequeños y sin ejecutarlo en Gunicorn.
6. Activar `MAIL_ENABLED=1` y observar varios ciclos antes de aumentar el lote.

## Monitoreo posterior

Durante las primeras 24–48 horas revisar:

- errores 4xx/5xx, latencia y reinicios web;
- altas completas frente a rollbacks;
- rechazos por DNI duplicado;
- cuentas históricas y administrativas no bloqueadas;
- checkout, pagos, inventario y entregas por estado;
- outbox por `estado`, antigüedad, intentos y leases vencidas;
- `FALLIDO`, `MAX_INTENTOS` y `REEMPLAZADO`;
- aceptación/rechazo de Resend y reputación del dominio;
- descargas PDF y respuestas 404/500 sin datos personales en logs;
- uso de conexiones Alwaysdata por web y Cron.

No usar destinatarios, tokens, DNI ni contenido de correos como etiquetas de
métricas o campos de log.

## Estrategia de rollback

### Rollback de aplicación

1. Poner `MAIL_ENABLED=0` y detener Cron.
2. Preservar/exportar outbox pendiente; no eliminarlo.
3. Replegar al commit anterior aprobado.
4. Mantener inicialmente las estructuras aditivas 003–006: el código anterior
   puede ignorarlas y así se evita pérdida de datos.
5. Validar login, catálogo y checkout de la versión replegada.

### Rollback de datos, solo si fuera indispensable

1. Requiere una segunda autorización y respaldo confirmado.
2. No eliminar 006 mientras existan tokens/eventos útiles o una instancia nueva.
3. No eliminar/desactivar CLIENTE sin revisar todos los `usuario_roles`.
4. No retirar `uq_perfiles_dni` hasta confirmar que ninguna operación concurrente
   puede crear duplicados.
5. Desactivar las dos banderas de APIsPERU antes de retirar 005 y confirmar que
   ningún worker la usa; conservarla inicialmente para evitar pérdida de datos.
6. Ejecutar las sentencias de reversión documentadas en cada migración, en orden
   inverso, y verificar conteos después de cada paso.

## Criterio de cierre

El despliegue solo se considera aprobado cuando migraciones, smoke tests,
checkout, PDF, transición histórica y un envío controlado funcionan, sin
errores críticos durante la ventana de observación. Las pruebas que requieren
MariaDB TEST deben ejecutarse antes de autorizar producción; las pruebas locales
con mocks no sustituyen validación real de SQL, locks ni transacciones.
