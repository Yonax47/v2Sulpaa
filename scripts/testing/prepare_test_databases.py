"""Crea y carga esquemas TEST después de comprobar que no son producción.

El script no contiene credenciales ni copia datos productivos. Para poblar los
esquemas necesita archivos SQL revisados y sanitizados en ``sql``. La opción de
confirmación evita que una ejecución accidental haga cambios en otro servidor.
"""

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv


RAIZ = Path(__file__).resolve().parents[2]
CARPETA_SQL = Path(__file__).resolve().parent / "sql"
DOMINIOS = ("identidad", "comercio", "inventario", "operaciones")

# Al ejecutar el archivo directamente, Python inicia en scripts/testing. Se
# agrega la raíz para importar la misma configuración central de la aplicación.
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def argumentos_linea_comandos():
    """Lee la ubicación del entorno y exige una confirmación explícita."""

    parser = argparse.ArgumentParser(
        description="Prepara las cuatro bases aisladas de SULPAA."
    )
    parser.add_argument(
        "--env",
        default=str(RAIZ / ".env.test"),
        help="Archivo con las variables DB_*_TEST.",
    )
    parser.add_argument(
        "--solo-crear",
        action="store_true",
        help="Crea esquemas vacíos sin ejecutar archivos SQL.",
    )
    parser.add_argument(
        "--permitir-esquemas-vacios",
        action="store_true",
        help="Confirmación adicional requerida junto con --solo-crear.",
    )
    parser.add_argument(
        "--confirmar-entorno-aislado",
        action="store_true",
        help="Confirma que el destino fue revisado y no es producción.",
    )
    parser.add_argument(
        "--confirmar-destino",
        help="Debe ser exactamente TEST:<host>:<prefijo>.",
    )
    return parser.parse_args()


def ejecutar_archivo(cursor, ruta):
    """Ejecuta todas las sentencias de un SQL mediante múltiples resultados."""

    contenido = ruta.read_text(encoding="utf-8").strip()
    if not contenido:
        return
    cursor.execute(contenido)
    # PyMySQL avanza por cada sentencia enviada con MULTI_STATEMENTS.
    while cursor.nextset():
        pass


def validar_contenido_sql(ruta):
    """Rechaza instrucciones que puedan escapar de los esquemas autorizados."""

    contenido = ruta.read_text(encoding="utf-8")
    # Los ejemplos o palabras dentro de comentarios no son instrucciones. Se
    # retiran antes del filtro para evitar rechazos falsos sin ejecutar nada.
    contenido_revisable = re.sub(r"/\*.*?\*/", "", contenido, flags=re.DOTALL)
    contenido_revisable = re.sub(r"--[^\r\n]*", "", contenido_revisable)
    contenido_revisable = re.sub(r"#[^\r\n]*", "", contenido_revisable)
    prohibidas = (
        r"\bDROP\s+DATABASE\b",
        r"\bCREATE\s+DATABASE\b",
        r"\bALTER\s+USER\b",
        r"\bCREATE\s+USER\b",
        r"\bDROP\s+USER\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
        r"\bLOAD\s+DATA\b",
        r"\bINTO\s+OUTFILE\b",
        r"\bINTO\s+DUMPFILE\b",
        r"\bUSE\s+[`\w]",
    )
    for patron in prohibidas:
        if re.search(patron, contenido_revisable, flags=re.IGNORECASE):
            raise RuntimeError(
                f"{ruta.name} contiene una instrucción no permitida: {patron}"
            )


def confirmacion_destino(configuracion):
    """Construye la frase exacta que debe confirmar quien ejecuta."""

    prefijo = str(os.environ["DB_TEST_SCHEMA_PREFIX"]).strip()
    return f"TEST:{configuracion['host']}:{prefijo}"


def main():
    """Valida todo antes de crear esquemas o cargar datos."""

    args = argumentos_linea_comandos()
    if not args.confirmar_entorno_aislado:
        raise SystemExit(
            "Cancelado: falta --confirmar-entorno-aislado."
        )

    archivo_entorno = Path(args.env)
    if not archivo_entorno.is_file():
        raise SystemExit(f"No existe el archivo de entorno: {archivo_entorno}")
    load_dotenv(archivo_entorno, override=True)
    os.environ["SULPAA_TESTING"] = "1"

    # Se importa después de cargar .env.test para no leer valores antiguos.
    from pymysql.constants import CLIENT
    from app.config.database import (
        pymysql,
        validar_configuracion_pruebas,
    )
    from scripts.testing.test_environment import (
        archivos_sql_requeridos,
        validar_credenciales_administrativas,
    )

    configuracion = validar_configuracion_pruebas()
    confirmacion_esperada = confirmacion_destino(configuracion)
    if args.confirmar_destino != confirmacion_esperada:
        raise SystemExit(
            "Cancelado: confirma el destino exacto con "
            f"--confirmar-destino {confirmacion_esperada}"
        )
    if args.solo_crear and not args.permitir_esquemas_vacios:
        raise SystemExit(
            "Cancelado: --solo-crear requiere --permitir-esquemas-vacios."
        )

    try:
        usuario_admin, password_admin = validar_credenciales_administrativas()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None

    sql = archivos_sql_requeridos(CARPETA_SQL)
    faltantes = [str(ruta) for ruta in sql if not ruta.is_file()]
    if faltantes and not args.solo_crear:
        raise SystemExit(
            "Faltan archivos SQL sanitizados:\n- " + "\n- ".join(faltantes)
        )
    if not args.solo_crear:
        try:
            for ruta in sql:
                validar_contenido_sql(ruta)
        except (OSError, UnicodeError, RuntimeError) as error:
            raise SystemExit(f"SQL rechazado antes de conectar: {error}") from None

    conexion = pymysql.connect(
        host=configuracion["host"],
        port=configuracion["port"],
        user=usuario_admin,
        password=password_admin,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        client_flag=CLIENT.MULTI_STATEMENTS,
    )
    try:
        with conexion.cursor() as cursor:
            # Esta lectura ocurre antes de cualquier DDL y deja evidencia del
            # servidor efectivo elegido por la configuración revisada.
            cursor.execute(
                "SELECT DATABASE() AS esquema, @@hostname AS servidor, "
                "CURRENT_USER() AS usuario"
            )
            destino = cursor.fetchone() or {}
            if destino.get("esquema") is not None:
                raise RuntimeError(
                    "La conexión administrativa inició dentro de un esquema; "
                    "se esperaba una conexión sin base seleccionada."
                )
            print(
                "Destino TEST verificado antes de escribir: "
                f"servidor={destino.get('servidor')}, "
                f"usuario={destino.get('usuario')}"
            )
            for esquema in configuracion["esquemas"].values():
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{esquema}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            if not args.solo_crear:
                for dominio in DOMINIOS:
                    cursor.execute(
                        f"USE `{configuracion['esquemas'][dominio]}`"
                    )
                    ejecutar_archivo(cursor, CARPETA_SQL / f"{dominio}.schema.sql")
                    ejecutar_archivo(cursor, CARPETA_SQL / f"{dominio}.data.sql")
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()

    print("Esquemas TEST preparados correctamente.")


if __name__ == "__main__":
    main()
