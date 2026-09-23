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
    # Fórmula oficial:
    #
    #     pedidos completados correctamente
    #     ---------------------------------- × 100
    #            pedidos iniciados
    #
    # Un pedido iniciado sí puede identificarse por una fila en
    # comercio.pedidos. Sin embargo, el modelo no registra un
    # estado final exitoso y canónico del pedido: entrega y pago
    # evolucionan en Operaciones sin sincronizar una finalización
    # integral en Comercio. Por seguridad metodológica, KPI-01
    # permanece pendiente y NO reutiliza ENTREGADO como una
    # equivalencia no demostrada de "pedido correcto".
    # ========================================================


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

    kpis = [
            {
                "codigo": "KPI-01",
                "nombre": "Pedidos procesados correctamente",
                "clasificacion": "RF-01",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "Pendiente: estado final canónico del pedido",
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
                "valor": None,
                "estado": "pendiente",
                "fuente": "operaciones (m\u00e1quina de estados)",
            },
            {
                "codigo": "KPI-08",
                "nombre": "Programaci\u00f3n de entregas",
                "clasificacion": "RF-08",
                "meta": "≥95%",
                "valor": None,
                "estado": "pendiente",
                "fuente": "operaciones (entregas programadas)",
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
        "KPI-04": 98.0,
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
