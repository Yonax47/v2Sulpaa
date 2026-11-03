"""Ejecuta la suite solo después de verificar las cuatro bases TEST."""

import argparse
import os
import sys
import unittest
from pathlib import Path

from dotenv import load_dotenv


RAIZ = Path(__file__).resolve().parents[2]

# Permite importar ``app`` aunque el ejecutor se invoque por su ruta completa.
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def main():
    """Carga .env.test, comprueba conexiones y recién entonces inicia tests."""

    parser = argparse.ArgumentParser(
        description="Ejecuta todas las pruebas contra bases aisladas."
    )
    parser.add_argument(
        "--env",
        default=str(RAIZ / ".env.test"),
        help="Archivo con las variables DB_*_TEST.",
    )
    parser.add_argument("--verbosity", type=int, default=2)
    parser.add_argument(
        "--confirmar-pruebas-con-escritura",
        action="store_true",
        help="Confirma que la suite puede modificar únicamente datos TEST.",
    )
    parser.add_argument(
        "--confirmar-destino",
        help="Debe ser exactamente TEST:<host>:<prefijo>.",
    )
    args = parser.parse_args()
    if not args.confirmar_pruebas_con_escritura:
        raise SystemExit(
            "Cancelado: falta --confirmar-pruebas-con-escritura."
        )

    archivo_entorno = Path(args.env)
    if not archivo_entorno.is_file():
        raise SystemExit(f"No existe el archivo de entorno: {archivo_entorno}")
    load_dotenv(archivo_entorno, override=True)
    os.environ["SULPAA_TESTING"] = "1"

    from app.config.database import (
        crear_conexion,
        validar_configuracion_pruebas,
    )

    configuracion = validar_configuracion_pruebas()
    confirmacion_esperada = (
        f"TEST:{configuracion['host']}:"
        f"{os.environ['DB_TEST_SCHEMA_PREFIX'].strip()}"
    )
    if args.confirmar_destino != confirmacion_esperada:
        raise SystemExit(
            "Cancelado: confirma el destino exacto con "
            f"--confirmar-destino {confirmacion_esperada}"
        )

    from scripts.testing.test_environment import revisar_directorio_imagenes
    imagenes_ok, detalle_imagenes = revisar_directorio_imagenes(
        os.getenv("CATALOGO_IMAGENES_DIR")
    )
    if not imagenes_ok:
        raise SystemExit(f"Almacenamiento de imágenes inválido: {detalle_imagenes}")

    # Cada conexión se abre antes de descubrir la suite. Si un esquema falta,
    # las pruebas no comienzan y ninguna operación de escritura puede ocurrir.
    for dominio, esquema in configuracion["esquemas"].items():
        conexion = crear_conexion(esquema, reutilizar=False)
        try:
            with conexion.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS esquema")
                fila = cursor.fetchone()
            if not fila or fila.get("esquema") != esquema:
                raise RuntimeError(
                    f"La conexión de {dominio} no usa el esquema TEST esperado."
                )
        finally:
            conexion.close()

    # El verificador solo consulta information_schema dentro de transacciones
    # de lectura. La suite no comienza si falta una tabla o columna esencial.
    from scripts.testing.verify_test_structure import verificar
    estructura = verificar(configuracion, crear_conexion)
    incompatibilidades = [
        f"{item['dominio']}: {error}"
        for item in estructura
        for error in item["errores"]
    ]
    if incompatibilidades:
        raise SystemExit(
            "La estructura TEST no es compatible:\n- "
            + "\n- ".join(incompatibilidades)
        )

    # ``tests`` no es un paquete Python; se descubre como carpeta para
    # conservar el mismo comportamiento de ``unittest discover`` del proyecto.
    suite = unittest.defaultTestLoader.discover(str(RAIZ / "tests"))
    resultado = unittest.TextTestRunner(verbosity=args.verbosity).run(suite)
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
