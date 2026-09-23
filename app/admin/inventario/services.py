"""
Reglas de negocio del módulo administrativo de Inventario de SULPAA V2.

Este Service orquesta consultas y operaciones sobre el inventario
REAL del sistema, aplicando las reglas del Bloque 3:

- Roles habilitados: GERENTE, ADMINISTRADOR, INVENTARIO.
  Un usuario SIN permiso jamás debe alcanzar una operación de
  escritura, incluso si conoce la URL.
- Nunca se modifica el stock directo sin un movimiento real que
  quede trazado (ENTRADA o AJUSTE).
- La diferencia de una verificación física nunca se corrige
  automáticamente: el usuario autorizado decide registrar el
  ajuste (AJUSTE_CONTEO) y ese ajuste puede referenciar la
  verificación para conservar la trazabilidad.
- Nunca stock negativo ni por debajo del stock reservado.
- Los errores se proyectan como ``ErrorInventario`` para mostrarse
  con seguridad en la interfaz (sin trazas internas).
"""

import logging

from app.admin.inventario.repositories import (
    listar_existencias_detalladas,
    obtener_existencia_detalle,
    listar_movimientos,
    listar_verificaciones,
    listar_motivos_activos,
    registrar_verificacion_fisica,
    registrar_movimiento_stock,
)

logger = logging.getLogger(__name__)


# ============================================================
# CONTROL DE ACCESO
# ============================================================

ROLES_INVENTARIO = ("GERENTE", "ADMINISTRADOR", "INVENTARIO")


class ErrorInventario(Exception):
    """Error de negocio seguro para mostrar en la interfaz."""


def _validar_acceso(roles):
    """Fuerza el permiso real antes de cualquier operación de Inventario."""
    roles = roles or []
    if not (set(ROLES_INVENTARIO) & set(roles)):
        raise ErrorInventario(
            "No tienes permisos para administrar el inventario."
        )


def _puede_leer(roles):
    """Indica si el usuario está habilitado para el módulo (lectura)."""
    return bool(set(ROLES_INVENTARIO) & set((roles or [])))


# ============================================================
# LECTURAS
# ============================================================

def listar_existencias(roles, busqueda=None, solo_bajo_minimo=False):
    """Lista existencias reales si el usuario tiene permiso de lectura."""
    if not _puede_leer(roles):
        raise ErrorInventario(
            "No tienes permisos para consultar el inventario."
        )
    return listar_existencias_detalladas(
        busqueda=busqueda or None,
        solo_bajo_minimo=bool(solo_bajo_minimo),
    )


def obtener_detalle_existencia(roles, existencia_id):
    """Devuelve el detalle completo de una existencia con permisos."""
    if not _puede_leer(roles):
        raise ErrorInventario(
            "No tienes permisos para consultar el inventario."
        )
    detalle = obtener_existencia_detalle(existencia_id)
    if not detalle:
        return None
    detalle["movimientos"] = listar_movimientos(existencia_id)
    detalle["verificaciones"] = listar_verificaciones(existencia_id)
    detalle["motivos_entrada"] = listar_motivos_activos()
    return detalle


def listar_motivos(roles):
    """Lista los motivos activos para los formularios del módulo."""
    if not _puede_leer(roles):
        raise ErrorInventario(
            "No tienes permisos para consultar el inventario."
        )
    return listar_motivos_activos()


# ============================================================
# OPERACIONES (exigen permiso real de escritura)
# ============================================================

def registrar_verificacion(
    actor_id,
    roles,
    existencia_id,
    conteo_fisico,
    observacion=None,
):
    """
    Registra una verificación física como fotografía histórica.

    Reglas:
    - Permiso real obligatorio (GERENTE, ADMINISTRADOR, INVENTARIO).
    - El conteo es un número entero no negativo.
    - NO modifica existencias: solo persiste la evidencia
      (stock_sistema, stock_fisico, diferencia, coincide).
    """
    _validar_acceso(roles)
    _validar_entero(conteo_fisico, "conteo físico")

    try:
        resultado = registrar_verificacion_fisica(
            existencia_id=existencia_id,
            conteo_fisico=int(conteo_fisico),
            usuario_responsable_id=actor_id,
            observacion=observacion,
        )
    except ValueError as error:
        raise ErrorInventario(str(error)) from error
    except Exception:
        logger.exception("Falló la verificación física de %s", existencia_id)
        raise ErrorInventario(
            "No se pudo registrar la verificación. No se guardaron cambios."
        ) from None

    if resultado["coincide"]:
        mensaje = (
            f"Verificación correcta: el conteo coincide "
            f"con el stock del sistema ({resultado['stock_sistema']})."
        )
    else:
        mensaje = (
            f"Verificación registrada: sistema {resultado['stock_sistema']} "
            f"vs conteo {resultado['stock_fisico']} "
            f"(diferencia {resultado['diferencia']:+d}). "
            f"Registra un ajuste AJUSTE_CONTEO si corresponde."
        )

    return {"ok": True, "mensaje": mensaje, "detalle": resultado}


