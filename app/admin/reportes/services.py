"""
Servicios del módulo administrativo de Reportes Gerenciales (Bloque 4).

Tipos de reporte con datos reales del sistema:

- KPI       (resumen ejecutivo de los 10 indicadores funcionales).
- VENTAS    (pedidos del período).
- CAJA      (movimientos de caja del período).
- ENCUESTAS (encuestas de satisfacción del período).

Cada generación REAL (POST desde el panel) queda auditada en
``reportes_solicitudes`` con resultado EXITO o FALLO. Esa auditoría es
la base del KPI-05 y nunca vuelve a generar un reporte (sin recursión).
"""

import csv
import io
from datetime import date

from app.admin.caja import repositories as repos_caja
from app.admin.inventario import repositories as repos_inventario
from app.admin.reportes import repositories as repos_reportes
from app.admin.reportes.entregas_repositories import (
    listar_entregas_reporte,
)
from app.admin.reportes.pdf import PdfReporteUnicode
from app.admin.reportes.ventas_repositories import obtener_datos_ventas
from app.admin.services import resumen_dashboard
from app.encuestas import repositories as repos_encuestas

ROLES_REPORTES = ("GERENTE", "ADMINISTRADOR")

TIPOS_REPORTE = {
    "KPI": {
        "nombre": "Resumen de indicadores KPI",
        "descripcion": "Los 10 KPI funcionales con su valor, meta y estado.",
    },
    "VENTAS": {
        "nombre": "Ventas por período",
        "descripcion": "Pedidos generados en el rango de fechas elegido.",
    },
    "PEDIDOS": {
        "nombre": "Pedidos del período",
        "descripcion": "Resumen y detalle real de pedidos por estado.",
    },
    "INVENTARIO": {
        "nombre": "Inventario actual",
        "descripcion": "Stock físico, reservado, disponible y mínimo por variante.",
    },
    "ENTREGAS": {
        "nombre": "Entregas del período",
        "descripcion": "Entregas reales con estado, programación y repartidor.",
    },
    "CAJA": {
        "nombre": "Flujo de caja",
        "descripcion": "Ingresos y egresos del período con su flujo neto.",
    },
    "ENCUESTAS": {
        "nombre": "Encuestas de satisfacción",
        "descripcion": "Calificaciones y recomendación recibidas en el período.",
    },
}

FORMATOS = ("PDF", "XLSX", "CSV")


def _normalizar(texto):
    """Texto seguro para reportes.

    La generación de PDF usa la familia Unicode ``DejaVu Sans``, por lo
    que los acentos y símbolos (≥, ≤, ñ, ¿, ¡, S/) se conservan tal cual
    en todos los formatos.
    """
    return str(texto or "")


class ReglaReporteError(Exception):
    """Regla de negocio violada en la generación de reportes."""


# ============================================================
# RECOLECCIÓN DE DATOS POR TIPO
# ============================================================

def _datos_kpi():
    resumen = resumen_dashboard()
    filas = []
    for kpi in resumen["kpis_funcionales"]:
        estado = {
            "cumple": "Cumple",
            "no_cumple": "No cumple",
            "pendiente": "Pendiente",
        }.get(kpi["estado"], "Pendiente")
        valor = (
            f"{float(kpi['valor']):.2f} %"
            if kpi["valor"] is not None
            else "Sin evidencia"
        )
        filas.append([
            kpi["codigo"], _normalizar(kpi["nombre"]),
            kpi["meta"], valor, estado,
        ])
    return {
        "titulo": "Resumen de indicadores KPI",
        "columnas": ["Código", "Indicador", "Meta", "Valor", "Estado"],
        "filas": filas,
        "anexo": None,
    }


