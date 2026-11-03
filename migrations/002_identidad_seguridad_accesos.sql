-- ============================================================
-- MIGRACIÓN 002 — CENTRO DE SEGURIDAD Y BLOQUEOS DE ACCESO
-- Esquema objetivo: base1sulpaa_identidad
-- Estado: PENDIENTE DE AUTORIZACIÓN. NO EJECUTAR EN PRODUCCIÓN.
-- Motor verificado: MariaDB 11.4.13 / InnoDB.
-- ============================================================

-- Verificación realizada antes de diseñar esta migración:
-- usuarios ya contiene id, correo, password_hash, estado y ultimo_acceso_en.
-- auditoria_accesos ya contiene usuario_id, correo_intentado, evento,
-- resultado, direccion_ip, user_agent, detalle y creado_en.
-- sesiones ya contiene usuario_id, token_hash, direccion_ip, user_agent,
-- expira_en y revocado_en. No se altera ninguna de estas tres tablas.

-- Seleccionar de forma explícita el esquema autorizado antes de ejecutar.
-- USE base1sulpaa_identidad;

-- Una fila resume la ventana vigente para una combinación cuenta+IP o IP.
-- La clave única permite INSERT IGNORE + SELECT FOR UPDATE, evitando que dos
-- instancias pierdan incrementos cuando reciben fallos al mismo tiempo.
CREATE TABLE IF NOT EXISTS contadores_acceso (
    tipo                ENUM('CUENTA_IP','IP') NOT NULL,
    correo_clave        VARCHAR(150) NOT NULL DEFAULT '',
    direccion_ip        VARCHAR(45) NOT NULL,
    usuario_id          CHAR(36) NULL,
    intentos            SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    ventana_inicia_en   DATETIME(6) NULL,
    ultimo_intento_en   DATETIME(6) NULL,
    bloqueado_hasta     DATETIME(6) NULL,
    actualizado_en      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tipo, correo_clave, direccion_ip),
    KEY idx_contadores_bloqueado (bloqueado_hasta),
    KEY idx_contadores_usuario (usuario_id),
    CONSTRAINT fk_contadores_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- Cada activación genera un episodio inmutable. La expiración se calcula con
-- expira_en; no hace falta una tarea programada para cambiar su estado.
CREATE TABLE IF NOT EXISTS bloqueos_acceso (
    id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tipo                  ENUM('CUENTA_IP','IP') NOT NULL,
    usuario_id            CHAR(36) NULL,
    correo_objetivo       VARCHAR(150) NULL,
    direccion_ip          VARCHAR(45) NOT NULL,
    intentos_al_bloquear  SMALLINT UNSIGNED NOT NULL,
    primer_intento_en     DATETIME(6) NOT NULL,
    ultimo_intento_en     DATETIME(6) NOT NULL,
    bloqueado_en          DATETIME(6) NOT NULL,
    expira_en             DATETIME(6) NOT NULL,
    desbloqueado_en       DATETIME(6) NULL,
    creado_en             DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_bloqueos_estado (desbloqueado_en, expira_en),
    KEY idx_bloqueos_correo (correo_objetivo, bloqueado_en),
    KEY idx_bloqueos_ip (direccion_ip, bloqueado_en),
    KEY idx_bloqueos_usuario (usuario_id),
    CONSTRAINT fk_bloqueos_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_bloqueos_fechas
        CHECK (expira_en > bloqueado_en),
    CONSTRAINT chk_bloqueos_intentos
        CHECK (intentos_al_bloquear > 0)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- El UNIQUE por bloqueo impide dos desbloqueos manuales concurrentes. El
-- motivo y la IP administrativa se conservan sin borrar los fallos previos.
CREATE TABLE IF NOT EXISTS desbloqueos_acceso (
    id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    bloqueo_id           BIGINT UNSIGNED NOT NULL,
    desbloqueado_por_id  CHAR(36) NOT NULL,
    motivo               VARCHAR(500) NOT NULL,
    direccion_ip         VARCHAR(45) NOT NULL,
    creado_en            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_desbloqueos_bloqueo (bloqueo_id),
    KEY idx_desbloqueos_actor (desbloqueado_por_id, creado_en),
    CONSTRAINT fk_desbloqueos_bloqueo
        FOREIGN KEY (bloqueo_id) REFERENCES bloqueos_acceso (id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_desbloqueos_actor
        FOREIGN KEY (desbloqueado_por_id) REFERENCES usuarios (id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_desbloqueos_motivo
        CHECK (CHAR_LENGTH(TRIM(motivo)) >= 5)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
