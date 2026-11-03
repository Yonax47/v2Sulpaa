"""Renderizado común de versiones HTML y texto plano."""

from flask import render_template


SUBJECTS = {
    "verificacion_correo": "Verifica tu correo en SULPAA",
    "pedido_confirmado": "Confirmación de tu compra en SULPAA",
}


def render_email(template_name, data):
    if template_name not in SUBJECTS:
        raise ValueError("Plantilla de correo no permitida.")
    base = f"emails/{template_name}"
    return {
        "subject": SUBJECTS[template_name],
        "html": render_template(base + ".html", **data),
        "text": render_template(base + ".txt", **data),
    }
