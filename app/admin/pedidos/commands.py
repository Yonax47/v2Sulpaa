"""Comandos operativos repetibles del módulo de pedidos."""

import click

from app.admin.pedidos.services import ejecutar_backfill_pedidos


def registrar_comandos_pedidos(app):
    """Registra el backfill controlado como comando Flask auditable."""

    @app.cli.command("backfill-pedido-historial")
    @click.option(
        "--apply",
        "aplicar",
        is_flag=True,
        help="Confirma que se desea escribir la regularización.",
    )
    def backfill_pedido_historial(aplicar):
        """Regulariza la evidencia base de pedidos históricos."""
        if not aplicar:
            raise click.ClickException(
                "Operación no ejecutada. Usa --apply después de revisar el contrato."
            )
        resultado = ejecutar_backfill_pedidos()
        click.echo(
            "Backfill correcto: "
            f"total={resultado['total_pedidos']}, "
            f"sin_historial_antes={resultado['sin_historial_antes']}, "
            f"insertados={resultado['insertados']}, "
            f"sin_historial_despues={resultado['sin_historial_despues']}."
        )
