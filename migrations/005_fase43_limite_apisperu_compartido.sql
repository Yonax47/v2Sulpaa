-- ============================================================
-- PROPUESTA 005 — LÍMITE COMPARTIDO PARA CONSULTAS APISPERU
-- Esquema objetivo: base1sulpaa_identidad
-- Estado: PENDIENTE DE AUTORIZACIÓN. NO EJECUTAR NI ACTIVAR.
-- ============================================================
--
-- El consumidor está implementado en app/identidad/apisperu_rate_limit.py.
-- Permanece DESACTIVADO por defecto. Aplicar/verificar esta tabla antes de
-- aprobar APISPERU_RATE_LIMIT_MIGRATION_APPROVED y habilitar el contador.
-- Los límites locales anteriores siguen como defensa adicional.
--
-- ``clave_hash`` debe ser HMAC-SHA256 de la IP normalizada con un secreto de
-- backend dedicado. No se debe guardar DNI, token APIsPERU ni respuesta del
-- proveedor. La HMAC evita persistir la IP en claro y dificulta enumerarla.
--
-- Algoritmo propuesto por solicitud, dentro de UNA transacción:
--   1. INSERT ... ON DUPLICATE KEY UPDATE (sin cambio) de la clave;
--   2. SELECT ... FOR UPDATE de la fila;
--   3. reiniciar ventana vencida o rechazar si intentos >= límite;
--   4. incrementar intentos y COMMIT antes de consultar APIsPERU.
-- La PK serializa solicitudes concurrentes para la misma clave en todos los
-- workers que comparten MariaDB.

-- USE base1sulpaa_identidad;

-- PRECHECK: verificar destino y colisiones antes de ejecutar el CREATE.
SELECT DATABASE() AS esquema, VERSION() AS version_mariadb;
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'limites_consulta_externa';
-- Si ya existe, comparar columnas, PK e índices con el contrato inferior;
-- IF NOT EXISTS no garantiza que una tabla previa sea compatible.

CREATE TABLE IF NOT EXISTS limites_consulta_externa (
    servicio            VARCHAR(40) NOT NULL,
    operacion           VARCHAR(60) NOT NULL,
    clave_hash          BINARY(32) NOT NULL,
    intentos            SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    ventana_inicia_en   DATETIME(6) NOT NULL,
    ultimo_intento_en   DATETIME(6) NOT NULL,
    actualizado_en      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (servicio, operacion, clave_hash),
    KEY idx_limites_consulta_ventana (ventana_inicia_en),
    CONSTRAINT chk_limites_consulta_intentos CHECK (intentos >= 0)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- POSTCHECK (sin datos personales).
SHOW CREATE TABLE limites_consulta_externa;

-- Limpieza propuesta (manual o tarea autorizada), nunca activada aquí:
-- DELETE FROM limites_consulta_externa
-- WHERE ventana_inicia_en < (NOW(6) - INTERVAL 2 DAY);

-- Reversión, solo con autorización y después de desactivar el código futuro:
-- DROP TABLE limites_consulta_externa;
