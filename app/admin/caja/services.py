"""
Servicios del módulo administrativo de Flujo de Caja (Bloque 4).

Reglas de negocio validadas aquí (no en el repositorio):

- Egresos manuales: SOLO GERENTE/ADMINISTRADOR, monto > 0, fecha
  válida, categoría EGRESO ACTIVA, concepto requerido y actor
  siempre presente (el CHECK de la BD lo respalda).
- El flujo neto nunca se presenta como utilidad o ganancia: solo es
  Ingresos - Egresos con movimientos ACTIVOS.
- La reconciliación es idempotente: de pagos PAGADO sin movimiento
  genera los ingresos faltantes sin duplicar (UNIQUE pago_id).
"""

from datetime import datetime

from app.admin.caja import repositories as repos
from app.operaciones import repositories as repos_operaciones_mov
from app.shared.unit_of_work import esquemas_sulpaa

ROLES_CAJA = ("GERENTE", "ADMINISTRADOR")
_MONEDA = "PEN"


class ReglaCajaError(Exception):
    """Regla de negocio violada en el flujo de caja."""


def _roles_ok(roles):
    return bool(set(roles or []) & set(ROLES_CAJA))


def _parsear_fecha(valor):
    """Convierte YYYY-MM-DD (o vacío) a datetime; rechaza fechas inválidas."""
    texto = str(valor or "").strip()
    if not texto:
        return datetime.now()
    try:
        dia = datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        raise ReglaCajaError(
            "La fecha debe tener el formato AAAA-MM-DD."
        )
    hoy = datetime.now()
    if dia.date() == hoy.date():
        return dia.replace(hour=hoy.hour, minute=hoy.minute, second=hoy.second)
    return dia.replace(hour=0, minute=0, second=0)


def registrar_egreso_manual(actor_id, roles, datos):
    """Registra un egreso manual trazable (solo caja ACTIVA)."""
    if not _roles_ok(roles):
        raise ReglaCajaError(
            "Solo GERENTE y ADMINISTRADOR registran egresos de caja."
        )

    datos = datos or {}
    monto_texto = str(datos.get("monto") or "").strip()
    try:
        monto = float(monto_texto)
    except (TypeError, ValueError):
        raise ReglaCajaError("El monto debe ser un número válido.")
    if monto <= 0:
        raise ReglaCajaError("El monto del egreso debe ser mayor a cero.")

    categoria_id = datos.get("categoria_id")
    try:
        categoria_id = int(categoria_id)
    except (TypeError, ValueError):
        raise ReglaCajaError("Indica una categoría de egreso.")

    categoria = repos.buscar_categoria_activa(categoria_id, "EGRESO")
    if not categoria:
        raise ReglaCajaError(
            "La categoría de egreso seleccionada no es válida."
        )

    concepto = str(datos.get("concepto") or "").strip()
    if len(concepto) < 3 or len(concepto) > 200:
        raise ReglaCajaError(
            "El concepto debe tener entre 3 y 200 caracteres."
        )

    metodo_pago_id = datos.get("metodo_pago_id") or None
    if metodo_pago_id is not None:
        try:
            metodo_pago_id = int(metodo_pago_id)
        except (TypeError, ValueError):
            metodo_pago_id = None

    fecha_movimiento = _parsear_fecha(datos.get("fecha"))

    repos.insertar_movimiento_manual(
        categoria_id=categoria["id"],
        tipo="EGRESO",
        concepto=concepto,
        monto=monto,
        moneda=_MONEDA,
        fecha_movimiento=fecha_movimiento,
        metodo_pago_id=metodo_pago_id,
        usuario_registra_id=actor_id,
    )
    return {"ok": True, "tipo": "EGRESO"}


def anular_movimiento(actor_id, roles, movimiento_id, motivo):
    """Anula un movimiento ACTIVO (nunca se elimina la evidencia)."""
    if not _roles_ok(roles):
        raise ReglaCajaError(
            "Solo GERENTE y ADMINISTRADOR anulan movimientos de caja."
        )
    motivo = str(motivo or "").strip()
    if len(motivo) < 5:
        raise ReglaCajaError(
            "Indica un motivo de anulación con detalle (mínimo 5 caracteres)."
        )
    anulado = repos.anular_movimiento(movimiento_id, actor_id, motivo)
    if not anulado:
        raise ReglaCajaError(
            "El movimiento no existe o ya fue anulado."
        )
    return {"ok": True, "estado": "ANULADO"}


def listar_movimientos(filtros=None):
    """Lista movimientos con filtros validados por tipo/origen."""
    filtros = filtros or {}
    return repos.listar_movimientos(
        desde=filtros.get("desde") or None,
        hasta=filtros.get("hasta") or None,
        tipo=filtros.get("tipo") or None,
        origen=filtros.get("origen") or None,
        categoria_id=filtros.get("categoria_id") or None,
    )


def resumen_caja(filtros=None):
    """Resumen de ingresos, egresos y flujo neto del período.

    Aplica los MISMOS filtros que la tabla (desde, hasta, tipo,
    origen, categoría) para que las tarjetas coincidan con la lista
    visible siempre.
    """
    filtros = filtros or {}
    return repos.resumen_movimientos(
        desde=filtros.get("desde") or None,
        hasta=filtros.get("hasta") or None,
        tipo=filtros.get("tipo") or None,
        origen=filtros.get("origen") or None,
        categoria_id=filtros.get("categoria_id") or None,
    )


def reconciliar_caja():
    """Crea los ingresos de caja que faltan por pagos PAGADO (idempotente).

    Devuelve la cantidad de ingresos generados. Un pago PAGADO sin
    movimiento (histórico o por corte) recupera su ingreso sin duplicar.
    """
    from app.config.database import crear_conexion

    esquemas = esquemas_sulpaa()
    conexion = crear_conexion(esquemas["operaciones"])
    try:
        conexion.begin()
        pendientes = repos.pagos_sin_movimiento_caja(conexion, esquemas)
        generados = 0
        for pago in pendientes:
            if repos_operaciones_mov.insertar_ingreso_caja_desde_pago(
                conexion, esquemas, pago
            ):
                generados += 1
        conexion.commit()
        return generados
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def serie_flujo_mensual(meses=6):
    """Serie mensual de flujo para los gráficos del panel (defensiva)."""
    try:
        return repos.serie_flujo_mensual(meses)
    except Exception:
        return []