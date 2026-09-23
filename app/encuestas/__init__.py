"""
Dominio de Encuestas de Satisfacción de SULPAA V2.

Crea, publica y resuelve la encuesta única por pedido entregado.

Estructura (misma arquitectura de la casa):

- codigos.py       -> token seguro (hash + Fernet).
- repositories.py  -> acceso a datos (tablas del Bloque 4).
- services.py      -> reglas de negocio.
- routes.py        -> portal público del cliente (blueprint `encuesta_bp`).

Convenciones (patrón de la casa):

- El SQL califica SIEMPRE los esquemas con variables validadas
  (``esquemas_sulpaa()``), nunca con texto recibido desde HTTP.
- El token de la encuesta nunca viaja en texto plano: solo su hash
  (búsqueda) y su forma cifrada (reconstrucción del enlace).
- El KPI-09 no se falsea: la invitación electrónica solo cuenta como
  ``INVITACION_OK`` cuando el flujo de publicación realmente habilita el
  enlace (el cliente abrió la pantalla del pedido), no al crear la fila.
"""

# ============================================================
# Import del blueprint al importar el paquete (patrón de la casa,
# idéntico a app/admin/inventario/__init__.py).
# ============================================================

from app.encuestas.routes import encuesta_bp  # noqa: F401