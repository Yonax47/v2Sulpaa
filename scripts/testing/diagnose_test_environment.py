"""Diagnostica la preparación de TEST sin conectarse ni escribir.

La salida distingue bloqueos de avisos. El comando nunca abre MySQL y tampoco
crea carpetas; sirve como primer paso seguro antes de cualquier preparación.
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


RAIZ = Path(__file__).resolve().parents[2]
CARPETA_SQL = Path(__file__).resolve().parent / "sql"
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts.testing.test_environment import (  # noqa: E402
    archivos_sql_requeridos,
    revisar_directorio_imagenes,
    validar_credenciales_administrativas,
    variables_incompletas,
)


def diagnosticar(ruta_entorno):
    """Ejecuta comprobaciones locales y devuelve mensajes y estado final."""

    mensajes = []
    ruta_entorno = Path(ruta_entorno)
    if not ruta_entorno.is_file():
        mensajes.append(("BLOQUEO", f"No existe {ruta_entorno}."))
    else:
        load_dotenv(ruta_entorno, override=True)
        os.environ["SULPAA_TESTING"] = "1"

        incompletas = variables_incompletas()
        if incompletas:
            mensajes.append((
                "BLOQUEO",
                "Variables ausentes o con marcador: " + ", ".join(incompletas),
            ))
        else:
            try:
                from app.config.database import validar_configuracion_pruebas
                configuracion = validar_configuracion_pruebas()
                destinos = ", ".join(
                    f"{dominio}={esquema}"
                    for dominio, esquema in configuracion["esquemas"].items()
                )
                mensajes.append(("OK", f"Configuración aislada válida: {destinos}."))
            except RuntimeError as error:
                mensajes.append(("BLOQUEO", str(error)))

        try:
            validar_credenciales_administrativas()
            mensajes.append(("OK", "Credenciales administrativas TEST separadas."))
        except RuntimeError as error:
            mensajes.append(("BLOQUEO", str(error)))

    faltantes = [
        ruta.name for ruta in archivos_sql_requeridos(CARPETA_SQL)
        if not ruta.is_file()
    ]
    if faltantes:
        mensajes.append((
            "BLOQUEO",
            "Faltan SQL revisados y sanitizados: " + ", ".join(faltantes),
        ))
    else:
        mensajes.append(("OK", "Están presentes los ocho archivos SQL."))

    imagenes_ok, detalle_imagenes = revisar_directorio_imagenes(
        os.getenv("CATALOGO_IMAGENES_DIR")
    )
    mensajes.append(("OK" if imagenes_ok else "BLOQUEO", detalle_imagenes))

    correcto = not any(nivel == "BLOQUEO" for nivel, _ in mensajes)
    return mensajes, correcto


def main():
    """Muestra el diagnóstico local y finaliza sin abrir conexiones."""

    parser = argparse.ArgumentParser(
        description="Revisa TEST localmente sin conectarse a MySQL."
    )
    parser.add_argument("--env", default=str(RAIZ / ".env.test"))
    args = parser.parse_args()

    mensajes, correcto = diagnosticar(args.env)
    print("Diagnóstico local de TEST (sin conexiones):")
    for nivel, mensaje in mensajes:
        print(f"[{nivel}] {mensaje}")
    if not correcto:
        print("Resultado: entorno incompleto; no ejecutar escrituras.")
        return 1
    print("Resultado: prevalidación local correcta. Falta verificar el servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