def _datos_ventas(desde, hasta):
    pedidos = obtener_datos_ventas(desde=desde or None, hasta=hasta or None)
    filas = []
    for pedido in pedidos:
        filas.append([
            _normalizar(pedido["numero_pedido"]),
            _normalizar(pedido.get("origen") or ""),
            _normalizar(pedido["estado"]),
            f"{float(pedido['total']):.2f}",
            _normalizar(pedido.get("moneda") or "PEN"),
            (pedido.get("creado_en") or "").strftime("%Y-%m-%d %H:%M")
            if hasattr(pedido.get("creado_en"), "strftime") else "",
        ])
    total_filas = sum(float(p["total"]) for p in pedidos if p["total"])
    return {
        "titulo": "Ventas por período",
        "columnas": ["Pedido", "Origen", "Estado", "Total", "Moneda", "Fecha"],
        "filas": filas,
        "anexo": {"etiqueta": "Total del período", "valor": total_filas},
    }


def _datos_pedidos(desde, hasta):
    """Detalle real de pedidos del período con resumen por estado.

    Reutiliza la fuente única de Comercio (``pedidos``) y agrupa los
    estados reales de los pedidos listados. No inventa estados: solo
    cuenta los que existen en la fuente.
    """
    pedidos = obtener_datos_ventas(desde=desde or None, hasta=hasta or None)
    filas = []
    conteo_estados = {}
    total_moneda = 0.0
    for pedido in pedidos:
        estado = str(pedido.get("estado") or "DESCONOCIDO").upper()
        conteo_estados[estado] = conteo_estados.get(estado, 0) + 1
        if pedido.get("total"):
            total_moneda += float(pedido["total"])
        filas.append([
            _normalizar(pedido["numero_pedido"]),
            _normalizar(pedido.get("origen") or ""),
            estado,
            f"{float(pedido['total']):.2f}" if pedido.get("total") else "",
            _normalizar(pedido.get("moneda") or "PEN"),
            (pedido.get("creado_en") or "").strftime("%Y-%m-%d %H:%M")
            if hasattr(pedido.get("creado_en"), "strftime") else "",
        ])
    resumen_estados = " · ".join(
        f"{estado}: {cantidad}"
        for estado, cantidad in sorted(conteo_estados.items())
    ) or "Sin pedidos en el período"
    return {
        "titulo": "Pedidos del período",
        "columnas": ["Pedido", "Origen", "Estado", "Total", "Moneda",
                     "Fecha"],
        "filas": filas,
        "anexo": {
            "etiqueta": "Total de pedidos",
            "valor": len(pedidos),
            "nota": (
                f"Por estado: {resumen_estados} | "
                f"Monto total: {total_moneda:.2f}"
            ),
        },
    }


def _datos_inventario():
    """Snapshot real del inventario (solo lectura, sin inventar stock).

    Fuente única: ``listar_existencias_detalladas`` de Inventario. El
    nivel (bajo/correcto) se deriva del ``stock_fisico`` real contra el
    ``stock_minimo`` registrado.
    """
    existencias = repos_inventario.listar_existencias_detalladas()
    filas = []
    conteo_bajo = 0
    for ex in existencias:
        bajo = bool(ex["bajo_minimo"])
        if bajo:
            conteo_bajo += 1
        filas.append([
            _normalizar(ex["almacen_codigo"]),
            _normalizar(ex["sku"]),
            _normalizar(ex["nombre_comercial"]),
            _normalizar(ex["sabor"]),
            _normalizar(ex["presentacion"]),
            int(ex["stock_fisico"]),
            int(ex["stock_reservado"]),
            int(ex["stock_disponible"]),
            int(ex["stock_minimo"]),
            "Bajo mínimo" if bajo else "Correcto",
        ])
    anexo = None
    if existencias:
        anexo = {
            "etiqueta": "Variantes totales",
            "valor": len(existencias),
            "nota": f"Con stock bajo el mínimo: {conteo_bajo}",
        }
    return {
        "titulo": "Inventario actual",
        "columnas": ["Almacén", "SKU", "Producto", "Sabor",
                     "Presentación", "Físico", "Reservado",
                     "Disponible", "Mínimo", "Nivel"],
        "filas": filas,
        "anexo": anexo,
    }


