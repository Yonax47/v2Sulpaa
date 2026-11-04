# Validación MariaDB TEST — procedimiento preparado, no ejecutado

Este documento **no autoriza** crear bases, migrar, extraer datos productivos ni
ejecutar limpieza. Todos esos pasos requieren autorización separada. Nunca
apuntar los scripts TEST a Alwaysdata productiva.

## 1. Respaldo y material seguro

1. Un operador autorizado obtiene respaldo consistente de los cuatro esquemas
   InnoDB en una ventana coordinada (transacción consistente, sin DDL concurrente).
   Registrar versión, fecha, checksums y ubicación cifrada con acceso mínimo.
2. Utilizar archivo de opciones de cliente o gestor de secretos, nunca contraseña
   en argumentos/historial. No guardar dumps ni credenciales en Git ni adjuntar
   resultados de SELECT con documentos/correos reales a incidencias.
3. Probar restauración en un destino autorizado separado antes de usar el backup
   como garantía. Dump lógico consistente de un solo servidor no equivale a
   backup verificado si hubo cambios DDL concurrentes.
4. Para TEST preferir estructura sin datos + fixtures sintéticos. No restaurar
   clientes reales en TEST. Eliminar de material de prueba claves, tokens,
   destinatarios y outbox real antes de cualquier importación autorizada.

## 2. Cuatro esquemas realmente aislados

1. Provisionar, solo tras autorización, MariaDB 11.4 dedicada fuera de producción,
   usuario exclusivo y cuatro esquemas distintos con prefijo aprobado, por
   ejemplo `sulpaa_test_identidad`, `sulpaa_test_comercio`,
   `sulpaa_test_inventario`, `sulpaa_test_operaciones`.
2. Importar estructura revisada de los cuatro dominios y fixtures falsos. Usuario
   de aplicación sin permisos en producción; usuario migrador distinto si es
   posible. Restricciones FK locales conservadas; no desactivarlas para ocultar
   incompatibilidades. Revisar referencias de esquema en vistas/triggers/rutinas.
3. Configurar `.env.test` ignorado con `SULPAA_TESTING=1`, variables `DB_*_TEST`
   exclusivas y `DB_TEST_SCHEMA_PREFIX`. Consultar `docs/entorno_pruebas.md` y
   `scripts/testing/sql/README.md`; los scripts requieren confirmación exacta
   de host/prefijo. No usar valores productivos ni fallback.
4. Ejecutar primero diagnóstico local; luego verificación READ ONLY autorizada.
   El verificador existente no sustituye los postchecks específicos 003–006.
5. Bloquear egress de red y usar mocks para APIsPERU/Resend. MAIL_ENABLED=0,
   claves Fernet/HMAC sintéticas, APP_PUBLIC_URL de TEST.

## 3. Migraciones y postchecks

1. Seleccionar manualmente Identidad TEST; ejecutar prechecks del SQL de solo
   lectura preparado y comparar metadatos con repositorios y migraciones.
2. Ensayar fixtures de DNI duplicado, vacío y malformado: precheck debe bloquear
   autorización de 003, sin autocorregir nada. Después usar fixture válido.
3. Aplicar **003**, verificar UNIQUE completo de dni. Dos inserciones sintéticas
   con el mismo DNI no nulo deben fallar; múltiples NULL deben aceptarse.
4. Aplicar **004**: CLIENTE exactamente una vez ACTIVO; un rol inactivo debe
   detener la operación, no reactivarse por sorpresa. Revisar vínculos.
5. Aplicar **005**: verificar PK, BINARY(32), InnoDB, columnas y fechas. Solo
   entonces probar APISPERU_RATE_LIMIT_MIGRATION_APPROVED=1 y ENABLED=1 en TEST.
6. Aplicar **006**: comparar FK y collation de usuarios.id; verificar columna
   DEFAULT 0, tokens, outbox, índices y CHECK. `IF NOT EXISTS` no valida DDL.
7. Guardar evidencias sin filas personales. Recordar commit implícito de DDL:
   no afirmar rollback integral de archivos SQL con BEGIN/ROLLBACK.

## 4. Transacciones multiesquema

1. En una única conexión TEST insertar fixtures dependientes en Identidad,
   Comercio, Inventario y Operaciones, alternando esquema sin commit intermedio.
