"""
Servicios del m\u00f3dulo Administrativo de SULPAA V2.

Responsabilidad:
- Orquestar las operaciones que el dashboard administrativo
  necesita (KPI-04 instrumentado en la Etapa 1).
- No contiene SQL (eso vive en admin/repositories.py).
- No contiene rutas (eso vive en admin/routes.py).
- No modifica datos reales: s\u00f3lo LEE las m\u00e9tricas que
  las tablas existentes ya permiten calcular.

KPI instrumentado en esta Etapa 1:

- KPI-04: Disponibilidad del historial de pedidos.

KPI-01 permanece pendiente: el modelo actual no dispone de
un estado final canónico del pedido que permita demostrar una
finalización correcta de extremo a extremo.

Los dem\u00e1s 16 KPI (02-03, 05-18) quedan documentados
como "Pendiente de instrumentaci\u00f3n" en el dashboard:
NO se inventan valores.
"""

from app.admin.repositories import (
    obtener_metrica_historial_pedidos,
    obtener_metrica_pedidos_procesados,
    obtener_metrica_consistencia_estados,
    obtener_metrica_programacion_entregas,
    obtener_metrica_satisfaccion,
)


def resumen_dashboard():
    """
    Calcula el resumen completo que el dashboard muestra.

    Returns:
        dict con tres secciones:
        - "kpis": catálogo completo de 18 indicadores.
        - "kpis_funcionales": KPI-01 a KPI-10, que son los
          indicadores visibles en este panel.
        - "resumen": conteos derivados de los diez KPI
          funcionales, sin valores simulados.
    """

    # ========================================================
    # KPI-01 — TASA DE PEDIDOS REALIZADOS CORRECTAMENTE
    # ========================================================
    #
    # Fórmula oficial:
    #
    #     pedidos completados correctamente (COMPLETADO legítimo)
    #     ------------------------------------------------------ × 100
    #            pedidos iniciados (EN_PREPARACION o COMPLETADO)
    #
    # Un "COMPLETADO legítimo" es un pedido en estado COMPLETADO
    # que además tiene una entrega ENTREGADO y un pago PAGADO en
    # Operaciones, es decir, cerró el flujo extremo a extremo por
    # la ruta canónica del Bloque 2.
    # ========================================================

    metrica_procesados = obtener_metrica_pedidos_procesados()
    pedidos_iniciados = metrica_procesados["pedidos_iniciados"]

    kpi_01_valor = (
        (
            metrica_procesados["pedidos_completados"]
            / pedidos_iniciados
        )
        * 100
    ) if pedidos_iniciados > 0 else 0.0


    # ========================================================
    # KPI-04 (valor real)
    # ========================================================
    #
    # Base real: `pedido_historial` (comercio) sobre
    # `pedidos`. Porcentaje de pedidos con historial.
    # ========================================================

    metrica_historial = obtener_metrica_historial_pedidos()

    total_pedidos_kpi04 = metrica_historial["total_pedidos"]

    kpi_04_valor = (
        (
            metrica_historial["pedidos_con_historial"]
            / total_pedidos_kpi04
        )
        * 100
    ) if total_pedidos_kpi04 > 0 else 0.0


    # ========================================================
    # KPI-07 — ESTADOS DE PEDIDO ACTUALIZADOS (consistencia)
    # ========================================================
    #
    # Fórmula oficial:
    #
    #     pedidos cuyo estado actual coincide con el último
    #     evento registrado en pedido_historial
    #     ---------------------------------------------------- × 100
    #           pedidos con al menos un evento de historial
    # ========================================================

    metrica_consistencia = obtener_metrica_consistencia_estados()
    total_pedidos_historial = metrica_consistencia[
        "total_pedidos_historial"
    ]

    kpi_07_valor = (
        (
            metrica_consistencia["estados_consistentes"]
            / total_pedidos_historial
        )
        * 100
    ) if total_pedidos_historial > 0 else 0.0


    # ========================================================
    # KPI-08 — PROGRAMACIÓN DE ENTREGAS
    # ========================================================
    #
    # Fórmula oficial:
    #
    #     entregas programadas correctamente
    #     --------------------------------- × 100
    #            total de solicitudes
    #
    # Una solicitud está "programada correctamente" cuando su
    # `fecha_programada` quedó registrada en Operaciones.
    # ========================================================

    metrica_programacion = obtener_metrica_programacion_entregas()
    total_entregas_kpi08 = metrica_programacion["total_entregas"]

    kpi_08_valor = (
        (
            metrica_programacion["entregas_programadas"]
            / total_entregas_kpi08
        )
        * 100
    ) if total_entregas_kpi08 > 0 else 0.0


    # ========================================================
    # KPI-09 (GANCHO) — ENCUESTA DE SATISFACCIÓN
    # ========================================================
    #
    # El dominio Operaciones aún no define la tabla `encuestas`
    # en el dump vigente. La métrica base consulta
    # information_schema y, si la tabla no existe, devuelve
    # "disponible": False. El dashboard conserva el KPI como
    # "Pendiente" sin inventar un valor.
    # ========================================================

    metrica_satisfaccion = obtener_metrica_satisfaccion()
    kpi_09_valor = None
    if metrica_satisfaccion.get("disponible") and (
        metrica_satisfaccion["encuestas_completadas"] or 0
    ) > 0:
        kpi_09_valor = (
            (
                metrica_satisfaccion["encuestas_satisfactorias"]
                / metrica_satisfaccion["encuestas_completadas"]
            )
            * 100
        )

    kpis = [
            {
                "codigo": "KPI-01",
                "nombre": "Pedidos procesados correctamente",
                "clasificacion": "RF-01",
                "meta": "≥95%",
                "valor": kpi_01_valor,
                "estado": "ok",
                "fuente": "comercio.pedidos + operaciones.entregas/pagos",
            },
            {
                "codigo": "KPI-02",
                "nombre": "Exactitud de inventario",
                "clasificacion": "RF-02",
                "meta": "≥98%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "inventario (conteo f\u00edsico)",
            },
            {
                "codigo": "KPI-03",
                "nombre": "Acceso a informaci\u00f3n de producto",
                "clasificacion": "RF-03",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "comercio (cat\u00e1logo/b\u00fasqueda)",
            },
            {
                "codigo": "KPI-04",
                "nombre": "Disponibilidad de historial de pedidos",
                "clasificacion": "RF-04",
                "meta": "≥98%",
                "valor": kpi_04_valor,
                "estado": "ok",
                "fuente": "comercio.pedido_historial / comercio.pedidos",
            },
            {
                "codigo": "KPI-05",
                "nombre": "Reportes gerenciales",
                "clasificacion": "RF-05",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "operaciones/administraci\u00f3n (reportes)",
            },
            {
                "codigo": "KPI-06",
                "nombre": "Art\u00edculos favoritos del cliente",
                "clasificacion": "RF-06",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "comercio (favoritos/lista deseos)",
            },
            {
                "codigo": "KPI-07",
                "nombre": "Estados de pedido actualizados",
                "clasificacion": "RF-07",
                "meta": "≥98%",
                "valor": kpi_07_valor,
                "estado": "ok",
                "fuente": "comercio.pedidos + comercio.pedido_historial",
            },
            {
                "codigo": "KPI-08",
                "nombre": "Programaci\u00f3n de entregas",
                "clasificacion": "RF-08",
                "meta": "≥95%",
                "valor": kpi_08_valor,
                "estado": "ok",
                "fuente": "operaciones.entregas (fecha_programada)",
            },
            {
                "codigo": "KPI-09",
                "nombre": "Encuesta de satisfacci\u00f3n",
                "clasificacion": "RF-09",
                "meta": "≥90%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "identidad/operaciones (encuestas)",
            },
            {
                "codigo": "KPI-10",
                "nombre": "Contenido educativo",
                "clasificacion": "RF-10",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "comercio (contenido/secciones)",
            },
            {
                "codigo": "KPI-11",
                "nombre": "Accesibilidad m\u00f3vil (RNF-M1)",
                "clasificacion": "RNF",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "evaluaci\u00f3n respaldo (pruebas)",
            },
            {
                "codigo": "KPI-12",
                "nombre": "Seguridad de acceso",
                "clasificacion": "RNF",
                "meta": "0 incidentes",
                "valor": None,
                "estado": "pendiente",
                "fuente": "identidad (auditor\u00eda de accesos)",
            },
            {
                "codigo": "KPI-13",
                "nombre": "Facilidad de uso",
                "clasificacion": "RNF",
                "meta": "≥90%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "evaluaci\u00f3n usuarios",
            },
            {
                "codigo": "KPI-14",
                "nombre": "Disponibilidad del sistema",
                "clasificacion": "RNF",
                "meta": "≥99%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "monitoreo/uptime",
            },
            {
                "codigo": "KPI-15",
                "nombre": "Crecimiento del sistema",
                "clasificacion": "RNF",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "story points/etapas",
            },
            {
                "codigo": "KPI-16",
                "nombre": "Claridad de reportes",
                "clasificacion": "RNF",
                "meta": "≥90%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "evaluaci\u00f3n reportes",
            },
            {
                "codigo": "KPI-17",
                "nombre": "Mantenibilidad",
                "clasificacion": "RNF",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "deuda t\u00e9cnica/commits",
            },
            {
                "codigo": "KPI-18",
                "nombre": "Tiempo de respuesta del sistema",
                "clasificacion": "RNF",
                "meta": "≤3 segundos",
                "valor": None,
                "estado": "pendiente",
                "fuente": "monitoreo tiempos",
            },
        ]

    # ========================================================
    # RESUMEN DE INDICADORES FUNCIONALES (KPI-01 A KPI-10)
    # ========================================================
    #
    # El panel administrativo de esta etapa presenta únicamente
    # los diez KPI funcionales. Los KPI instrumentados se evalúan
    # contra su meta real; los demás permanecen pendientes y no
    # participan como cumplimiento ni incumplimiento.
    # ========================================================

    kpis_funcionales = kpis[:10]
    metas_porcentuales = {
        "KPI-01": 95.0,
        "KPI-04": 98.0,
        "KPI-07": 98.0,
        "KPI-08": 95.0,
    }

    for kpi in kpis_funcionales:
        if kpi["valor"] is None:
            kpi["estado"] = "pendiente"
            continue

        kpi["valor"] = round(float(kpi["valor"]), 2)
        meta = metas_porcentuales.get(kpi["codigo"])
        kpi["estado"] = (
            "cumple"
            if meta is not None and kpi["valor"] >= meta
            else "no_cumple"
        )

    instrumentados = sum(
        kpi["valor"] is not None
        for kpi in kpis_funcionales
    )
    cumplen = sum(
        kpi["estado"] == "cumple"
        for kpi in kpis_funcionales
    )
    no_cumplen = sum(
        kpi["estado"] == "no_cumple"
        for kpi in kpis_funcionales
    )

    return {
        "ok": True,
        "kpis": kpis,
        "kpis_funcionales": kpis_funcionales,
        "resumen": {
            "total": len(kpis_funcionales),
            "instrumentados": instrumentados,
            "pendientes": len(kpis_funcionales) - instrumentados,
            "cumplen": cumplen,
            "no_cumplen": no_cumplen,
        },
    }
