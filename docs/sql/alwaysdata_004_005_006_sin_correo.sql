-- LISTO PARA REVISIÓN/IMPORTACIÓN. NO EJECUTADO POR EL AGENTE.
-- Destino: mysql-base1sulpaa.alwaysdata.net / MariaDB 11.4.13.
-- Requiere recuperación probada ANTES de importar y ventana controlada.
-- 003 YA SATISFECHA: no repetir uq_perfiles_dni.
-- Estado precomprobado: CLIENTE ausente; las cuatro tablas nuevas y la columna
-- requiere_verificacion_correo ausentes. Volver a comprobar si hubo cambios.
-- CREATE sin IF NOT EXISTS intencional: una colisión debe detener la importación,
-- no ocultar estructuras incompatibles. No usar "continuar ante errores".
-- DDL hace commit implícito: este archivo NO es una transacción reversible.

USE base1sulpaa_identidad;

-- 004. roles.id es SMALLINT UNSIGNED AUTO_INCREMENT, confirmado por SELECT.
-- No insertar UUID, no modificar IDs existentes ni vínculos usuario_roles.
START TRANSACTION;
INSERT INTO roles (codigo, nombre, descripcion, estado)
SELECT 'CLIENTE', 'Cliente',
       'Cuenta de cliente creada mediante autorregistro.', 'ACTIVO'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE codigo = 'CLIENTE');
COMMIT;
SELECT codigo, estado, COUNT(*) AS cantidad
FROM roles WHERE codigo = 'CLIENTE' GROUP BY codigo, estado;
-- Esperado: CLIENTE / ACTIVO / 1.

-- 005. Compatible con el consumidor del rate limit; permanece desactivado.
CREATE TABLE limites_consulta_externa (
    servicio VARCHAR(40) NOT NULL,
    operacion VARCHAR(60) NOT NULL,
    clave_hash BINARY(32) NOT NULL,
    intentos SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    ventana_inicia_en DATETIME(6) NOT NULL,
    ultimo_intento_en DATETIME(6) NOT NULL,
    actualizado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                   ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (servicio, operacion, clave_hash),
    KEY idx_limites_consulta_ventana (ventana_inicia_en),
    CONSTRAINT chk_limites_consulta_intentos CHECK (intentos >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
SHOW CREATE TABLE limites_consulta_externa;

-- 006. usuarios.id CHAR(36) utf8mb4_unicode_ci PK, confirmado por SELECT.
ALTER TABLE usuarios
    ADD COLUMN requiere_verificacion_correo TINYINT(1) NOT NULL DEFAULT 0
    AFTER correo_verificado;

CREATE TABLE tokens_verificacion (
    id CHAR(36) NOT NULL,
    usuario_id CHAR(36) NOT NULL,
    proposito ENUM('VERIFICAR_CORREO') NOT NULL,
    token_hash BINARY(32) NOT NULL,
    expira_en DATETIME(6) NOT NULL,
    consumido_en DATETIME(6) NULL,
    invalidado_en DATETIME(6) NULL,
    creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_tokens_verificacion_hash (token_hash),
    KEY idx_tokens_usuario_estado
        (usuario_id, proposito, consumido_en, invalidado_en, expira_en),
    CONSTRAINT fk_tokens_verificacion_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_tokens_verificacion_expira CHECK (expira_en > creado_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE correos_outbox (
    id CHAR(36) NOT NULL,
    clave_idempotencia VARCHAR(191) NOT NULL,
    tipo ENUM('VERIFICAR_CORREO','PEDIDO_CONFIRMADO') NOT NULL,
    destinatario VARCHAR(150) NOT NULL,
    plantilla VARCHAR(80) NOT NULL,
    datos_json LONGTEXT NOT NULL,
    secreto_cifrado TEXT NULL,
    estado ENUM('PENDIENTE','PROCESANDO','REINTENTO','ENVIADO','FALLIDO')
        NOT NULL DEFAULT 'PENDIENTE',
    intentos SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    proximo_intento_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    bloqueado_hasta DATETIME(6) NULL,
    lease_token CHAR(36) NULL,
    proveedor_id VARCHAR(191) NULL,
    enviado_en DATETIME(6) NULL,
    ultimo_error VARCHAR(80) NULL,
    creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    actualizado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                   ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_correos_outbox_idempotencia (clave_idempotencia),
    KEY idx_correos_outbox_pendientes
        (estado, proximo_intento_en, bloqueado_hasta, creado_en),
    CONSTRAINT chk_correos_outbox_json CHECK (JSON_VALID(datos_json)),
    CONSTRAINT chk_correos_outbox_intentos CHECK (intentos <= 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE limites_correo (
    alcance VARCHAR(40) NOT NULL,
    clave_hash BINARY(32) NOT NULL,
    intentos SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    ventana_inicia_en DATETIME(6) NOT NULL,
    ultimo_intento_en DATETIME(6) NOT NULL,
    actualizado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                   ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (alcance, clave_hash),
    KEY idx_limites_correo_ventana (ventana_inicia_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SHOW CREATE TABLE tokens_verificacion;
SHOW CREATE TABLE correos_outbox;
SHOW CREATE TABLE limites_correo;
SELECT requiere_verificacion_correo, correo_verificado, COUNT(*) AS cantidad
FROM usuarios GROUP BY requiere_verificacion_correo, correo_verificado;
-- Requiere=0 para todos los usuarios previos; correo_verificado sin actualizar.
-- No activar mail ni worker. No ejecutar DROP/DELETE para deshacer errores.
