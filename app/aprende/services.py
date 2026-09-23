"""
Reglas de negocio de la experiencia "Aprende" de SULPAA V2.

Orquesta las lecturas públicas del contenido educativo y la
evidencia de accesos del KPI-10:

- Solo expone contenido PUBLICADO.
- Un borrador (o un slug inexistente) responde como NO disponible
  y deja evidencia de acceso fallido (KPI-10).
- El registro de accesos es la única escritura que hace este
  módulo público; todo lo demás es solo lectura.
"""

from app.aprende.repositories import (
    listar_contenido_publicado,
    obtener_contenido_publicado,
    registrar_acceso,
)


def listar_publico():
    """Devuelve el contenido educativo PUBLICADO ordenado."""
    return listar_contenido_publicado()


def obtener_detalle_publico(slug, usuario_id=None):
    """
    Resuelve el detalle público de un contenido y registra el acceso.

    - Si el contenido existe y está PUBLICADO: resultado='EXITO'.
    - Si el slug no existe o es un borrador: resultado='FALLO'
      (la URL es legítima pero el recurso no es accesible).

    En ambos casos se conserva la evidencia para el KPI-10.
    """

    slug = str(slug or "").strip()

    contenido = obtener_contenido_publicado(slug)

    if not contenido:
        registrar_acceso(
            slug_solicitado=slug,
            contenido_id=None,
            usuario_id=usuario_id,
            resultado="FALLO",
        )
        return None

    registrar_acceso(
        slug_solicitado=slug,
        contenido_id=contenido["contenido_id"],
        usuario_id=usuario_id,
        resultado="EXITO",
    )

    return contenido