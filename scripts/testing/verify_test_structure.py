"""Comprueba en solo lectura la estructura mínima de los cuatro esquemas TEST.

El comando consulta ``SELECT DATABASE()``, la versión e ``information_schema``.
No ejecuta DDL ni DML. Cada conexión inicia una transacción de solo lectura y
se revierte antes de cerrarse.
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


# El contrato incluye las columnas usadas por Catálogo y por sus integraciones
# directas. No intenta reproducir un dump completo de producción.
CONTRATO = {
    "identidad": {
        "usuarios": {"id", "correo", "password_hash", "estado"},
        "roles": {"id", "codigo", "estado"},
        "usuario_roles": {"usuario_id", "rol_id", "estado"},
        "perfiles": {"usuario_id"},
    },
    "comercio": {
        "categorias": {"id", "nombre", "slug", "descripcion", "orden", "estado"},
        "sabores": {"id", "nombre", "descripcion", "estado"},
        "presentaciones": {"id", "nombre", "tipo_unidad", "cantidad", "estado"},
        "productos": {"id", "categoria_id", "nombre", "slug", "descripcion", "estado"},
        "variantes": {
            "id", "producto_id", "sabor_id", "presentacion_id", "sku",
            "nombre_comercial", "peso_gramos", "estado",
        },
        "articulos_venta": {"id", "tipo", "variante_id", "pack_id", "estado"},
        "tipos_precio": {"id", "codigo", "nombre", "estado"},
        "precios": {
            "id", "articulo_venta_id", "tipo_precio_id", "monto", "moneda",
            "vigente_desde", "vigente_hasta", "estado",
        },
        "imagenes_catalogo": {
            "id", "producto_id", "variante_id", "ruta", "texto_alternativo",
            "es_principal", "orden", "estado",
        },
        "packs": {"id", "nombre", "slug", "tipo", "cantidad_unidades", "estado"},
        "pack_componentes": {"id", "pack_id", "variante_id", "cantidad"},
        "pack_reglas": {
            "id", "pack_id", "numero_sabores", "unidades_por_sabor", "estado",
        },
        "pack_variantes_permitidas": {"id", "pack_id", "variante_id", "estado"},
        "favoritos": {"id", "usuario_id", "variante_id"},
        "carritos": {"id", "usuario_id", "estado"},
        "carrito_detalles": {"id", "carrito_id", "articulo_venta_id", "cantidad"},
        "carrito_composiciones": {"carrito_detalle_id", "variante_id", "cantidad"},
        "pedidos": {"id", "numero_pedido", "usuario_id", "estado", "total"},
        "pedido_detalles": {
            "id", "pedido_id", "articulo_venta_id", "nombre_articulo", "cantidad",
        },
        "pedido_composiciones": {
            "pedido_detalle_id", "variante_id", "nombre_variante", "cantidad",
        },
        "pedido_historial": {"pedido_id", "estado_nuevo", "origen"},
    },
    "inventario": {
        "almacenes": {"id", "codigo", "nombre", "estado"},
        "existencias": {"id", "almacen_id", "variante_id", "stock_fisico", "stock_reservado"},
        "reservas": {"id", "codigo_reserva", "referencia_id", "estado", "expira_en"},
        "reserva_detalles": {"reserva_id", "almacen_id", "variante_id", "cantidad"},
        "motivos_movimiento": {"id"},
        "movimientos_inventario": {
            "id", "almacen_id", "variante_id", "motivo_id", "cantidad",
            "referencia_id",
        },
    },
    "operaciones": {
        "auditoria_operaciones": {
            "id", "usuario_id", "modulo", "entidad", "entidad_id", "accion",
            "datos_anteriores", "datos_nuevos", "direccion_ip",
        },
    },
}


def leer_estructura(cursor, esquema):
    """Devuelve tablas y columnas de un esquema mediante ``information_schema``."""

    cursor.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """,
        (esquema,),
    )
    estructura = {}
    for fila in cursor.fetchall():
        estructura.setdefault(fila["TABLE_NAME"], set()).add(fila["COLUMN_NAME"])
    return estructura


def comparar_estructura(dominio, estructura):
    """Lista tablas o columnas ausentes para un dominio."""

    errores = []
    for tabla, columnas in CONTRATO[dominio].items():
        if tabla not in estructura:
            errores.append(f"falta la tabla {tabla}")
            continue
        faltantes = sorted(columnas - estructura[tabla])
        if faltantes:
            errores.append(
                f"{tabla}: faltan columnas {', '.join(faltantes)}"
            )
    return errores


def verificar(configuracion, crear_conexion):
    """Conecta en modo de solo lectura y devuelve un informe estructurado."""

    informe = []
    for dominio, esquema in configuracion["esquemas"].items():
        conexion = crear_conexion(esquema, reutilizar=False)
        try:
            with conexion.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
                cursor.execute(
                    "SELECT DATABASE() AS esquema, VERSION() AS version"
                )
                destino = cursor.fetchone() or {}
                if destino.get("esquema") != esquema:
                    raise RuntimeError(
                        f"{dominio} no usa el esquema TEST esperado."
                    )
                estructura = leer_estructura(cursor, esquema)
                errores = comparar_estructura(dominio, estructura)
                informe.append({
                    "dominio": dominio,
                    "esquema": esquema,
                    "version": destino.get("version"),
                    "errores": errores,
                })
        finally:
            conexion.rollback()
            conexion.close()
    return informe


def main():
    """Exige confirmación y ejecuta únicamente consultas de metadatos."""

    parser = argparse.ArgumentParser(
        description="Verifica tablas y columnas TEST mediante solo lectura."
    )
    parser.add_argument("--env", default=str(RAIZ / ".env.test"))
    parser.add_argument(
        "--confirmar-solo-lectura",
        action="store_true",
        help="Confirma que solo se consultarán metadatos del destino TEST.",
    )
    args = parser.parse_args()
    if not args.confirmar_solo_lectura:
        raise SystemExit("Cancelado: falta --confirmar-solo-lectura.")

    ruta_entorno = Path(args.env)
    if not ruta_entorno.is_file():
        raise SystemExit(f"No existe el archivo de entorno: {ruta_entorno}")
    load_dotenv(ruta_entorno, override=True)
    os.environ["SULPAA_TESTING"] = "1"

    from app.config.database import crear_conexion, validar_configuracion_pruebas

    configuracion = validar_configuracion_pruebas()
    informe = verificar(configuracion, crear_conexion)
    correcto = True
    for resultado in informe:
        print(
            f"[{resultado['dominio']}] {resultado['esquema']} "
            f"({resultado['version']})"
        )
        for error in resultado["errores"]:
            correcto = False
            print(f"  [FALTA] {error}")
        if not resultado["errores"]:
            print("  [OK] Estructura mínima compatible.")
    return 0 if correcto else 1


if __name__ == "__main__":
    sys.exit(main())