def _datos_entregas(desde, hasta):
    """Entregas reales del período con estado y repartidor cuando existe.

    Fuente única: ``listar_entregas_reporte`` de Operaciones. No crea
    entregas: solo reporta las registradas y su estado real.
    """
    entregas = listar_entregas_reporte(
        desde=desde or None, hasta=hasta or None
    )
    filas = []
    conteo_estados = {}
    for entrega in entregas:
        estado = str(entrega.get("estado") or "DESCONOCIDO").upper()
        conteo_estados[estado] = conteo_estados.get(estado, 0) + 1
        filas.append([
            _normalizar(entrega["numero_pedido"]),
            _normalizar(entrega.get("tipo_entrega") or ""),
            estado,
            (entrega.get("fecha_programada") or "").strftime("%Y-%m-%d")
            if hasattr(entrega.get("fecha_programada"), "strftime") else "",
            (entrega.get("completado_en") or "").strftime("%Y-%m-%d %H:%M")
            if hasattr(entrega.get("completado_en"), "strftime") else "",
            _normalizar(entrega.get("repartidor_detalle") or "Sin asignar"),
            _normalizar(entrega.get("moneda") or "PEN"),
            f"{float(entrega['costo_cobrado_cliente']):.2f}"
            if entrega.get("costo_cobrado_cliente") is not None else "",
        ])
    resumen_estados = " · ".join(
        f"{estado}: {cantidad}"
        for estado, cantidad in sorted(conteo_estados.items())
    ) or "Sin entregas en el período"
    return {
        "titulo": "Entregas del período",
        "columnas": ["Pedido", "Tipo", "Estado", "Programada",
                     "Completada", "Repartidor", "Moneda", "Costo"],
        "filas": filas,
        "anexo": {
            "etiqueta": "Total de entregas",
            "valor": len(entregas),
            "nota": f"Por estado: {resumen_estados}",
        },
    }


def _datos_caja(desde, hasta):
    movimientos = repos_caja.listar_movimientos(
        desde=desde or None, hasta=hasta or None
    )
    resumen = repos_caja.resumen_movimientos(
        desde=desde or None, hasta=hasta or None
    )
    filas = []
    for mov in movimientos:
        filas.append([
            _normalizar(mov.get("fecha_movimiento")),
            mov["tipo"],
            mov["origen"],
            _normalizar(mov.get("categoria_nombre") or ""),
            _normalizar(mov.get("concepto") or ""),
            f"{float(mov['monto']):.2f}",
            _normalizar(mov.get("moneda") or "PEN"),
            _normalizar(mov.get("metodo_nombre") or ""),
            mov["estado"],
        ])
    anexo = {
        "etiqueta": "Flujo neto del período",
        "valor": resumen["flujo_neto"],
        "nota": (
            f"Ingresos: {resumen['ingresos']:.2f} | "
            f"Egresos: {resumen['egresos']:.2f}"
        ),
    }
    return {
        "titulo": "Flujo de caja",
        "columnas": ["Fecha", "Tipo", "Origen", "Categoría", "Concepto",
                     "Monto", "Moneda", "Método", "Estado"],
        "filas": filas,
        "anexo": anexo,
    }


def _datos_encuestas(desde, hasta):
    encuestas = repos_encuestas.listar_encuestas(
        estado=None, desde=desde or None, hasta=hasta or None
    )
    filas = []
    for encuesta in encuestas:
        filas.append([
            _normalizar(encuesta.get("numero_pedido") or ""),
            encuesta["estado"],
            _normalizar(encuesta.get("canal") or ""),
            (encuesta.get("calificacion_general") if
             encuesta.get("calificacion_general") is not None else ""),
            _normalizar(encuesta.get("recomendaria") or ""),
            (encuesta.get("creado_en") or "").strftime("%Y-%m-%d %H:%M")
            if hasattr(encuesta.get("creado_en"), "strftime") else "",
        ])
    respondidas = sum(
        1 for e in encuestas if e["estado"] == "RESPONDIDA"
    )
    return {
        "titulo": "Encuestas de satisfacción",
        "columnas": ["Pedido", "Estado", "Canal", "Calif. gral.",
                     "Recomienda", "Creada"],
        "filas": filas,
        "anexo": {
            "etiqueta": "Encuestas respondidas",
            "valor": respondidas,
            "nota": f"Total registradas: {len(encuestas)}",
        },
    }


