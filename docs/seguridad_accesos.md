# Centro de seguridad y bloqueos de acceso

## Estructura existente verificada

Se consultó únicamente `information_schema`, en modo de solo lectura. El
servidor informó MariaDB 11.4.13 y las tres tablas usan InnoDB:

- `usuarios`: ya posee correo único, hash, estado y último acceso.
- `auditoria_accesos`: ya posee usuario, correo intentado, evento, resultado,
  IP, agente, detalle y fecha.
- `sesiones`: ya posee usuario, hash de token, IP, agente, expiración y
  revocación.

Por ello la migración no altera esas tablas. Los eventos de login reutilizan
`auditoria_accesos` y no se creó otra tabla duplicada de intentos.

## Activación segura

El bloqueo queda apagado por defecto. Las variables disponibles son:

- `LOGIN_BLOQUEO_HABILITADO`: solicita la activación.
- `LOGIN_MAX_FALLOS_CUENTA_IP`: valor inicial `3`.
- `LOGIN_MAX_FALLOS_IP`: valor inicial `20`.
- `LOGIN_VENTANA_MINUTOS`: valor inicial `15`.
- `LOGIN_BLOQUEO_MINUTOS`: valor inicial `15`.
- `RAILWAY_PROXY_VALIDADO`: confirma que staging verificó la cadena real.
- `TRUSTED_PROXY_HOPS`: cantidad exacta de proxies confiables.
- `LOGIN_MIGRACION_APROBADA`: confirma que la migración fue autorizada y
  aplicada antes de usar las tablas nuevas.

En producción no basta con `LOGIN_BLOQUEO_HABILITADO=1`: también deben existir
`RAILWAY_PROXY_VALIDADO=1` y `LOGIN_MIGRACION_APROBADA=1`. Mientras falte una
de esas aprobaciones, la aplicación no activa el bloqueo. `ProxyFix` depende
únicamente de la validación del proxy y del número de saltos.

## Validación pendiente en Railway staging

Antes de habilitar producción se debe realizar en staging:

1. Confirmar con la documentación vigente de Railway cuántos proxies agregan
   `X-Forwarded-For` antes del contenedor.
2. Registrar temporalmente, sin cookies ni credenciales, `REMOTE_ADDR` y la
   cantidad de elementos de `X-Forwarded-For` para peticiones controladas.
3. Enviar una petición externa con una cabecera `X-Forwarded-For` inventada y
   comprobar que Railway la elimina o agrega la IP real al extremo esperado.
4. Confirmar que el contenedor no sea accesible directamente sin el proxy.
5. Configurar `TRUSTED_PROXY_HOPS` con el número exacto, nunca con un valor
   estimado.
6. Probar IPv4 e IPv6 y verificar que Flask exponga la IP pública esperada en
   `request.remote_addr`.
7. Recién entonces definir `RAILWAY_PROXY_VALIDADO=1` y habilitar el bloqueo.

La aplicación nunca analiza `X-Forwarded-For` por su cuenta. Usa únicamente
`request.remote_addr`, que Werkzeug sustituye después de aplicar la confianza
configurada en `ProxyFix`.

## Persistencia y concurrencia

`contadores_acceso` conserva la ventana actual y tiene una clave única por
cuenta+IP o por IP. Cada fallo crea la fila si falta y luego utiliza
`SELECT ... FOR UPDATE`. Esto serializa incrementos aunque existan varias
instancias de Railway.

`bloqueos_acceso` conserva cada episodio, incluso después de expirar.
`desbloqueos_acceso` conserva actor, motivo, fecha e IP administrativa. Su
restricción única por bloqueo impide desbloqueos duplicados.

Los intentos y accesos exitosos reutilizan `auditoria_accesos`; no se guardan
contraseñas, tokens ni cookies. La tabla `sesiones` no necesita cambios.

## Orden de despliegue pendiente de autorización

1. Preparar los tres objetos nuevos en una base TEST aislada.
2. Ejecutar toda la suite y las pruebas concurrentes contra TEST.
3. Validar Railway staging.
4. Aprobar y ejecutar `migrations/002_identidad_seguridad_accesos.sql`.
5. Desplegar el código con el bloqueo todavía desactivado.
6. Revisar el centro administrativo.
7. Activar las variables de producción en una ventana controlada.

La migración no fue ejecutada por esta fase.
