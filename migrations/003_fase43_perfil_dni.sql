-- ============================================================
-- MIGRACIÓN 003 — FASE 4.3: UNICIDAD DE DNI EN PERFILES
-- Esquema objetivo: base1sulpaa_identidad
-- Estado: PENDIENTE DE AUTORIZACIÓN. NO EJECUTAR EN PRODUCCIÓN.
-- ============================================================
--
-- Motivo:
-- La aplicación ya comprueba duplicados antes de registrar, pero dos
-- solicitudes simultáneas podrían superar esa comprobación. Un índice único
-- en perfiles.dni convierte la regla de negocio en una garantía de la base.
--
-- Esta migración NO se ha ejecutado. Antes de aplicarla se debe:
--   1. confirmar que el esquema autorizado es el correcto;
--   2. revisar que no existan DNI duplicados;
--   3. decidir, con autorización expresa, qué hacer con los duplicados
--      históricos (no se borran datos automáticamente);
--   4. ejecutarla en una ventana controlada y verificar el resultado.
--
-- Compatibilidad con migraciones anteriores:
--   - 001 actúa sobre encuestas/caja/reportes y no altera perfiles;
--   - 002 crea controles de acceso y tampoco altera perfiles;
--   - esta migración no depende de 002 y solo requiere la tabla perfiles.
--
-- MariaDB permite varios NULL en un índice UNIQUE. Se conservan así los
-- perfiles históricos que aún no tengan DNI. Las cuentas creadas por el flujo
-- nuevo siempre exigen ocho dígitos. Las cadenas vacías o valores malformados
-- deben revisarse antes de crear el índice y NO se corrigen automáticamente.
--
-- Seleccionar de forma explícita el esquema autorizado antes de ejecutar:
-- USE base1sulpaa_identidad;

-- ------------------------------------------------------------
-- 1. PRECHECK OBLIGATORIO: DNI duplicados
-- ------------------------------------------------------------
-- Si esta consulta devuelve filas, DETENERSE. El índice fallaría y, más
-- importante, existirían cuentas distintas con el mismo documento.
SELECT
    dni,
    COUNT(*) AS repeticiones
FROM perfiles
WHERE dni IS NOT NULL
  AND dni <> ''
GROUP BY dni
HAVING COUNT(*) > 1;

-- ------------------------------------------------------------
-- 2. PRECHECK: cadenas vacías que deberían ser NULL
-- ------------------------------------------------------------
-- El índice único permite varios NULL, pero solo una cadena ''. Aunque hubiera
-- una sola, el dato seguiría siendo inválido: cualquier resultado mayor a cero
-- exige revisión autorizada. No se incluye un UPDATE automático.
SELECT
    COUNT(*) AS dni_vacios
FROM perfiles
WHERE dni = '';

-- ------------------------------------------------------------
-- 2.b PRECHECK: DNI históricos con formato distinto de 8 dígitos
-- ------------------------------------------------------------
SELECT
    id,
    usuario_id,
    dni
FROM perfiles
WHERE dni IS NOT NULL
  AND (dni NOT REGEXP '^[0-9]{8}$');

-- ------------------------------------------------------------
-- 3. PRECHECK: comprobar índices existentes y colisiones de nombre
-- ------------------------------------------------------------
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'perfiles'
  AND COLUMN_NAME = 'dni';

SELECT
    INDEX_NAME,
    NON_UNIQUE
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'perfiles'
  AND COLUMN_NAME = 'dni';

SELECT
    INDEX_NAME,
    NON_UNIQUE,
    COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'perfiles'
  AND INDEX_NAME = 'uq_perfiles_dni';

-- ------------------------------------------------------------
-- 4. CREAR EL ÍNDICE ÚNICO
-- ------------------------------------------------------------
-- Ejecutar SOLO si 1, 2 y 2.b no devolvieron conflictos y el paso 3 confirmó
-- que no existe ya una restricción equivalente ni una colisión de nombre.
ALTER TABLE perfiles
    ADD UNIQUE INDEX uq_perfiles_dni (dni);

-- ------------------------------------------------------------
-- 5. VERIFICACIÓN POSTERIOR
-- ------------------------------------------------------------
SHOW INDEX FROM perfiles
WHERE Column_name = 'dni';

-- ------------------------------------------------------------
-- NOTA SOBRE REVERSIÓN
-- ------------------------------------------------------------
-- Si fuera necesario revertir (solo con autorización):
-- ALTER TABLE perfiles DROP INDEX uq_perfiles_dni;
