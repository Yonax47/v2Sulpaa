# Despliegue controlado sin correo — preparación local

## Decisión del propietario

Desplegar mejoras 4.1–4.5 excepto verificación de correo y Resend:

```dotenv
EMAIL_VERIFICATION_REQUIRED=0
MAIL_ENABLED=0
APP_PUBLIC_URL=https://v2sulpaa-production.up.railway.app
```

No hacen falta API key Resend, clave Fernet ni clave HMAC de correo para estas
operaciones mientras permanezcan ambos modos desactivados.

## Semántica del modo

- Las altas públicas conservan DNI obligatorio validado por APIsPERU y rol CLIENTE.
- Las tres altas (pública, administrativa y repartidor) escriben
  `correo_verificado=0` y `requiere_verificacion_correo=0`.
- No se generan tokens ni eventos de verificación, tampoco aunque un llamador
  interno entregue accidentalmente una solicitud al repositorio desactivado.
- Login, roles y checkout no exigen correo confirmado, incluso en cuentas que
  tenían la marca obligatoria. No se actualizan masivamente cuentas existentes.
- No se muestran CTA/banners de verificación. Sus rutas GET/POST responden 404;
  CSRF conserva su protección normal y puede rechazar antes un POST sin CSRF.
- Con MAIL_ENABLED=0, checkout no consulta destinatarios ni inserta outbox.
  Se conserva la misma transacción de facturación, pedido, pago, inventario y
  entrega. No hay llamadas Resend ni necesidad de Fernet.
- No se emitirán retroactivamente correos de pedidos realizados en este modo.
- CLI de correo desactivada no reclama filas. Si se habilita mail por separado
  en el futuro, el worker tampoco enviará verificaciones con la política apagada.

EMAIL_VERIFICATION_REQUIRED=1 restaura la política original para nuevas altas y
cuentas ya marcadas, requiere claves de verificación y crea token/outbox atómicos.
Las cuentas creadas durante la pausa mantienen marca 0: se consideran históricas
en transición, no se bloquean retroactivamente por activar la bandera. Una futura
fecha de gracia requiere decisión expresa. Nunca se marca una cuenta verificada
solo por permitirle operar.

## Migraciones necesarias

**003 → 004 → 005 → 006**, sujetas a respaldo y prechecks reales:

- 003: unicidad DNI; detenerse ante duplicados/vacíos/malformados.
- 004: CLIENTE debe existir exactamente una vez y ACTIVO.
- 005: contador persistente de APIsPERU.
- 006: **todavía necesaria** porque las lecturas de login, sesión y perfil y las
  tres altas utilizan `requiere_verificacion_correo`. Se aplica íntegra si sus
  prechecks pasan; sus tablas de tokens/outbox permanecen sin uso con correo
  apagado. No se mantiene un esquema parcial ni un fallback que oculte errores.

No ejecutar la inserción de CLIENTE si ya existe ACTIVO. No repetir 003 sin
verificar el índice. IF NOT EXISTS no valida una estructura existente. Revisar
tipos/collation de usuarios.id contra la FK local propuesta por 006 e InnoDB en
todas las tablas involucradas. No corregir datos reales automáticamente.

## Rate limit y proxy

Mantener inicialmente:

```dotenv
APISPERU_RATE_LIMIT_ENABLED=0
APISPERU_RATE_LIMIT_MIGRATION_APPROVED=0
APISPERU_RATE_LIMIT_MAX_DNI=5
APISPERU_RATE_LIMIT_MAX_RUC=5
APISPERU_RATE_LIMIT_WINDOW_SECONDS=600
```

Después de verificar 005 y la cadena real de proxies:

1. Verificar que el contenedor no pueda recibir tráfico evitando el proxy.
2. Establecer RAILWAY_PROXY_VALIDADO=1 y TRUSTED_PROXY_HOPS al número **medido**.
3. Provisionar APISPERU_RATE_LIMIT_KEY aleatoria dedicada >=32 caracteres igual
   en todos los workers, sin imprimirla ni versionarla.
4. Aprobar migración y activar ambas banderas de APIsPERU en una configuración
   coordinada. Conservar APISPERU_TOKEN backend y SECRET_KEY existentes.

No adivinar saltos ni activar un límite supuestamente por IP con cabeceras no
confiables. Si el contador habilitado falla, no se llama al proveedor.

## Puertas obligatorias antes de publicar

1. Confirmar servidor y cuatro nombres de esquema con un operador autorizado.
2. Obtener respaldo completo consistente de los cuatro esquemas, copia cifrada
   fuera del servidor, checksums y prueba de restauración verificable. Sin esto
   no aplicar migraciones. No guardar dumps en Git ni imprimir credenciales.
3. Ejecutar `docs/sql/preflight_003_006_solo_lectura.sql` con nombres revisados.
   Guardar evidencias sanitizadas; abortar ante incompatibilidades.
4. Aplicar solo pasos no existentes y verificados, en orden, comprobando estructura
   después de cada uno. No suponer que DDL se revierte con ROLLBACK.
5. Configurar Railway para ambos modos apagados y URL pública confiable.
6. Revisar remoto/ramas, integrar sin descartar cambios ajenos, publicar main
   únicamente después de aprobar las puertas anteriores y confirmar commit de
   rollback `a3195abf7d729d7a336e7d9256531eb8a842f5d4`.
7. Confirmar commit efectivo del deployment y healthcheck; validar login real,
   GERENTE/ADMINISTRADOR, gráficos/filtros/paginación, perfil y logout.
8. Registro real solo con DNI autorizado; no usar terceros. Checkout real solo
   sin cargos o con aprobación específica. Probar PDF únicamente de pedido propio.
   Lo no ejecutado debe reportarse como pendiente, nunca como operativo.

## Bloqueos observados en esta ejecución

**Actualización posterior:** ya se confirmó acceso MariaDB por TLS en solo
lectura y se localizaron los cuatro respaldos; recuperación aún no probada.
Se corrigió localmente 004 para `roles.id SMALLINT UNSIGNED AUTO_INCREMENT`.
Consultar `docs/alwaysdata_prechecks_confirmados.md` y el paquete SQL exacto
allí indicado. Railway sigue sin acceso CLI autenticado; no se aplicó SQL.

No hay clientes `mariadb-dump`/`mysqldump` ni CLI Railway/GitHub disponibles.
No se detectaron tokens Railway en entorno/.env. Solo se comprobó presencia de
variables de conexión, sin revelar valores ni conectar al servidor. No se
obtuvo ni verificó un respaldo: por ello se detuvo la etapa productiva antes de
abrir conexiones, aplicar migraciones, integrar/pushear main o desplegar.

Se necesita una herramienta de respaldo disponible y acceso Railway autenticado
(o un operador que realice esas acciones con evidencia). No se inventan ni
rotan credenciales, ni se instala un servicio externo automáticamente.

Resultado local: 486 pruebas seguras aprobadas, incluidas pruebas de ambos modos.
La validación real de MariaDB, datos, usuarios, gráficos y checkout productivos
permanece pendiente. Guías adicionales: `preflight_produccion.md`,
`validacion_mariadb_test.md` y `plan_integracion_despliegue_fases41_45.md`.

## Rollback

Detener despliegue/worker y volver al commit productivo anterior si los smoke
tests fallan. Conservar inicialmente estructuras aditivas, respaldos y datos
nuevos. No retirar CLIENTE con vínculos ni eliminar tokens/outbox útiles.
Reversión estructural/restauración requiere revisión de dependencias y evidencia
del respaldo; no ejecutar cambios destructivos automáticamente.
