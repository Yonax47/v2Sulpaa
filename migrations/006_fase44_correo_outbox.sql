-- ============================================================
-- MIGRACIÓN 006 — VERIFICACIÓN DE CORREO Y OUTBOX
-- Esquema objetivo: base1sulpaa_identidad
-- Estado: PENDIENTE DE AUTORIZACIÓN. NO EJECUTAR EN PRODUCCIÓN.
-- Motor objetivo: MariaDB 11.4 / InnoDB.
-- Orden: después de revisar 003 y 004. No depende funcionalmente de 005.
-- ============================================================
-- Despliegue gradual recomendado:
--   1. ejecutar prechecks y respaldar esquema;
--   2. aplicar 006 con MAIL_ENABLED=0;
--   3. desplegar aplicación y validar generación de outbox;
--   4. configurar dominio/variables y probar un destinatario autorizado;
--   5. activar procesador; luego MAIL_ENABLED=1;
--   6. mantener EMAIL_EXISTING_GRACE_END sin definir hasta autorización.
--
-- USE base1sulpaa_identidad;

-- PRECHECKS: deben existir las tablas y columnas base.
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('usuarios', 'roles', 'usuario_roles');

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'usuarios'
  AND COLUMN_NAME IN ('id', 'correo', 'correo_verificado', 'creado_en');

-- Cuentas históricas conservan 0 y continúan bajo política de transición.
-- Solo el nuevo INSERT de autorregistro escribe 1 expresamente.
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS requiere_verificacion_correo TINYINT(1)
        NOT NULL DEFAULT 0 AFTER correo_verificado;

CREATE TABLE IF NOT EXISTS tokens_verificacion (
    id              CHAR(36) NOT NULL,
    usuario_id      CHAR(36) NOT NULL,
    proposito       ENUM('VERIFICAR_CORREO') NOT NULL,
    token_hash      BINARY(32) NOT NULL,
    expira_en       DATETIME(6) NOT NULL,
    consumido_en    DATETIME(6) NULL,
    invalidado_en   DATETIME(6) NULL,
    creado_en       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_tokens_verificacion_hash (token_hash),
    KEY idx_tokens_usuario_estado (
        usuario_id, proposito, consumido_en, invalidado_en, expira_en
    ),
    CONSTRAINT fk_tokens_verificacion_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_tokens_verificacion_expira
        CHECK (expira_en > creado_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS correos_outbox (
    id                  CHAR(36) NOT NULL,
    clave_idempotencia  VARCHAR(191) NOT NULL,
    tipo                ENUM('VERIFICAR_CORREO','PEDIDO_CONFIRMADO') NOT NULL,
    destinatario        VARCHAR(150) NOT NULL,
    plantilla           VARCHAR(80) NOT NULL,
    datos_json          LONGTEXT NOT NULL,
    secreto_cifrado     TEXT NULL,
    estado              ENUM(
        'PENDIENTE','PROCESANDO','REINTENTO','ENVIADO','FALLIDO'
    ) NOT NULL DEFAULT 'PENDIENTE',
    intentos            SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    proximo_intento_en  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    bloqueado_hasta     DATETIME(6) NULL,
    lease_token         CHAR(36) NULL,
    proveedor_id        VARCHAR(191) NULL,
    enviado_en          DATETIME(6) NULL,
    ultimo_error        VARCHAR(80) NULL,
    creado_en           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    actualizado_en      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_correos_outbox_idempotencia (clave_idempotencia),
    KEY idx_correos_outbox_pendientes (
        estado, proximo_intento_en, bloqueado_hasta, creado_en
    ),
    CONSTRAINT chk_correos_outbox_json CHECK (JSON_VALID(datos_json)),
    CONSTRAINT chk_correos_outbox_intentos CHECK (intentos <= 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Límite compartido por IP/correo/usuario, usando exclusivamente HMAC.
CREATE TABLE IF NOT EXISTS limites_correo (
    alcance            VARCHAR(40) NOT NULL,
    clave_hash         BINARY(32) NOT NULL,
    intentos           SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    ventana_inicia_en  DATETIME(6) NOT NULL,
    ultimo_intento_en  DATETIME(6) NOT NULL,
    actualizado_en     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                       ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (alcance, clave_hash),
    KEY idx_limites_correo_ventana (ventana_inicia_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- VERIFICACIÓN POSTERIOR (solo lectura).
SHOW CREATE TABLE tokens_verificacion;
SHOW CREATE TABLE correos_outbox;
SHOW CREATE TABLE limites_correo;

-- Rollback seguro requiere primero detener web/worker nuevos. No se debe
-- eliminar información mientras existan eventos pendientes. Tras exportar y
-- confirmar que no hay filas útiles:
-- DROP TABLE limites_correo;
-- DROP TABLE correos_outbox;
-- DROP TABLE tokens_verificacion;
-- ALTER TABLE usuarios DROP COLUMN requiere_verificacion_correo;