2. Desde otra conexión confirmar que no son visibles antes del commit.
3. Forzar fallo al insertar el outbox: rollback debe revertir pedido, pago,
   inventario y entrega. Confirmar conteos iniciales en los cuatro dominios.
4. Repetir con commit: todas las filas deben aparecer juntas. No llamar Resend.
5. Ejecutar checkout con importe manipulado del navegador y verificar uso de
   precios snapshot backend, stock, pago, entrega y evento único por pedido.

## 5. Concurrencia real del contador y unicidad

1. Usar 40 llamadas concurrentes, cada una con conexión independiente y la misma
   HMAC/IP sintética, DNI operación y ventana de 600 s, máximo 5.
2. Exactamente 5 autorizaciones; 35 rechazos, una fila con intentos=5. Otra IP
   y RUC deben tener presupuestos separados. No realizar HTTP real.
3. Repetir en dos procesos distintos, no solo hilos. Inspeccionar locks y
   latencia en TEST. Una solicitud bloqueada debe usar el reloj posterior al lock.
4. Simular fallo SQL, falta de tabla, timeout de lock y fallo de commit: el cliente
   no debe llamar APIsPERU ni hacer fallback local; revisar cierre de sockets.
5. Con fixture de ventana vencida, comprobar reinicio. Ensayar dos registros con
   mismo DNI en paralelo: un alta completa como máximo y ningún perfil parcial.

## 6. Outbox, leases y SKIP LOCKED

1. Crear eventos sintéticos transaccionales con FakeEmailProvider.
2. Worker A mantiene bloqueo en un evento; worker B con SKIP LOCKED no debe
   reclamar esa fila ni quedar bloqueado por ella.
3. Dos workers reclaman lotes diferentes. Comprobar lease_token, commit y cierre
   físico de conexiones antes del proveedor; en CLI usar un contexto por ciclo.
4. Simular 429, timeout, 500 y error permanente: comprobar backoff, intentos,
   máximo y limpieza del secreto cifrado.
5. Abandonar una lease y verificar recuperación; propietario anterior no puede
   marcar ENVIADO con token de lease obsoleto. Medir duración del lote vs lease.
6. Reinsertar clave PEDIDO_CONFIRMADO idéntica: un evento. Simular aceptación
   seguida de fallo al marcar enviado; mismo Idempotency-Key en el reintento,
   sin prometer entrega exactamente una vez.
7. Dos POST del mismo token: solo uno verifica. GET nunca consume. Reenvío
   invalida token/eventos reemplazados. Probar rate limit de correo entre procesos.

## 7. Regresión funcional y PDF

Ejecutar suites integradas del entorno aislado, incluyendo usuarios, entregas,
lecturas y checkout reales, además de la suite local con mocks. Probar cuentas
históricas y nuevas, CSRF, roles, paginación y dashboard. Descargar PDF propio;
ajeno/inexistente debe ser 404, sin modificar tablas ni guardar archivos.
Verificar Unicode, advertencia SUNAT, importes, cabeceras privadas y ausencia de
tokens/DNI. Usar navegador manual si se autoriza; no automatizarlo.

## 8. Limpieza y rollback

1. Parar procesos TEST y desactivar mail/contador. Exportar solo evidencias
   sanitizadas. No copiar outbox TEST a producción.
2. Borrar exclusivamente fixtures identificados por UUID/prefijo de la ejecución,
   en orden de FK, con revisión y autorización. No usar borrado amplio ni
   comandos contra un destino cuya identidad no se haya comprobado.
3. Si se autoriza destruir TEST, verificar host y los cuatro nombres completos;
   nunca reutilizar un comando genérico sin confirmar esos valores.
4. Para rollback de aplicación: desactivar ambas banderas del contador y correo,
   parar Cron, desplegar versión previa compatible; conservar tablas aditivas y
   eventos útiles. No rotar SECRET_KEY ni claves Fernet para 'deshacer' un envío.
5. Rollback de esquema solo con respaldo y autorización nuevos: 006, 005, 004,
   003 en orden inverso según dependencias, preservando eventos y roles usados.
   No borrar CLIENTE con vínculos existentes. Ensayar restauración, tiempos y
   conteos. No suponer que ROLLBACK revierte DDL.