def registrar_entrada(
    actor_id,
    roles,
    existencia_id,
    motivo_codigo,
    cantidad,
    observacion=None,
):
    """
    Registra una ENTRADA de stock con motivo real y trazabilidad.

    Reglas:
    - Permiso real obligatorio.
    - El motivo debe ser de categoría ENTRADA.
    - La cantidad debe ser mayor que cero.
    - El stock nunca queda por debajo del reservado.
    """
    _validar_acceso(roles)
    _validar_entero(cantidad, "cantidad")

    try:
        resultado = registrar_movimiento_stock(
            existencia_id=existencia_id,
            motivo_codigo=motivo_codigo,
            cantidad=int(cantidad),
            tipo_movimiento="ENTRADA",
            usuario_responsable_id=actor_id,
            observacion=observacion,
        )
    except ValueError as error:
        raise ErrorInventario(str(error)) from error
    except Exception:
        logger.exception("Falló la entrada de stock de %s", existencia_id)
        raise ErrorInventario(
            "No se pudo registrar la entrada. No se guardaron cambios."
        ) from None

    return {
        "ok": True,
        "mensaje": (
            f"Entrada de {cantidad} unidades registrada "
            f"(motivo {resultado['motivo_codigo']}). "
            f"Stock anterior {resultado['stock_anterior']}, "
            f"nuevo {resultado['stock_posterior']}."
        ),
    }


def registrar_ajuste(
    actor_id,
    roles,
    existencia_id,
    motivo_codigo,
    tipo_ajuste,
    cantidad,
    observacion=None,
    verificacion_id=None,
):
    """
    Registra un AJUSTE de stock decidido explícitamente por el usuario.

    La diferencia de una verificación NUNCA se aplica sola: aquí el
    usuario autorizado comunica la cantidad y dirección. Si indica la
    verificación que la respalda, el movimiento la referencia
    (movimientos_inventario.referencia_tipo='VERIFICACION').

    Reglas:
    - Permiso real obligatorio.
    - Motivo AJUSTE (AJUSTE_CONTEO u OTRO) y sentido explícito.
    - Cantidad positiva; stock nunca negativo ni bajo reservado.
    """
    _validar_acceso(roles)
    _validar_entero(cantidad, "cantidad")

    tipo_ajuste = str(tipo_ajuste or "").upper()

    if tipo_ajuste not in ("AJUSTE_POSITIVO", "AJUSTE_NEGATIVO"):
        raise ErrorInventario(
            "Selecciona el sentido del ajuste (agregar o retirar)."
        )

    motivo_real = None
    for motivo in listar_motivos_activos():
        if motivo["codigo"] == motivo_codigo:
            motivo_real = motivo
            break

    if not motivo_real:
        raise ErrorInventario("El motivo del ajuste indicado no es válido.")

    if motivo_real["categoria"] != "AJUSTE":
        raise ErrorInventario(
            "Los ajustes requieren un motivo de categoría AJUSTE "
            "(AJUSTE_CONTEO u OTRO)."
        )

    try:
        resultado = registrar_movimiento_stock(
            existencia_id=existencia_id,
            motivo_codigo=motivo_codigo,
            cantidad=int(cantidad),
            tipo_movimiento=tipo_ajuste,
            usuario_responsable_id=actor_id,
            observacion=observacion,
            referencia_tipo=(
                "VERIFICACION" if verificacion_id else None
            ),
            referencia_id=verificacion_id,
        )
    except ValueError as error:
        raise ErrorInventario(str(error)) from error
    except Exception:
        logger.exception("Falló el ajuste de stock de %s", existencia_id)
        raise ErrorInventario(
            "No se pudo registrar el ajuste. No se guardaron cambios."
        ) from None

    sentido = "aumentado" if tipo_ajuste == "AJUSTE_POSITIVO" else "reducido"

    return {
        "ok": True,
        "mensaje": (
            f"Ajuste registrado: stock {sentido} en {cantidad} "
            f"(motivo {motivo_codigo}). Stock anterior "
            f"{resultado['stock_anterior']}, nuevo "
            f"{resultado['stock_posterior']}."
        ),
    }


# ============================================================
# VALIDACIONES COMPARTIDAS
# ============================================================

def _validar_entero(valor, nombre_campo):
    """Valida que el valor sea convertible a un entero positivo útil."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ErrorInventario(
            f"El {nombre_campo} debe ser un número entero."
        ) from None
    if numero < 0:
        raise ErrorInventario(
            f"El {nombre_campo} no puede ser negativo."
        )
    return numero