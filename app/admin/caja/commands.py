"""Comandos CLI del módulo de Flujo de Caja (Bloque 4)."""

import click


def registrar_comandos_caja(app):
    """Registra los comandos `flask ...` relacionados con la caja."""
    from app.admin.caja.services import reconciliar_caja

    @app.cli.command("reconciliar-caja")
    def reconciliar_caja_cli():
        """Crea los ingresos de caja faltantes de pagos PAGADO (idempotente)."""
        generados = reconciliar_caja()
        click.echo(
            f"Reconciliación de caja correcta: "
            f"{generados} ingreso(s) generado(s)."
        )