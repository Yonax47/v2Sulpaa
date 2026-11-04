-- SOLO LECTURA. PREPARADO, NO EJECUTADO. No contiene DDL/DML ni USE.
-- Conectar mediante un cliente autorizado al esquema de IDENTIDAD.
-- Los cuatro nombres de esquema de la sección multiesquema son MARCADORES:
-- reemplazar localmente por los nombres comprobados del destino autorizado.
-- No publicar resultados que permitan identificar clientes.

SELECT DATABASE() AS esquema_actual, VERSION() AS version_servidor,
       @@session.time_zone AS zona_sesion, @@global.time_zone AS zona_global,
       @@session.tx_isolation AS aislamiento, @@session.autocommit AS autocommit;

-- Conteos sin exponer el DNI, nombres, UUID o correo de los clientes.
SELECT COUNT(*) AS grupos_dni_duplicados,
       COALESCE(SUM(repeticiones - 1), 0) AS perfiles_excedentes
FROM (
    SELECT COUNT(*) AS repeticiones
    FROM perfiles
    WHERE dni IS NOT NULL AND dni <> ''
    GROUP BY dni
    HAVING COUNT(*) > 1
) AS duplicados;

SELECT COUNT(*) AS total_perfiles,
       COALESCE(SUM(dni IS NULL), 0) AS sin_dni,
       COALESCE(SUM(dni = ''), 0) AS dni_vacios,
       COALESCE(SUM(dni IS NOT NULL AND dni NOT REGEXP '^[0-9]{8}$'), 0)
           AS dni_malformados
FROM perfiles;

-- 003: verificar índice entero sobre dni, unicidad y posibles colisiones.
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX,
       COLUMN_NAME, SUB_PART, INDEX_TYPE
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('perfiles', 'usuarios', 'roles', 'usuario_roles',
                     'limites_consulta_externa', 'tokens_verificacion',
                     'correos_outbox', 'limites_correo')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- 004: exactamente una fila ACTIVA es el postcheck esperado.
SELECT codigo, estado, COUNT(*) AS cantidad
FROM roles WHERE codigo = 'CLIENTE' GROUP BY codigo, estado;

-- 005/006: ausencia antes de aplicar es normal; presencia exige comparar DDL.
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('usuarios', 'perfiles', 'roles', 'usuario_roles',
                     'limites_consulta_externa', 'tokens_verificacion',
                     'correos_outbox', 'limites_correo')
ORDER BY TABLE_NAME;

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
       CHARACTER_SET_NAME, COLLATION_NAME, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('usuarios', 'perfiles', 'roles', 'usuario_roles',
                     'limites_consulta_externa', 'tokens_verificacion',
                     'correos_outbox', 'limites_correo')
ORDER BY TABLE_NAME, ORDINAL_POSITION;

-- 006 FK local: tipo/charset/collation de usuarios.id debe coincidir con
-- tokens_verificacion.usuario_id: CHAR(36), utf8mb4, utf8mb4_unicode_ci.
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND ((TABLE_NAME = 'usuarios' AND COLUMN_NAME = 'id')
    OR (TABLE_NAME = 'tokens_verificacion' AND COLUMN_NAME = 'usuario_id'));

SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;

SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME,
       REFERENCED_TABLE_SCHEMA, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;

-- Compatibilidad multiesquema: sustituir TODOS los marcadores antes de usar.
-- Verificar tablas afectadas; todas deben ser InnoDB en el MISMO servidor.
SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA IN (
    '<IDENTIDAD>', '<COMERCIO>', '<INVENTARIO>', '<OPERACIONES>'
)
ORDER BY TABLE_SCHEMA, TABLE_NAME;

-- Inventario completo de columnas para contrastar repositorios antes/después.
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA IN (
    '<IDENTIDAD>', '<COMERCIO>', '<INVENTARIO>', '<OPERACIONES>'
)
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;

-- Capacidad: max_connections del servidor no equivale al cupo Alwaysdata.
-- Comprobar el cupo contractual por usuario con el administrador del servicio.
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_user_connections';
SHOW SESSION VARIABLES LIKE 'max_user_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
-- Metadatos de permisos de tablas sin mostrar material de autenticación.
SELECT TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE
FROM information_schema.TABLE_PRIVILEGES
WHERE TABLE_SCHEMA IN (
    '<IDENTIDAD>', '<COMERCIO>', '<INVENTARIO>', '<OPERACIONES>'
)
ORDER BY TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE;
-- Un administrador autorizado debe confirmar también privilegios a nivel de
-- esquema; ausencia aquí no demuestra falta de permisos heredados/globales.

-- Consultas POST 006 solamente (no ejecutar si las estructuras no existen).
-- SELECT requiere_verificacion_correo, correo_verificado, COUNT(*) AS cantidad
-- FROM usuarios GROUP BY requiere_verificacion_correo, correo_verificado;
-- SELECT estado, COUNT(*) AS cantidad, MIN(creado_en) AS mas_antiguo,
--        MAX(intentos) AS max_intentos
-- FROM correos_outbox GROUP BY estado;
-- SELECT servicio, operacion, COUNT(*) AS contadores, MAX(intentos) AS max_intentos
-- FROM limites_consulta_externa GROUP BY servicio, operacion;