# ============================================================
# GENERADORES DE ARCHIVOS
# ============================================================

def _csv_generar(titulo, columnas, filas, anexo):
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow([_normalizar(titulo)])
    escritor.writerow(columnas)
    for fila in filas:
        escritor.writerow([_normalizar(str(celda)) for celda in fila])
    if anexo:
        escritor.writerow([])
        escritor.writerow([
            _normalizar(anexo.get("etiqueta", "")),
            _normalizar(str(anexo.get("valor", ""))),
        ])
        if anexo.get("nota"):
            escritor.writerow([_normalizar(anexo["nota"])])
    return buffer.getvalue().encode("utf-8-sig")


def _xlsx_generar(titulo, columnas, filas, anexo):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Reporte"
    hoja.append([titulo])
    hoja["A1"].font = Font(bold=True)
    hoja.append(columnas)
    for celda in hoja[2]:
        celda.font = Font(bold=True)
    for fila in filas:
        hoja.append([_normalizar(str(celda)) for celda in fila])
    if anexo:
        hoja.append([])
        hoja.append([
            _normalizar(anexo.get("etiqueta", "")),
            _normalizar(str(anexo.get("valor", ""))),
        ])
        if anexo.get("nota"):
            hoja.append([_normalizar(anexo["nota"])])
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


# Anchos de columna por tipo de reporte (en milímetros, para tablas PDF).
# La tabla se escala al ancho útil del A4 (190 mm), por lo que las
# proporciones relativas se conservan. La columna de mayor contenido
# textual recibe más espacio para evitar cortes o superposiciones.
_PDF_ANCHOS = {
    "KPI": [20, 78, 24, 32, 36],
    "VENTAS": [30, 24, 34, 24, 22, 56],
    "PEDIDOS": [30, 24, 34, 24, 22, 56],
    "INVENTARIO": [16, 20, 34, 22, 22, 14, 14, 14, 14, 20],
    "ENTREGAS": [28, 20, 30, 26, 30, 30, 16, 20],
    "CAJA": [26, 16, 20, 24, 34, 22, 18, 18, 12],
    "ENCUESTAS": [30, 30, 26, 22, 30, 52],
}

# Columnas cuyos valores son numéricos y deben alinearse a la derecha.
_COLUMNAS_NUMERICAS = {
    "Total", "Monto", "Físico", "Reservado", "Disponible", "Mínimo",
    "Costo", "Calif. gral.",
}


def _pdf_generar(titulo, columnas, filas, anexo, rango="", tipo=None):
    """PDF con la base visual común (encabezado, tabla y pie)."""
    pdf = PdfReporteUnicode()
    pdf.encabezado_institucional(titulo, rango)
    anchos = (_PDF_ANCHOS or {}).get(tipo) if tipo else None
    alineaciones = ["R" if col in _COLUMNAS_NUMERICAS else "L"
                    for col in columnas]
    pdf.tabla(columnas, filas, col_anchos=anchos, alineaciones=alineaciones)
    if anexo:
        pdf.anexo(
            anexo.get("etiqueta", ""), anexo.get("valor", ""),
            anexo.get("nota"),
        )
    return bytes(pdf.output())


_GENERADORES = {
    "PDF": _pdf_generar,
    "XLSX": _xlsx_generar,
    "CSV": _csv_generar,
}


