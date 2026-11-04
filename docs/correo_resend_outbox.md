# Correo transaccional SULPAA — Resend y outbox

## Modo inicial sin correo

Con `EMAIL_VERIFICATION_REQUIRED=0` no se exige correo, no se crean solicitudes,
tokens ni eventos de verificación y sus endpoints quedan desactivados. Con
`MAIL_ENABLED=0` tampoco se encolan correos de pedidos. Registro/checkout no
necesitan claves Fernet en ese modo. No se marca a nadie como verificado.
Consultar `docs/despliegue_sin_correo.md`; el resto de esta guía describe la
activación futura con EMAIL_VERIFICATION_REQUIRED=1 y Resend configurado.

> Fase 4.4 preparada localmente. Ninguna migración, variable, dominio, cron o
> envío real ha sido activado.

## 1. Resend y dominio

1. Crear una cuenta en Resend desde su sitio oficial.
2. Añadir el dominio que enviará los mensajes (preferentemente un subdominio,
   por ejemplo `correo.sulpaa.com`).
3. Publicar exactamente los registros DNS SPF/DKIM indicados por Resend.
4. Esperar el estado **Verified** y revisar DMARC antes de usar producción.
5. Crear una API key restringida al envío y guardarla solo en Railway.

La clave nunca debe copiarse a `.env` versionados, plantillas, JavaScript,
logs ni tablas. Para pruebas se utiliza `FakeEmailProvider`.

## 2. Variables pendientes

| Variable | Uso |
|---|---|
| `MAIL_ENABLED` | `1` habilita al worker; mantener `0` durante migración |
| `RESEND_API_KEY` | API key restringida de Resend |
| `MAIL_FROM` | Remitente del dominio verificado |
| `MAIL_FROM_NAME` | Nombre visible, por defecto SULPAA |
| `APP_PUBLIC_URL` | Origen público confiable, sin derivarlo de `Host` |
| `MAIL_PAYLOAD_ENCRYPTION_KEY` | Clave Fernet dedicada para secretos temporales |
| `MAIL_RATE_LIMIT_KEY` | Secreto dedicado para HMAC de IP/correo |
| `EMAIL_VERIFICATION_TTL_HOURS` | Vencimiento, 24 por defecto |
| `EMAIL_RESEND_MIN_SECONDS` | Separación mínima entre reenvíos |
| `EMAIL_RESEND_MAX_WINDOW` | Máximo diario por clave |
| `MAIL_OUTBOX_MAX_ATTEMPTS` | Máximo de intentos del worker |
| `MAIL_OUTBOX_LEASE_SECONDS` | Recuperación de trabajos abandonados |
| `EMAIL_EXISTING_GRACE_END` | Fecha UTC opcional; dejar vacía inicialmente |

Las claves Fernet pueden generarse localmente con
`Fernet.generate_key()`. Deben almacenarse como secretos diferentes de
`SECRET_KEY`; rotarlas exige primero drenar o volver a cifrar eventos pendientes.

## 3. Migración y despliegue gradual

1. Revisar/aplicar primero las decisiones pendientes de 003 y 004.
2. Ejecutar los prechecks de `006_fase44_correo_outbox.sql` en un entorno
   autorizado y respaldar el esquema.
3. Configurar URL pública y las dos claves dedicadas; mantener
   `MAIL_ENABLED=0` para impedir envíos.
4. Aplicar 006 y desplegar la aplicación; comprobar que genera tokens/outbox
   sin enviar. Durante este cambio conviene pausar brevemente el autorregistro.
5. Configurar dominio, remitente y API key de Resend.
6. Procesar un evento dirigido exclusivamente a una cuenta autorizada.
7. Activar el procesador periódico y después `MAIL_ENABLED=1`.
8. Mantener `EMAIL_EXISTING_GRACE_END` vacía hasta decisión del propietario.

El código web no lee ni ejecuta archivos SQL. El comando de correo tampoco se
ejecuta al arrancar Gunicorn.

## 4. Funcionamiento del outbox

- Registro: usuario, perfil, rol, token hash y evento se confirman juntos.
- Checkout: `PEDIDO_CONFIRMADO:<pedido_id>` se inserta en la misma unidad de
  trabajo multiesquema que el pedido.
- El valor del token no se guarda en claro: solo su SHA-256 queda en
  `tokens_verificacion`; el outbox conserva temporalmente un payload Fernet.
- El enlace lleva el token en un fragmento `#token=`, que no llega en la
  petición GET ni en access logs. La confirmación real es un POST con CSRF; la
  pantalla ofrece también pegado manual para no depender solo de JavaScript.
- Al enviar o fallar permanentemente, el secreto cifrado se elimina.
- Una restricción única evita dos eventos con la misma clave de idempotencia.

## 5. Procesador y reintentos

Ejecución manual segura:

```bash
flask procesar-correos --limite 10
```

El worker reclama lotes con `FOR UPDATE SKIP LOCKED`, asigna una lease, cierra
la conexión y recién después llama a Resend. Los fallos de red, timeout, 429 y
5xx usan backoff exponencial acotado; los 4xx permanentes no se reintentan.
Trabajos con lease vencida pueden recuperarse.

Resend recibe `Idempotency-Key`, pero una caída después de que acepte el correo
y antes de confirmar `ENVIADO` puede producir reintento. No se promete entrega
exactamente una vez; se debe reconciliar con el ID del proveedor y sus logs.

## 6. Railway Cron (solo propuesta)

Crear, tras autorización, un servicio/cron con el mismo código y variables que
ejecute el comando anterior cada pocos minutos. Usar lotes pequeños y una
frecuencia compatible con el plan de Resend y el límite de conexiones de
Alwaysdata. No ejecutar el worker dentro del proceso web ni mantener conexiones
abiertas durante la llamada HTTPS.

## 7. Monitoreo

Supervisar conteos por `estado`, antigüedad de `PENDIENTE/REINTENTO`, eventos
`FALLIDO`, intentos y leases vencidas. `ultimo_error` contiene solo códigos
controlados, nunca cuerpos de Resend, tokens ni destinatarios. Las métricas del
CLI tampoco muestran correos.

## 8. Transición de cuentas existentes

`requiere_verificacion_correo=0` es el valor inicial para históricos. Estas
cuentas muestran aviso y pueden verificar, pero conservan permisos mientras
`EMAIL_EXISTING_GRACE_END` esté vacía. Nuevos registros escriben `1` y no pueden
confirmar compras sin verificar. Los roles GERENTE/ADMINISTRADOR históricos no
se bloquean por la fecha de gracia.

No se actualiza masivamente `correo_verificado` ni se considera verificada una
cuenta porque Resend acepte un mensaje.

La política inicial bloquea en backend la confirmación definitiva del checkout
y las rutas protegidas por roles administrativos/operativos para cuentas nuevas
pendientes. Se permite iniciar sesión, navegar sin privilegios, preparar
carrito, consultar el estado, usar Mi perfil, reenviar y cerrar sesión. Las
cuentas administrativas históricas permanecen en transición para evitar un
bloqueo sorpresivo.

## 9. Rollback

1. Poner `MAIL_ENABLED=0` y detener el cron.
2. Desplegar una versión que no escriba las tablas nuevas.
3. Exportar eventos/tokens necesarios y confirmar que no existen pendientes.
4. Solo con autorización, ejecutar en orden inverso las sentencias comentadas
   al final de la migración 006.

No eliminar tablas mientras una versión web o worker todavía las utilice.
