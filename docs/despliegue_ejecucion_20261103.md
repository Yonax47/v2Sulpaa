# Evidencia de preparación y migraciones — 2026-11-03

## Recuperación comprobada

- Imagen oficial MariaDB 11.4.13; contenedores aislados sin red ni puertos.
- Respaldos originales recuperados: 91 tablas, 109 FKs sin huérfanos.
- Nuevo respaldo consistente de los cuatro esquemas obtenido con cliente oficial
  Windows, `--single-transaction`, rutinas, eventos, triggers y datos binarios.
- Nuevo respaldo: 449650 bytes, SHA-256
  `7edbcbfe5aece8bada0cfdd04d7b6bec3074bfb9314745c18a1f268a9a9cd449`.
- Restauración independiente del respaldo nuevo: 91 tablas, 109 FKs sin huérfanos.
- Copia persistente fuera del servidor: Descargas / `sulpaa-predeploy-20261103`.
  Los dumps y archivos de credenciales no están en Git.

## Ensayos reales en contenedor

- 004 corregida para `roles.id SMALLINT UNSIGNED AUTO_INCREMENT`.
- 005 y 006 aplicadas sin errores en la copia aislada.
- Commit y rollback entre cuatro esquemas InnoDB comprobados.
- Contador: 40 solicitudes SQL concurrentes, cinco admitidas y 35 rechazadas.
- SKIP LOCKED omite una fila bloqueada sin esperar su liberación.

## Alwaysdata: aplicación realizada

Servidor autorizado `mysql-base1sulpaa.alwaysdata.net`, MariaDB 11.4.13.
Conexión TLS con certificado validado. Prechecks READ ONLY aprobados antes de
permitir escrituras. Contrato base de columnas de los cuatro dominios comprobado.

- 003: satisfecha por `uq_perfiles_dni` existente; no se repitió ALTER.
- 004: CLIENTE insertado ACTIVO sin modificar los cinco roles anteriores.
- 005: `limites_consulta_externa` creada y verificada InnoDB.
- 006: columna de política y tres tablas creadas y verificadas InnoDB.
- Conteo de usuarios y suma de correo_verificado conservados; todos los usuarios
  previos mantienen requiere_verificacion_correo=0.
- Evidencia privada de aplicación: `sulpaa-migration-audit.json` en el directorio
  temporal aprobado de OpenCode. Ningún dato personal se incorpora al informe.

## Configuración Railway preparada

Proyecto `pacific-fascination`, entorno `production`, servicio `v2Sulpaa`.

```dotenv
EMAIL_VERIFICATION_REQUIRED=0
MAIL_ENABLED=0
APP_PUBLIC_URL=https://v2sulpaa-production.up.railway.app
APISPERU_RATE_LIMIT_ENABLED=0
APISPERU_RATE_LIMIT_MIGRATION_APPROVED=1
APISPERU_RATE_LIMIT_MAX_DNI=5
APISPERU_RATE_LIMIT_MAX_RUC=5
APISPERU_RATE_LIMIT_WINDOW_SECONDS=600
```

SECRET_KEY conservada y contrastada sin imprimir valores. No se activó Resend
ni worker. El límite compartido permanece apagado hasta validar el proxy;
los limitadores locales anteriores siguen presentes. Configuración preparada
con `--skip-deploys` para no desplegar antes de verificar las migraciones.

## Validación local anterior a la publicación

489 pruebas seguras aprobadas, cero fallos. Compilación de Python y 69 plantillas
Jinja correctas; arranque sin correo y sin claves de correo comprobado.

Este documento registra la preparación y la aplicación SQL, no sustituye la
comprobación posterior del deployment efectivo. La validación pública y las
rutas autenticadas deben informarse separadamente; no se afirma una compra
real ni una consulta de DNI válido sin autorización de su titular.
