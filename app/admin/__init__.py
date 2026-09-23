"""
M\u00f3dulo Administrativo de SULPAA V2.

Este paquete contiene el panel administrativo del sistema.

Estructura (misma arquitectura que los dem\u00e1s m\u00f3dulos):

- routes.py       -> rutas (blueprint `admin_bp`).
- services.py     -> l\u00f3gica de negocio (calcula los KPI).
- repositories.py -> acceso a datos (SELECT sobre la BD real).

El Blueprint `admin_bp` vive en app/admin/routes.py
(igual que identidad/comercio/operaciones): este archivo
s\u00f3lo documenta el paquete.
"""
