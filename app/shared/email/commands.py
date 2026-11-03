"""Comando manual/cron para procesar el outbox."""

import click

from app.shared.email.outbox import procesar_outbox


def registrar_comandos_email(app):
    @app.cli.command("procesar-correos")
    @click.option("--limite", default=10, type=click.IntRange(1, 50))
    def procesar_correos(limite):
        """Procesa un lote; nunca se invoca al arrancar el servidor web."""

        resumen = procesar_outbox(limite=limite)
        if resumen.get("deshabilitado"):
            click.echo("Correo deshabilitado: no se reclamaron eventos.")
            return
        click.echo(
            "Reclamados: {reclamados}; enviados: {enviados}; "
            "fallidos/reintento: {fallidos}".format(**resumen)
        )
