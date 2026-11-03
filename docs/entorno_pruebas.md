# Entorno aislado de pruebas

## Estado y protección

Cuando `SULPAA_TESTING=1` o Flask tiene `TESTING=True`, la aplicación usa
exclusivamente variables `DB_*_TEST`. No existe respaldo hacia credenciales o
esquemas normales. Antes de conectar se comprueba:

- que no falte ningún valor ni permanezcan marcadores como `<servidor>`;
- que los cuatro esquemas tengan el prefijo autorizado y sean distintos;
- que ningún esquema coincida con un nombre productivo conocido;
- que host, usuario y contraseña TEST no reutilicen valores productivos;
- que cada conexión solicite uno de los cuatro esquemas autorizados.

Los comandos de preparación y ejecución requieren además confirmar de forma
exacta el host y el prefijo. Ningún comando aplica migraciones automáticamente.

## 1. Preparación local sin conexiones

1. Instalar `requirements.txt` en un entorno virtual.
2. Copiar `.env.test.example` como `.env.test`.
3. Reemplazar todos los marcadores con credenciales exclusivas de TEST.
4. Configurar una carpeta absoluta y no temporal para imágenes. En este equipo
   se preparó, sin habilitarla automáticamente:

```text
C:/Users/Acer/Documents/v2Sulpaa/instance/catalogo-media
```

5. Colocar los ocho SQL revisados descritos en
   `scripts/testing/sql/README.md`.
6. Ejecutar el diagnóstico local, que **no abre conexiones**:

```powershell
python scripts/testing/diagnose_test_environment.py
```

Un resultado con `[BLOQUEO]` significa que no se debe continuar.

## 2. Verificación remota de solo lectura

Después de que el diagnóstico local pase, comprobar tablas y columnas:

```powershell
python scripts/testing/verify_test_structure.py --confirmar-solo-lectura
```

Este comando solo ejecuta `SELECT DATABASE()`, `VERSION()` y consultas a
`information_schema` dentro de transacciones `READ ONLY`. No crea ni modifica
datos. Si un esquema no existe o no es compatible, termina con error.

## 3. Creación y carga de los esquemas

Esta etapa sí escribe y solo debe ejecutarse después de revisar el servidor.
La confirmación usa los valores reales de `.env.test`:

```powershell
python scripts/testing/prepare_test_databases.py `
  --confirmar-entorno-aislado `
  --confirmar-destino "TEST:<host-test>:<prefijo-test>"
```

El preparador rechaza SQL con administración de usuarios, bases, permisos,
`LOAD DATA`, `OUTFILE`, `DUMPFILE` o `USE`. También verifica el servidor y el
usuario efectivos antes del primer `CREATE DATABASE`.

Crear esquemas vacíos no es el flujo recomendado. Si fuera imprescindible,
requiere dos confirmaciones adicionales:

```powershell
python scripts/testing/prepare_test_databases.py `
  --solo-crear `
  --permitir-esquemas-vacios `
  --confirmar-entorno-aislado `
  --confirmar-destino "TEST:<host-test>:<prefijo-test>"
```

## 4. Suite aislada

La suite puede crear, actualizar o desactivar datos ficticios. Solo se inicia
cuando las cuatro conexiones, la estructura y la carpeta de imágenes pasan:

```powershell
python scripts/testing/run_isolated_tests.py `
  --confirmar-pruebas-con-escritura `
  --confirmar-destino "TEST:<host-test>:<prefijo-test>"
```

Antes de descubrir pruebas, el ejecutor confirma `SELECT DATABASE()` para cada
dominio y aplica el mismo contrato de `verify_test_structure.py`.

## 5. Datos mínimos esperados

- Un usuario ficticio con rol `GERENTE` o `ADMINISTRADOR` y contraseña creada
  específicamente para TEST.
- Categoría, sabor, presentación, producto, variante, artículo de venta, tipo
  de precio y precio vigente.
- Un pack fijo y uno personalizable con sus relaciones.
- Un almacén ficticio y existencias para las variantes de prueba.
- Tablas vacías válidas para carrito, favoritos, pedidos y auditoría.

No deben incluirse nombres, correos, direcciones, teléfonos, documentos,
contraseñas, tokens ni pedidos reales. Usa dominios como `example.test`.

## Pendientes actuales

Faltan `.env.test`, servidor y credenciales TEST, cuatro esquemas comprobables y
los ocho SQL sanitizados. La carpeta local de imágenes existe, pero aún debe
declararse en `.env.test`. Hasta completar estos puntos no se deben ejecutar
preparación, CRUD real ni checkout.

`migrations/002_identidad_seguridad_accesos.sql` no forma parte de esta fase y
no debe ejecutarse sin autorización explícita.
