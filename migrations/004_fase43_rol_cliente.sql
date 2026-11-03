-- ============================================================
-- MIGRACIÓN 004 — ROL CLIENTE PARA AUTORREGISTRO
-- Esquema objetivo: base1sulpaa_identidad
-- Estado: PENDIENTE DE AUTORIZACIÓN. NO EJECUTAR EN PRODUCCIÓN.
-- ============================================================
--
-- El nuevo autorregistro inserta usuario + perfil + vínculo CLIENTE en una
-- sola transacción. Si este rol no existe y está ACTIVO, la aplicación revierte
-- todo el alta para no dejar cuentas incompletas.
--
-- Esta migración NO modifica vínculos ni roles de cuentas existentes. Tampoco
-- reactiva automáticamente un CLIENTE inactivo: ese caso requiere revisión y
-- autorización explícitas.

-- USE base1sulpaa_identidad;

-- 1. PRECHECK: revisar cualquier fila previa, activa o inactiva.
SELECT id, codigo, nombre, descripcion, estado
FROM roles
WHERE codigo = 'CLIENTE';

-- 2. Ejecutar SOLO si el precheck no devolvió ninguna fila.
-- Si devolvió una fila INACTIVA, DETENERSE y decidir su reactivación de forma
-- explícita; no crear un código duplicado.
INSERT INTO roles (id, codigo, nombre, descripcion, estado)
SELECT
    UUID(),
    'CLIENTE',
    'Cliente',
    'Cuenta de cliente creada mediante autorregistro.',
    'ACTIVO'
WHERE NOT EXISTS (
    SELECT 1 FROM roles WHERE codigo = 'CLIENTE'
);

-- 3. VERIFICACIÓN POSTERIOR: debe devolver exactamente una fila ACTIVA.
SELECT id, codigo, nombre, descripcion, estado
FROM roles
WHERE codigo = 'CLIENTE';

-- No se incluye reversión automática: una vez asignado a usuarios, eliminar o
-- desactivar el rol requeriría revisar primero todos sus vínculos históricos.