def _rango_texto(desde, hasta):
    """Texto legible del rango de fechas aplicado al reporte."""
    if not desde and not hasta:
        return ""
    inicio = _formatear_fecha(desde) if desde else "inicio"
    fin = _formatear_fecha(hasta) if hasta else "hoy"
    return f"Período: {inicio} → {fin}"


def _formatear_fecha(valor):
    """Convierte una fecha (date o texto ISO) a dd/mm/aaaa si es posible."""
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor or "").strip()
    partes = texto.split(" ")[0].split("-")
    if len(partes) == 3:
        anio, mes, dia = partes
        if anio.isdigit() and mes.isdigit() and dia.isdigit():
            return f"{dia}/{mes}/{anio}"
    return texto

_MIMETYPES = {
    "PDF": "application/pdf",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "CSV": "text/csv",
}

# ============================================================
# ORQUESTACIÓN PRINCIPAL (KPI-05)
# ============================================================

def generar_reporte(tipo, formato, actor_id, filtros=None):
    """Genera el reporte, construye su archivo y audita la solicitud.

    La auditoría (EXITO/FALLO) se registra SIEMPRE al terminar de
    construir el archivo. El registro de la solicitud es posterior a la
    toma de datos (snapshot primero) y nunca genera otro reporte.
    """
    filtros = filtros or {}
    tipo = str(tipo or "").upper()
    formato = str(formato or "").upper()

    if tipo not in TIPOS_REPORTE:
        raise ReglaReporteError("El tipo de reporte no es válido.")
    if formato not in FORMATOS:
        raise ReglaReporteError("El formato del reporte no es válido.")

    desde = filtros.get("desde") or None
    hasta = filtros.get("hasta") or None
    parametros = f"desde={desde or ''}|hasta={hasta or ''}"

    try:
        if tipo == "KPI":
            datos = _datos_kpi()
        elif tipo == "VENTAS":
            datos = _datos_ventas(desde, hasta)
        elif tipo == "PEDIDOS":
            datos = _datos_pedidos(desde, hasta)
        elif tipo == "INVENTARIO":
            datos = _datos_inventario()
        elif tipo == "ENTREGAS":
            datos = _datos_entregas(desde, hasta)
        elif tipo == "CAJA":
            datos = _datos_caja(desde, hasta)
        elif tipo == "ENCUESTAS":
            datos = _datos_encuestas(desde, hasta)
        else:
            raise ReglaReporteError("El tipo de reporte no es válido.")

        rango = _rango_texto(desde, hasta)
        generador = _GENERADORES[formato]
        if formato == "PDF":
            contenido = generador(
                datos["titulo"], datos["columnas"], datos["filas"],
                datos.get("anexo"), rango=rango, tipo=tipo,
            )
        else:
            contenido = generador(
                datos["titulo"], datos["columnas"], datos["filas"],
                datos.get("anexo"),
            )
        repos_reportes.registrar_solicitud_reporte(
            tipo_reporte=tipo, formato=formato, parametros=parametros,
            usuario_solicitante_id=actor_id, resultado="EXITO",
        )
    except Exception as error:
        try:
            repos_reportes.registrar_solicitud_reporte(
                tipo_reporte=tipo, formato=formato, parametros=parametros,
                usuario_solicitante_id=actor_id, resultado="FALLO",
                error_tecnico=str(error)[:300],
            )
        except Exception:
            pass
        raise ReglaReporteError(
            f"No se pudo generar el reporte: {error}"
        )

    fecha = date.today().strftime("%Y%m%d")
    return {
        "ok": True,
        "contenido": contenido,
        "nombre_archivo": f"reporte_{tipo.lower()}_{fecha}.{formato.lower()}",
        "mimetype": _MIMETYPES[formato],
    }


def tipos_reportes():
    """Catálogo de reportes disponibles con su descripción."""
    resultado = []
    for codigo, info in TIPOS_REPORTE.items():
        resultado.append({
            "codigo": codigo,
            "nombre": info["nombre"],
            "descripcion": info["descripcion"],
        })
    return resultado