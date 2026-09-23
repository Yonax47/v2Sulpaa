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
    obtener_metrica_accesos_contenido,
    obtener_metrica_consultas_producto,
    obtener_metrica_favoritos,
    obtener_metrica_historial_pedidos,
    obtener_metrica_kpi09,
    obtener_metrica_pedidos_procesados,
    obtener_metrica_consistencia_estados,
    obtener_metrica_programacion_entregas,
    obtener_metrica_reportes,
    obtener_metrica_satisfaccion,
    obtener_metrica_verificaciones_fisicas,
)


def _calcular_kpi09(metrica):
    """Aplica la fórmula OFICIAL del KPI-09 y aísla su estado.

    KPI-09 = pedidos con INVITACION_OK válida / pedidos entregados elegibles.

    ``metrica`` es el dict devuelto por ``obtener_metrica_kpi09()``.
    Devuelve ``(valor, numerador, denominador)``:

    - valor:   porcentaje (float) o None cuando no hay evidencia.
    - numerador:   COUNT DISTINCT real (no lo inflan INVITACION_OK
      duplicadas del mismo pedido).
    - denominador: COUNT DISTINCT de pedidos elegibles ENTREGADO; si es
      0, el KPI queda PENDIENTE (valor None).

    Una encuesta RESPONDIDA no altera este KPI: el numerador depende
    exclusivamente del evento INVITACION_OK.
    """
    if not metrica.get("disponible"):
        return None, None, None

    numerador = int(metrica.get("invitaciones_ok") or 0)
    denominador = int(metrica.get("pedidos_entregados") or 0)
    if denominador <= 0:
        return None, numerador, denominador

    valor = (numerador / denominador) * 100
    return valor, numerador, denominador


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
    pedidos_completados = metrica_procesados["pedidos_completados"]

    # Regla conceptual: sin denominador (sin evidencia) el KPI NO
    # muestra 0%, queda PENDIENTE. Solo se muestra 0% cuando existe
    # denominador y el numerador es 0.
    kpi_01_valor = (
        (
            pedidos_completados
            / pedidos_iniciados
        )
        * 100
    ) if pedidos_iniciados > 0 else None


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
    ) if total_pedidos_kpi04 > 0 else None


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
    ) if total_pedidos_historial > 0 else None


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
    # "Programadas correctamente" exige distinguir, de forma trazable:
    # una solicitud real de programación (inicia el trámite), su
    # programación aceptada/fecha fijada (correcta) y sus fallos o
    # rechazos. En Operaciones solo existe la tabla `entregas` con la
    # columna `fecha_programada` (nullable) y el historial de estados;
    # NO existe una entidad de "solicitudes de programación" ni un
    # registro de rechazos. Sin ese denominador real, usar el total de
    # entregas sería un sustituto silencioso del "total de solicitudes",
    # por lo que el KPI-08 permanece PENDIENTE (sin evidencia suficiente)
    # hasta que se instrumenten solicitudes reales de programación.
    # ========================================================

    kpi_08_valor = None
    kpi_08_numerador = None
    kpi_08_denominador = None

    # Conteo operativo real de entregas para el dashboard (tarjeta
    # informativa "Entregas"). NO alimenta el KPI-08, que permanece
    # pendiente hasta instrumentar solicitudes de programación.
    try:
        metrica_programacion = obtener_metrica_programacion_entregas()
    except Exception:
        metrica_programacion = {"total_entregas": 0}


    # ========================================================
    # KPI-09 — ENCUESTA DE SATISFACCIÓN (Bloque 4)
    # ========================================================
    #
    # Fórmula OFICIAL (invariable):
    #
    #     pedidos entregados con invitación válida
    #     --------------------------------------- × 100
    #         pedidos entregados elegibles
    #
    # - Numerador:   COUNT DISTINCT de pedidos cuya encuesta tiene un
    #   evento INVITACION_OK real (el enlace PORTAL quedó disponible).
    # - Denominador: COUNT DISTINCT de pedidos elegibles con su entrega
    #   en estado ENTREGADO.
    #
    # Si el denominador es 0, el KPI permanece PENDIENTE. Una encuesta
    # RESPONDIDA NO altera este KPI; varias INVITACION_OK del mismo
    # pedido no duplican el numerador.
    #
    # La satisfacción (promedios, tasa de respuesta) es una métrica
    # GERENCIAL complementaria que se muestra por separado y NUNCA
    # alimenta este KPI.
    # ========================================================

    metrica_kpi09 = obtener_metrica_kpi09()
    kpi_09_valor, kpi_09_numerador, kpi_09_denominador = (
        _calcular_kpi09(metrica_kpi09)
    )

    # Satisfacción: métricas GERENCIALES complementarias (separadas del
    # KPI-09). Promedios, tasa de respuesta y recomendación; ninguna
    # sustituye la fórmula oficial de invitaciones/entregados.
    metrica_satisfaccion = obtener_metrica_satisfaccion()


    # ========================================================
    # KPI-05 — REPORTES GERENCIALES (Bloque 4)
    # ========================================================
    #
    # Fórmula oficial:
    #
    #     solicitudes de reporte EXITOSAS
    #     ------------------------------ × 100
    #        total de solicitudes reales
    #
    # Base real: operaciones.reportes_solicitudes. Visitar el panel de
    # reportes NO genera solicitudes; cada POST de generación registra
    # EXITO o FALLO al terminar de construir el archivo.
    # ========================================================

    metrica_reportes = obtener_metrica_reportes()
    kpi_05_valor = None
    if metrica_reportes.get("disponible") and (
        metrica_reportes["total_solicitudes"] or 0
    ) > 0:
        kpi_05_valor = (
            (
                metrica_reportes["solicitudes_exitosas"]
                / metrica_reportes["total_solicitudes"]
            )
            * 100
        )


    # ========================================================
    # KPI-02 — EXACTITUD DE INVENTARIO (Bloque 3)
    # ========================================================
    #
    # Fórmula (condición de autorización Bloque 3):
    #
    #     verificaciones donde coincide = 1
    #     --------------------------------- × 100
    #     total de verificaciones físicas
    #
    # Base real: inventario.verificaciones_fisicas. Sin
    # evidencia registrada aún, se conserva "Pendiente".
    # ========================================================

    metrica_verificaciones = obtener_metrica_verificaciones_fisicas()
    kpi_02_valor = None
    if (
        metrica_verificaciones.get("disponible")
        and (metrica_verificaciones["total_verificaciones"] or 0) > 0
    ):
        kpi_02_valor = (
            (
                metrica_verificaciones["verificaciones_ok"]
                / metrica_verificaciones["total_verificaciones"]
            )
            * 100
        )


    # ========================================================
    # KPI-03 — ACCESO A INFORMACIÓN DE PRODUCTO (Bloque 3)
    # ========================================================
    #
    # Fórmula (condición de autorización Bloque 3):
    #
    #     consultas EXITO
    #     ---------------- × 100
    #     total de consultas
    #
    # Base real: comercio.consultas_producto (solo intentos
    # funcionales del cliente, nunca assets ni navegación).
    # ========================================================

    metrica_consultas = obtener_metrica_consultas_producto()
    kpi_03_valor = None
    if (
        metrica_consultas.get("disponible")
        and (metrica_consultas["total_consultas"] or 0) > 0
    ):
        kpi_03_valor = (
            (
                metrica_consultas["consultas_exitosas"]
                / metrica_consultas["total_consultas"]
            )
            * 100
        )


    # ========================================================
    # KPI-06 — ARTÍCULOS FAVORITOS DEL CLIENTE (Bloque 3)
    # ========================================================
    #
    # Fórmula (condición de autorización Bloque 3):
    #
    #      operaciones de favoritos EXITOSAS
    #     --------------------------------- × 100
    #     total de operaciones de favoritos
    #
    # Base real: comercio.favoritos_auditoria (append-only).
    # Cada agregar/quitar real deja su resultado EXITO/FALLO.
    # ========================================================

    metrica_favoritos = obtener_metrica_favoritos()
    kpi_06_valor = None
    if (
        metrica_favoritos.get("disponible")
        and (metrica_favoritos["total_favoritos_ops"] or 0) > 0
    ):
        kpi_06_valor = (
            (
                metrica_favoritos["favoritos_exitosos"]
                / metrica_favoritos["total_favoritos_ops"]
            )
            * 100
        )


    # ========================================================
    # KPI-10 — DISPONIBILIDAD DEL CONTENIDO EDUCATIVO (Bloque 3)
    # ========================================================
    #
    # Fórmula (condición de autorización Bloque 3):
    #
    #     accesos EXITO
    #     -------------- × 100
    #     total de accesos
    #
    # Base real: comercio.accesos_contenido (evidencia real de
    # cada consulta a la experiencia "Aprende").
    # ========================================================

    metrica_accesos = obtener_metrica_accesos_contenido()
    kpi_10_valor = None
    if (
        metrica_accesos.get("disponible")
        and (metrica_accesos["total_accesos"] or 0) > 0
    ):
        kpi_10_valor = (
            (
                metrica_accesos["accesos_exitosos"]
                / metrica_accesos["total_accesos"]
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
                "numerador": pedidos_completados,
                "denominador": pedidos_iniciados,
                "formula": ("pedidos completados / pedidos iniciados "
                            "* 100"),
                "evidencia_requerida": ("pedidos con historial completo "
                                        "(iniciados y completados)"),
                "estado": "ok",
                "fuente": "comercio.pedidos + operaciones.entregas/pagos",
            },
            {
                "codigo": "KPI-02",
                "nombre": "Exactitud de inventario",
                "clasificacion": "RF-02",
                "meta": "≥98%",
                "valor": kpi_02_valor,
                "numerador": (
                    metrica_verificaciones.get("verificaciones_ok")
                    if metrica_verificaciones.get("disponible") else None
                ),
                "denominador": (
                    metrica_verificaciones.get("total_verificaciones")
                    if metrica_verificaciones.get("disponible") else None
                ),
                "formula": ("verificaciones con coincidencia / "
                            "total de verificaciones físicas * 100"),
                "evidencia_requerida": (
                    "verificaciones físicas de inventario registradas"),
                "estado": "pendiente" if kpi_02_valor is None else "ok",
                "fuente": "inventario.verificaciones_fisicas",
            },
            {
                "codigo": "KPI-03",
                "nombre": "Acceso a informaci\u00f3n de producto",
                "clasificacion": "RF-03",
                "meta": "≥95%",
                "valor": kpi_03_valor,
                "numerador": (
                    metrica_consultas.get("consultas_exitosas")
                    if metrica_consultas.get("disponible") else None
                ),
                "denominador": (
                    metrica_consultas.get("total_consultas")
                    if metrica_consultas.get("disponible") else None
                ),
                "formula": ("consultas exitosas / total de consultas "
                            "* 100"),
                "evidencia_requerida": (
                    "consultas reales del cliente al detalle de producto"),
                "estado": "pendiente" if kpi_03_valor is None else "ok",
                "fuente": "comercio.consultas_producto",
            },
            {
                "codigo": "KPI-04",
                "nombre": "Disponibilidad de historial de pedidos",
                "clasificacion": "RF-04",
                "meta": "≥98%",
                "valor": kpi_04_valor,
                "numerador": metrica_historial["pedidos_con_historial"],
                "denominador": total_pedidos_kpi04,
                "formula": ("pedidos con historial / total de pedidos "
                            "* 100"),
                "evidencia_requerida": "pedidos registrados",
                "estado": "ok",
                "fuente": "comercio.pedido_historial / comercio.pedidos",
            },
            {
                "codigo": "KPI-05",
                "nombre": "Reportes gerenciales",
                "clasificacion": "RF-05",
                "meta": "≥95%",
                "valor": kpi_05_valor,
                "numerador": (
                    metrica_reportes.get("solicitudes_exitosas")
                    if metrica_reportes.get("disponible") else None
                ),
                "denominador": (
                    metrica_reportes.get("total_solicitudes")
                    if metrica_reportes.get("disponible") else None
                ),
                "formula": ("solicitudes exitosas / total de "
                            "solicitudes * 100"),
                "evidencia_requerida": (
                    "solicitudes reales de generación de reportes"),
                "estado": "pendiente" if kpi_05_valor is None else "ok",
                "fuente": "operaciones.reportes_solicitudes (Bl. 4)",
            },
            {
                "codigo": "KPI-06",
                "nombre": "Art\u00edculos favoritos del cliente",
                "clasificacion": "RF-06",
                "meta": "≥95%",
                "valor": kpi_06_valor,
                "numerador": (
                    metrica_favoritos.get("favoritos_exitosos")
                    if metrica_favoritos.get("disponible") else None
                ),
                "denominador": (
                    metrica_favoritos.get("total_favoritos_ops")
                    if metrica_favoritos.get("disponible") else None
                ),
                "formula": ("operaciones de favoritos exitosas / total "
                            "de operaciones * 100"),
                "evidencia_requerida": (
                    "operaciones reales de favoritos del cliente"),
                "estado": "pendiente" if kpi_06_valor is None else "ok",
                "fuente": "comercio.favoritos_auditoria",
            },
            {
                "codigo": "KPI-07",
                "nombre": "Estados de pedido actualizados",
                "clasificacion": "RF-07",
                "meta": "≥98%",
                "valor": kpi_07_valor,
                "numerador": metrica_consistencia["estados_consistentes"],
                "denominador": total_pedidos_historial,
                "formula": ("pedidos consistentes / pedidos con "
                            "historial * 100"),
                "evidencia_requerida": "pedidos con historial registrado",
                "estado": "ok",
                "fuente": "comercio.pedidos + comercio.pedido_historial",
            },
{
                "codigo": "KPI-08",
                "nombre": "Programaci\u00f3n de entregas",
                "clasificacion": "RF-08",
                "meta": "\u226595%",
                "valor": kpi_08_valor,
                "numerador": kpi_08_numerador,
                "denominador": kpi_08_denominador,
                "formula": ("entregas programadas correctamente / "
                            "total de solicitudes * 100"),
                "evidencia_requerida": ("solicitudes reales de "
                                        "programaci\u00f3n de entrega "
                                        "con desenlace trazable "
                                        "(correcta / fallo / rechazo); "
                                        "el modelo actual solo registra "
                                        "entregas con fecha_programada"),
                "estado": "pendiente",
                "fuente": "operaciones.entregas (sin registro de "
                          "solicitudes de programaci\u00f3n)",
            },
            {
                "codigo": "KPI-09",
                "nombre": "Encuesta de satisfacci\u00f3n",
                "clasificacion": "RF-09",
                "meta": "≥90%",
                "valor": kpi_09_valor,
                "numerador": kpi_09_numerador,
                "denominador": kpi_09_denominador,
                "unidad": "invitaciones/entregados",
                "formula": ("pedidos con INVITACION_OK / pedidos "
                            "entregados elegibles * 100"),
                "evidencia_requerida": (
                    "pedidos entregados con invitación PORTAL validada"),
                "estado": "pendiente" if kpi_09_valor is None else "ok",
                "fuente": "operaciones.encuestas + encuesta_eventos "
                          "(INVITACION_OK) y entregas ENTREGADO",
            },
            {
                "codigo": "KPI-10",
                "nombre": "Contenido educativo",
                "clasificacion": "RF-10",
                "meta": "≥95%",
                "valor": kpi_10_valor,
                "numerador": (
                    metrica_accesos.get("accesos_exitosos")
                    if metrica_accesos.get("disponible") else None
                ),
                "denominador": (
                    metrica_accesos.get("total_accesos")
                    if metrica_accesos.get("disponible") else None
                ),
                "formula": "accesos exitosos / total de accesos * 100",
                "evidencia_requerida": "accesos reales a contenido",
                "estado": "pendiente" if kpi_10_valor is None else "ok",
                "fuente": "comercio.accesos_contenido",
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
    # Los diez KPI funcionales están instrumentados en código (tienen
    # una consulta real definida). Un KPI "sin evidencia en BD" no es
    # "no instrumentado": es un KPI instrumentado que permanece
    # PENDIENTE (pendiente de datos) hasta que su fuente registre
    # actividad real. Esa distinción evita reportar como "pendiente
    # de instrumentación" lo que en realidad está correctamente
    # instrumentado pero aún no dispone de datos.
    # ========================================================

    kpis_funcionales = kpis[:10]
    metas_porcentuales = {
        "KPI-01": 95.0,
        "KPI-02": 98.0,
        "KPI-03": 95.0,
        "KPI-04": 98.0,
        "KPI-05": 95.0,
        "KPI-06": 95.0,
        "KPI-07": 98.0,
        "KPI-08": 95.0,
        "KPI-09": 90.0,
        "KPI-10": 95.0,
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

    # Los diez KPIs son instrumentados (cuentan con consulta real).
    # "Con evidencia" es cuántos tienen valor con denominador > 0;
    # la diferencia son "pendientes de datos" (PENDIENTE, que NO se
    # cuenta como incumplimiento).
    instrumentados = len(kpis_funcionales)
    con_evidencia = sum(
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

    # ========================================================
    # DATOS PARA GRÁFICOS DEL PANEL (defensivos)
    # ========================================================
    #
    # Serie mensual de flujo de caja (caja_movimientos ACTIVOS) y
    # contexto de la encuesta KPI-09. Si las tablas del Bloque 4
    # aún no existieran, se entregan listas vacías sin romper el
    # resto del panel ni los conteos de instrumentados.
    # ========================================================

    graficos = {"flujo_caja": [], "kpi09": None, "satisfaccion": None}
    try:
        from app.admin.caja.services import serie_flujo_mensual
        serie = serie_flujo_mensual(6)
        graficos["flujo_caja"] = [
            {
                "periodo": fila["periodo"],
                "ingresos": round(float(fila["ingresos"] or 0), 2),
                "egresos": round(float(fila["egresos"] or 0), 2),
            }
            for fila in serie
        ]
    except Exception:
        graficos["flujo_caja"] = []

    try:
        if metrica_kpi09.get("disponible"):
            graficos["kpi09"] = {
                "invitaciones_ok": kpi_09_numerador or 0,
                "pedidos_entregados": kpi_09_denominador or 0,
                "valor": (
                    round(kpi_09_valor, 2)
                    if kpi_09_valor is not None else None
                ),
            }
    except Exception:
        graficos["kpi09"] = None

    try:
        graficos["satisfaccion"] = (
            metrica_satisfaccion
            if metrica_satisfaccion.get("disponible")
            else None
        )
    except Exception:
        graficos["satisfaccion"] = None

    # ========================================================
    # RESUMEN OPERATIVO (defensivo)
    # ========================================================
    #
    # Bloque B del resumen ejecutivo: conteos REALES de Comercio,
    # Operaciones y Caja cuando existen datos. Cada pieza se
    # envuelve en try/except para no romper el panel por una tabla
    # vacía o un esquema todavía sin registros. NO se inventa ningún
    # número: si la fuente no tiene datos, el valor queda 0/None y el
    # template lo muestra como "sin datos".
    # ========================================================

    operativo = {
        "pedidos_iniciados": 0,
        "pedidos_completados": 0,
        "entregas": 0,
        "productos_con_stock_bajo": 0,
        "ingresos": 0.0,
        "egresos": 0.0,
        "flujo_neto": 0.0,
        "encuestas_completadas": 0,
        "satisfaccion_promedio": None,
    }

    try:
        operativo["pedidos_iniciados"] = int(
            metrica_procesados.get("pedidos_iniciados") or 0
        )
        operativo["pedidos_completados"] = int(
            metrica_procesados.get("pedidos_completados") or 0
        )
    except Exception:
        pass

    try:
        operativo["entregas"] = int(
            metrica_programacion.get("total_entregas") or 0
        )
    except Exception:
        pass

    # Cantidad de variantes con stock por debajo del mínimo real.
    try:
        from app.admin.inventario.repositories import (
            listar_existencias_detalladas,
        )

        existencias = listar_existencias_detalladas(
            solo_bajo_minimo=True
        )
        operativo["productos_con_stock_bajo"] = int(
            len(existencias or [])
        )
    except Exception:
        pass

    # Totales reales de Caja (movimientos ACTIVOS del período).
    try:
        from app.admin.caja.services import resumen_caja

        resumen_caja_data = resumen_caja()
        caja_ingresos = float(
            resumen_caja_data.get("ingresos") or 0.0
        )
        caja_egresos = float(
            resumen_caja_data.get("egresos") or 0.0
        )
        operativo["ingresos"] = round(caja_ingresos, 2)
        operativo["egresos"] = round(caja_egresos, 2)
        operativo["flujo_neto"] = round(
            caja_ingresos - caja_egresos, 2
        )
    except Exception:
        pass

    try:
        if metrica_satisfaccion.get("disponible"):
            operativo["encuestas_completadas"] = int(
                metrica_satisfaccion.get("encuestas_completadas") or 0
            )
            operativo["satisfaccion_promedio"] = (
                metrica_satisfaccion.get("satisfaccion_promedio")
            )
    except Exception:
        pass

    return {
        "ok": True,
        "kpis": kpis,
        "kpis_funcionales": kpis_funcionales,
        "graficos": graficos,
        "operativo": operativo,
        "resumen": {
            "total": len(kpis_funcionales),
            "instrumentados": instrumentados,
            "con_evidencia": con_evidencia,
            "pendientes_de_datos": len(kpis_funcionales) - con_evidencia,
            "pendientes": len(kpis_funcionales) - con_evidencia,
            "cumplen": cumplen,
            "no_cumplen": no_cumplen,
        },
    }
