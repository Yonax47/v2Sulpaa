"""Módulo administrativo del catálogo comercial de SULPAA V2.

Agrupa las pantallas y reglas para administrar productos, categorías,
sabores, presentaciones, variantes, precios, imágenes y packs.

La lógica se separa igual que en los demás módulos de la casa:

- ``routes.py`` atiende HTTP y muestra formularios.
- ``services.py`` aplica permisos, validaciones y auditoría.
- ``repositories.py`` habla con las tablas reales de Comercio.
- ``imagenes.py`` valida y guarda archivos en almacenamiento persistente.
- ``validaciones.py`` reúne reglas puras que se pueden probar sin MySQL.
"""
