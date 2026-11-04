# Prechecks reales y paquete SQL — sin escrituras productivas

## Evidencia observada por el agente

Conexión a `mysql-base1sulpaa.alwaysdata.net` usando variables locales ya
existentes, con TLS y validación de certificado. Sesiones `READ ONLY` cerradas
mediante rollback. No se imprimieron secretos ni filas personales.

- MariaDB 11.4.13; esquema seleccionado `base1sulpaa_identidad`.
- 24 perfiles: 1 DNI NULL, 0 vacíos, 0 inválidos, 0 grupos duplicados.
- UNIQUE `uq_perfiles_dni` completo sobre `dni`, sin prefijo: **003 satisfecha**.
- `usuarios.id`: CHAR(36), PK, utf8mb4_unicode_ci.
- CLIENTE ausente; cinco roles previos ACTIVO.
- `roles.id`: **SMALLINT UNSIGNED AUTO_INCREMENT**.
- UNIQUE `uq_roles_codigo`; estado admite ACTIVO e INACTIVO.
- Las cuatro tablas nuevas de 005/006 y la columna de transición no existen.
- No hay colisiones con los nombres de constraints nuevos comprobados de 006.
- Tablas visibles: Identidad 12, Comercio 36, Inventario 9, Operaciones 34.
  Ninguna tabla con motor distinto de InnoDB entre las tablas base visibles.
- `max_user_connections=40`; Threads_connected global observado 137. El segundo
  número es global del servidor y no mide el consumo del usuario de SULPAA.

**Incompatibilidad encontrada y corregida localmente:** la 004 original intentaba
insertar UUID() en el ID numérico. Ahora omite `id` y deja actuar AUTO_INCREMENT.
No se cambiaron tipos, secuencias, roles ni vínculos en el servidor.

## Respaldos localizados en Descargas

Solo comprobación estática de archivos, sin ejecutar su contenido ni copiarlo
al repositorio. Todos se decodifican UTF-8, contienen COMMIT y terminan en `;`.
El número de CREATE TABLE coincide con los conteos observados en cada esquema.

| Archivo | Bytes | Tablas DDL | SHA-256 |
|---|---:|---:|---|
| base1sulpaa_identidad.sql | 121072 | 12 | 0370910a256285212ca0fd51ff8c83911a358066e704e9195a520e87e880c02c |
| base1sulpaa_comercio.sql | 162730 | 36 | 352835a10303a680a2f376b002c1caaea64e7e409d72bb302ae9ccf4b67091d6 |
| base1sulpaa_inventario.sql | 49755 | 9 | 429dc53916cdc2b8a48a4177f8340c4e8d163dc74df5cc282e7415abec43873a |
| base1sulpaa_operaciones.sql | 119367 | 34 | 41c33dd570318d925df2ae265598ffdd30b274612f74b7e8d2b10080862da5ee |

Estos datos permiten identificar archivos y detectar cambios posteriores, pero
**no prueban restauración, consistencia entre exportaciones ni igualdad de datos**.
No se certifica recuperación viable hasta importar en un destino aislado y
verificar integridad. Docker CLI existe pero el motor Linux no está iniciado;
no hay clientes MariaDB locales disponibles. No se creó un entorno de prueba.

## Paquete exacto para el destino real

`docs/sql/alwaysdata_004_005_006_sin_correo.sql` contiene, en orden:

1. USE base1sulpaa_identidad.
2. 004 corregida para ID AUTO_INCREMENT, sin tocar roles anteriores.
3. Tabla de 005 y SHOW CREATE de comprobación.
4. Columna y tres tablas de 006, con FK local e índices originales.
5. Postchecks estructurales y conteos por política, sin datos personales.

**No importarlo antes de verificar recuperación.** Si cambia el estado del
servidor, repetir prechecks. El paquete falla ante tablas/columna ya existentes
en lugar de ocultar colisiones. No reimportarlo completo tras un fallo parcial:
revisar primero qué pasos quedaron aplicados. No activar continuar ante errores.
Los DDL tienen commit implícito; no prometer rollback transaccional del archivo.

No se aplicaron 004, 005 ni 006. No se hizo push, merge ni despliegue.

## Acceso Railway

Railway CLI no está instalada y no hay token Railway en las variables revisadas.
Es necesario instalar la CLI oficial y autenticarse con `railway login`, luego
vincular el proyecto/entorno/servicio v2Sulpaa con `railway link`.
No compartir tokens en el chat. No se configuraron variables ni se activó worker.

Tras comprobar migraciones, la configuración de correo será:

```dotenv
EMAIL_VERIFICATION_REQUIRED=0
MAIL_ENABLED=0
APP_PUBLIC_URL=https://v2sulpaa-production.up.railway.app
```

El rate limit permanece desactivado hasta confirmar 005 y el proxy real.
SECRET_KEY y credenciales existentes se conservan.
