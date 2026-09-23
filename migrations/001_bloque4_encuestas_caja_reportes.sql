-- ============================================================
-- MIGRACIÓN BLOQUE 4 — SULPAA V2
-- Reportes Gerenciales + Encuestas + Flujo de Caja
-- Base de datos: v2sulpaa_operaciones_db
-- Motor objetivo: MariaDB 10.4
--
-- Este script es REPRODUCIBLE: contiene únicamente DDL y
-- semilla de CATÁLOGO (sin montos, sin datos operativos,
-- sin secretos). Autorizado el 2026-09-23.
-- ============================================================

USE v2sulpaa_operaciones_db;

-- ============================================================
-- 1. caja_categorias
-- Catálogo de categorías de flujo de caja (no son datos
-- financieros: solo clasifican ingresos/egresos).
-- ============================================================

CREATE TABLE IF NOT EXISTS caja_categorias (
    id                SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    codigo            VARCHAR(40)  NOT NULL,
    nombre            VARCHAR(80)  NOT NULL,
    tipo              ENUM('INGRESO','EGRESO') NOT NULL,
    estado            ENUM('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO',
    creado_en         DATETIME NOT NULL DEFAULT current_timestamp(),
    actualizado_en    DATETIME NOT NULL DEFAULT current_timestamp()
                      ON UPDATE current_timestamp(),
    PRIMARY KEY (id),
    UNIQUE KEY uq_caja_categorias_codigo (codigo)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- Semilla de catálogo: SOLO categorías, NUNCA montos.
INSERT IGNORE INTO caja_categorias (codigo, nombre, tipo) VALUES
    ('COBRO_PEDIDO',   'Cobro de pedido',        'INGRESO'),
    ('OTROS_INGRESOS', 'Otros ingresos',         'INGRESO'),
    ('INSUMOS',        'Compra de insumos',      'EGRESO'),
    ('TRANSPORTE',     'Transporte',             'EGRESO'),
    ('SERVICIOS',      'Servicios',              'EGRESO'),
    ('MANTENIMIENTO',  'Mantenimiento',          'EGRESO'),
    ('OTROS_GASTOS',   'Otros gastos',           'EGRESO');

-- ============================================================
-- 2. caja_movimientos
-- Fuente única de ingresos y egresos.
--
-- IDEMPOTENCIA FINANCIERA:
--   Ingreso automático UNIQUE por pago_id => un pago PAGADO
--   genera COMO MÁXIMO un movimiento (refresh/retry/doble
--   POST no pueden duplicar ingresos).
--
-- REGLA DE INGRESO (autorizada):
--   origen='PAGO' solo para pagos con estado='PAGADO'
--   AND pagado_en IS NOT NULL. Un pedido creado/confirmado/
--   completado NUNCA equivale automáticamente a ingreso.
--
-- EVIDENCIA FINANCIERA:
--   estado ACTIVO -> ANULADO (anulación trazable con motivo
--   y actor). Nunca DELETE destructivo.
--
-- ACTOR:
--   usuario_registra_id puede ser NULL únicamente cuando
--   origen='PAGO' y el registro es automático (no existe
--   actor humano confiable). En origen='MANUAL' es
--   OBLIGATORIO (CHECK + validación en Service).
-- ============================================================

CREATE TABLE IF NOT EXISTS caja_movimientos (
    id                       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    categoria_id             SMALLINT UNSIGNED NOT NULL,
    tipo                     ENUM('INGRESO','EGRESO') NOT NULL,
    origen                   ENUM('PAGO','MANUAL') NOT NULL,
    concepto                 VARCHAR(200) NOT NULL,
    monto                    DECIMAL(12,2) NOT NULL,
    moneda                   CHAR(3)      NOT NULL DEFAULT 'PEN',
    metodo_pago_id           SMALLINT UNSIGNED NULL,
    pago_id                  CHAR(36)     NULL,
    pedido_id                CHAR(36)     NULL,
    fecha_movimiento         DATETIME     NOT NULL,
    estado                   ENUM('ACTIVO','ANULADO') NOT NULL DEFAULT 'ACTIVO',
    anulado_en               DATETIME     NULL,
    anulado_motivo           VARCHAR(200) NULL,
    anulado_por_usuario_id   CHAR(36)     NULL,
    usuario_registra_id      CHAR(36)     NULL,
    creado_en                DATETIME NOT NULL DEFAULT current_timestamp(),
    PRIMARY KEY (id),
    -- IDEMPOTENCIA: un pago -> máximo un ingreso de caja.
    UNIQUE KEY uq_caja_movimientos_pago (pago_id),
    KEY idx_caja_movimientos_fecha (fecha_movimiento),
    KEY idx_caja_movimientos_tipo_estado (tipo, estado, fecha_movimiento),
    KEY idx_caja_movimientos_categoria (categoria_id),
    KEY idx_caja_movimientos_pedido (pedido_id),
    CONSTRAINT fk_caja_movimientos_categoria
        FOREIGN KEY (categoria_id) REFERENCES caja_categorias (id)
        ON UPDATE CASCADE,
    CONSTRAINT fk_caja_movimientos_metodo
        FOREIGN KEY (metodo_pago_id) REFERENCES metodos_pago (id)
        ON UPDATE CASCADE,
    CONSTRAINT fk_caja_movimientos_pago
        FOREIGN KEY (pago_id) REFERENCES pagos (id)
        ON UPDATE CASCADE,
    CONSTRAINT chk_caja_movimientos_monto
        CHECK (monto > 0),
    -- Un movimiento con origen PAGO siempre es un INGRESO.
    CONSTRAINT chk_caja_movimientos_origen
        CHECK (origen = 'PAGO' AND tipo = 'INGRESO'
               OR origen = 'MANUAL'),
    -- En origen MANUAL debe existir un actor responsable.
    CONSTRAINT chk_caja_movimientos_actor
        CHECK (origen = 'PAGO' OR usuario_registra_id IS NOT NULL)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 3. encuestas
-- Una encuesta por pedido entregado (IDEMPOTENCIA por
-- UNIQUE(pedido_id): refresh/retry no duplican encuestas).
--
-- SEGURIDAD DEL TOKEN:
--   token_hash  = SHA-256(hex) del token aleatorio (CSPRNG).
--   token_cifrado = token cifrado con Fernet (patrón
--     codigos_cliente del proyecto) para que la aplicación
--     pueda reconstruir el enlace público sin persistir el
--     token en texto plano. NUNCA se guarda token plano en
--     BD, logs o auditoría.
--
-- CANAL (metodología KPI-09 autorizada):
--   PORTAL = invitación electrónica puesta a disposición del
--   cliente dentro del sistema SULPAA (no implica correo).
--   CORREO queda reservado para cuando exista SMTP real.
-- ============================================================

CREATE TABLE IF NOT EXISTS encuestas (
    id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    pedido_id      CHAR(36) NOT NULL,
    entrega_id     CHAR(36) NOT NULL,
    usuario_id     CHAR(36) NOT NULL,
    estado         ENUM('PENDIENTE','ENVIADA','RESPONDIDA','ERROR_ENVIO')
                   NOT NULL DEFAULT 'PENDIENTE',
    canal          ENUM('PORTAL','CORREO') NOT NULL DEFAULT 'PORTAL',
    token_hash     CHAR(64)   NOT NULL,
    token_cifrado  VARCHAR(255) NOT NULL,
    enviado_en     DATETIME   NULL,
    respondido_en  DATETIME   NULL,
    creado_en      DATETIME NOT NULL DEFAULT current_timestamp(),
    actualizado_en DATETIME NOT NULL DEFAULT current_timestamp()
                   ON UPDATE current_timestamp(),
    PRIMARY KEY (id),
    UNIQUE KEY uq_encuestas_pedido (pedido_id),
    UNIQUE KEY uq_encuestas_entrega (entrega_id),
    UNIQUE KEY uq_encuestas_token_hash (token_hash),
    KEY idx_encuestas_estado (estado, creado_en),
    -- ON DELETE RESTRICT: la evidencia de satisfacción no se
    -- destruye junto con la entrega en el flujo operativo.
    CONSTRAINT fk_encuestas_entrega
        FOREIGN KEY (entrega_id) REFERENCES entregas (id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 4. encuesta_respuestas
-- 1:1 con encuesta (UNIQUE encuesta_id => imposible doble
-- respuesta a nivel de constraint, no solo de UI).
-- ============================================================

CREATE TABLE IF NOT EXISTS encuesta_respuestas (
    id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    encuesta_id          BIGINT UNSIGNED NOT NULL,
    calificacion_general TINYINT UNSIGNED NOT NULL,
    calificacion_producto TINYINT UNSIGNED NOT NULL,
    calificacion_entrega TINYINT UNSIGNED NOT NULL,
    calificacion_atencion TINYINT UNSIGNED NOT NULL,
    recomendaria         ENUM('SI','NO') NOT NULL,
    comentario           VARCHAR(500) NULL,
    creado_en            DATETIME NOT NULL DEFAULT current_timestamp(),
    PRIMARY KEY (id),
    UNIQUE KEY uq_encuesta_respuesta_encuesta (encuesta_id),
    CONSTRAINT fk_encuesta_respuesta_encuesta
        FOREIGN KEY (encuesta_id) REFERENCES encuestas (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_resp_general CHECK (calificacion_general BETWEEN 1 AND 5),
    CONSTRAINT chk_resp_producto CHECK (calificacion_producto BETWEEN 1 AND 5),
    CONSTRAINT chk_resp_entrega CHECK (calificacion_entrega BETWEEN 1 AND 5),
    CONSTRAINT chk_resp_atencion CHECK (calificacion_atencion BETWEEN 1 AND 5)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 5. encuesta_eventos
-- Evidencia auditable del mecanismo de invitación.
-- Numerador KPI-09 = pedidos entregados con >= 1
-- evento INVITACION_OK (COUNT DISTINCT: sin doble conteo).
-- ============================================================

CREATE TABLE IF NOT EXISTS encuesta_eventos (
    id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    encuesta_id             BIGINT UNSIGNED NOT NULL,
    tipo                    ENUM('CREADA','INVITACION_OK','INVITACION_FALLA',
                                 'REINTENTO','RESPONDIDA') NOT NULL,
    detalle                 VARCHAR(200) NULL,
    usuario_responsable_id  CHAR(36) NULL,
    creado_en               DATETIME NOT NULL DEFAULT current_timestamp(),
    PRIMARY KEY (id),
    KEY idx_encuesta_eventos_encuesta (encuesta_id, creado_en),
    CONSTRAINT fk_encuesta_eventos_encuesta
        FOREIGN KEY (encuesta_id) REFERENCES encuestas (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 6. reportes_solicitudes
-- Auditoría KPI-05: solo cuenta una SOLICITUD REAL de
-- generación/exportación (visitar la página NO cuenta).
--   KPI-05 = EXITO / solicitudes x 100, meta >= 95%.
-- ============================================================

CREATE TABLE IF NOT EXISTS reportes_solicitudes (
    id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tipo_reporte           VARCHAR(40) NOT NULL,
    formato                ENUM('PDF','XLSX','CSV') NOT NULL,
    parametros             VARCHAR(500) NULL,
    usuario_solicitante_id CHAR(36) NOT NULL,
    resultado              ENUM('EXITO','FALLO') NOT NULL,
    error_tecnico          VARCHAR(300) NULL,
    creado_en              DATETIME NOT NULL DEFAULT current_timestamp(),
    PRIMARY KEY (id),
    KEY idx_reportes_solicitudes_tipo (tipo_reporte, creado_en),
    KEY idx_reportes_solicitudes_resultado (resultado, creado_en)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
