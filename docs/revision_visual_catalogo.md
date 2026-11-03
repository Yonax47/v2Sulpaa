# Revisión visual del catálogo en TEST

Esta guía se usa únicamente después de validar los cuatro esquemas con
`verify_test_structure.py`. Mantén `SULPAA_TESTING=1` durante toda la revisión.

## Preparación

1. Confirma que la URL local usa `.env.test` y no variables productivas.
2. Inicia sesión con un usuario ficticio `GERENTE` o `ADMINISTRADOR`.
3. Abre las herramientas del navegador y verifica que no haya errores de
   consola ni solicitudes hacia dominios productivos.
4. Conserva una variante con stock, otra sin stock y precios con vigencias
   distintas para revisar estados límite.

## Catálogo administrativo

- **Permisos:** un cliente normal recibe `403`; gerente y administrador acceden.
- **CSRF:** un POST sin token válido se rechaza y no cambia datos.
- **Categorías, sabores y presentaciones:** crear, editar, filtrar, desactivar y
  reactivar registros ficticios; comprobar mensajes y orden responsive.
- **Productos:** crear un producto, asociar categoría, editar descripción y
  confirmar que no se publica con relaciones inactivas.
- **Variantes:** crear SKU único, medidas y precio inicial; verificar rechazo de
  duplicados y mostrar stock solo lectura.
- **Precios:** agregar vigencia, rechazar superposición y cerrar una vigencia sin
  borrar el historial anterior.
- **Imágenes:** subir JPG/PNG/WEBP pequeño, revisar texto alternativo, principal,
  orden y respaldo estático; rechazar extensión o firma inválida.
- **Packs:** probar uno fijo y uno personalizable. Confirmar que el disponible
  se calcula desde variantes y que un pack usado en pedidos no permite cambiar
  su composición.
- **Auditoría:** revisar que cada cambio confirmado genere un evento con actor,
  entidad, acción y datos anteriores/nuevos, sin secretos.

## Integración del cliente

- **Tienda:** producto, sabor nuevo, precio, imagen administrada y estado de
  agotado coinciden con administración e inventario.
- **Ficha:** muestra SKU, presentación, precio, imagen y disponibilidad correctos.
- **Favoritos:** agregar y quitar solo para el usuario autenticado; una variante
  inactiva deja de exponerse.
- **Carrito:** agregar variante y packs, cambiar cantidades y comprobar totales.
- **Checkout:** con datos totalmente ficticios, crear un pedido y confirmar
  reserva de inventario, snapshot de precio/composición e historial.
- **Inventario:** el catálogo nunca cambia stock por sí mismo. Solo checkout y
  los flujos de inventario autorizados modifican reservas o existencias.

## Vistas y cierre

Repetir panel, listados y formularios a 360 px, 768 px y escritorio. Revisar
teclado, foco visible, etiquetas, texto alternativo, confirmaciones y mensajes.

Al terminar, registrar los identificadores TEST creados y limpiar solo mediante
un procedimiento aprobado para esos esquemas. No reutilizar esta revisión en
producción y no declarar la Fase 2 lista hasta completar todos los puntos.
