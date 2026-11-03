# SQL para las bases de pruebas

Esta carpeta debe recibir ocho archivos revisados:

- `identidad.schema.sql` y `identidad.data.sql`
- `comercio.schema.sql` y `comercio.data.sql`
- `inventario.schema.sql` y `inventario.data.sql`
- `operaciones.schema.sql` y `operaciones.data.sql`

## Contrato de los archivos

- `*.schema.sql`: estructura compatible con la aplicación, sin crear bases,
  usuarios ni permisos. El preparador selecciona el esquema autorizado.
- `*.data.sql`: únicamente datos ficticios o anonimizados de forma irreversible.
- Codificación UTF-8 y sentencias compatibles con MariaDB/MySQL del servidor
  TEST.
- No incluir `CREATE/DROP DATABASE`, `USE`, `CREATE/ALTER/DROP USER`, `GRANT`,
  `REVOKE`, `LOAD DATA`, `OUTFILE` ni `DUMPFILE`.
- No incluir referencias calificadas a esquemas productivos.

La estructura mínima comprobada automáticamente está declarada en `CONTRATO`
de `scripts/testing/verify_test_structure.py`. Incluye catálogo, roles,
auditoría, inventario, favoritos, carrito y pedidos.

## Sanitización obligatoria

No se permiten copias directas de producción. Eliminar o reemplazar antes de
guardar cualquier archivo:

- nombres, correos, teléfonos, documentos y direcciones reales;
- coordenadas o referencias de entrega reales;
- hashes de contraseñas productivas, tokens, cookies y secretos;
- números, comentarios o composiciones de pedidos identificables;
- rutas privadas de archivos y datos de facturación.

Los usuarios de ejemplo deben usar correos `@example.test` y contraseñas
generadas solo para TEST. Los UUID pueden ser nuevos o deterministas, siempre
que no permitan relacionar el conjunto con personas reales.

## Datos mínimos recomendados

1. Identidad: usuario administrativo ficticio, roles y relación activa.
2. Comercio: catálogos simples, producto, dos variantes, precios, imágenes con
   rutas ficticias, pack fijo y pack personalizable.
3. Inventario: almacén ficticio y existencias suficientes para una compra.
4. Operaciones: tabla de auditoría vacía y lista para recibir eventos.
5. Carrito/pedidos: tablas estructurales vacías; las pruebas crearán sus propios
   registros y deben limpiar únicamente los datos TEST que controlen.

El preparador comprueba los ocho archivos y su contenido antes de abrir la
conexión administrativa, salvo el modo explícito de esquemas vacíos.
