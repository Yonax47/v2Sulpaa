"""Configuración centralizada de los PDF gerenciales de SULPAA V2.

Los PDF se generan con la familia ``DejaVu Sans`` (description:
https://dejavu-fonts.github.io/), una fuente Unicode de distribución
libre que cubre el alfabeto completo requerido por SULPAA:

- Símbolos de comparación: ≥, ≤
- Vocales acentuadas: á é í ó ú / Á É Í Ó Ú
- ñ / Ñ
- Signos de apertura: ¿, ¡
- Moneda peruana: S/

La fuente vive bajo ``app/admin/reportes/fonts/`` (con su licencia) y se
resuelve de forma relativa al propio paquete, por lo que funciona sin
depender de rutas absolutas ni de fuentes del sistema operativo. Esta
resolución es válida al clonar el repositorio en otra máquina.

Toda generación de PDF del sistema debe crear su documento a partir de
:class:`PdfReporteUnicode` (o registrar las fuentes mediante
:func:`registrar_fuentes`) para no repetir la configuración de fuentes en
cada generador ni reintroducir la fuente core latin-1 de fpdf2.

Base visual común (ajuste visual/UX final)
-----------------------------------------

Todos los PDF comparten la misma identidad institucional:

- Encabezado: logo de SULPAA (si el archivo existe), identificación
  ``CORPORACIÓN SULPAA S.A.C.``, nombre del reporte, período o rango de
  fechas cuando aplica y fecha de generación.
- Cuerpo: tablas profesionalmente formateadas con la API ``table()`` de
  fpdf2 (wrapping real de textos, encabezados diferenciados, repetición
  de encabezado en cada página, altura de fila dinámica y alineación de
  números) y anexos con la jerarquía tipográfica correspondiente.
- Pie: identificación institucional, página actual y la indicación de
  que el documento fue generado por el sistema.
"""

from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

RUTA_FUENTES = Path(__file__).resolve().parent / "fonts"
RUTA_LOGO = (
    Path(__file__).resolve().parents[3] / "static" / "img" / "logo-sulpaa.png"
)

_FAMILIA = "DejaVuSans"

_VARIANTES = {
    "": "DejaVuSans.ttf",
    "B": "DejaVuSans-Bold.ttf",
    "I": "DejaVuSans-Oblique.ttf",
    "BI": "DejaVuSans-BoldOblique.ttf",
}

# Paleta institucional SULPAA (verde corporativo #016f46).
_VERDE_OSCURO = (1, 111, 70)
_VERDE_ACENTO = (87, 160, 82)
_TEXTO_OSCURO = (23, 49, 42)
_TEXTO_SUAVE = (95, 103, 99)
_LINEA_SEPARADORA = (208, 219, 210)
_FONDO_FILA = (246, 250, 243)


def registrar_fuentes(pdf):
    """Registra las variantes DejaVu Sans en un documento fpdf2."""
    for estilo, archivo in _VARIANTES.items():
        pdf.add_font(
            _FAMILIA,
            estilo,
            str(RUTA_FUENTES / archivo),
        )
    return pdf


class PdfReporteUnicode(FPDF):
    """Documento PDF con la identidad institucional de SULPAA.

    Aplica la base visual común a los reportes gerenciales: encabezado
    con logo y datos institucionales, tabla con wrapping real y pie de
    página con la numeración y el origen del documento.
    """

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=18)
        registrar_fuentes(self)
        self._titulo = ""
        self._rango = ""

    # ------------------------------------------------------------
    # Identidad del documento
    # ------------------------------------------------------------

    def encabezado_institucional(self, titulo, rango=""):
        """Define el título (y rango opcional) del reporte actual.

        El rango suele ser ``"Período: 01/01/2026 - 31/01/2026"``.
        """
        self._titulo = _normalizar(titulo)
        self._rango = _normalizar(rango)
        self.add_page()

    def header(self):
        """Encabezado institucional repetido en cada página."""
        if self.page_no() < 1:
            return
        self.set_font(_FAMILIA, "", 7)
        margen = 10
        ancho = self.w - margen * 2

        logo_ancho = 12
        logo_altura = 12
        hay_logo = RUTA_LOGO.is_file()
        if hay_logo:
            try:
                self.image(str(RUTA_LOGO), margen, 7, logo_ancho)
            except Exception:
                hay_logo = False

        x_texto = margen + (logo_ancho + 4 if hay_logo else 0)
        texto_ancho = ancho - (logo_ancho + 4 if hay_logo else 0)

        self.set_xy(x_texto, 6)
        self.set_font(_FAMILIA, "B", 10)
        self.set_text_color(*_VERDE_OSCURO)
        self.cell(texto_ancho, 6, "CORPORACIÓN SULPAA S.A.C.",
                  new_x=XPos.LMARGIN,
                  new_y=YPos.NEXT)

        self.set_x(x_texto)
        self.set_font(_FAMILIA, "B", 14)
        self.set_text_color(*_TEXTO_OSCURO)
        self.cell(texto_ancho, 7, self._titulo,
                  new_x=XPos.LMARGIN,
                  new_y=YPos.NEXT)

        self.set_x(x_texto)
        self.set_font(_FAMILIA, "", 7)
        self.set_text_color(*_TEXTO_SUAVE)
        self.write(3, self._rango or "Reporte gerencial")
        self.set_text_color(*_TEXTO_SUAVE)
        self.write(
            3,
            f"  ·  Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        )

        self.set_draw_color(*_LINEA_SEPARADORA)
        self.set_line_width(0.4)
        self.line(margen, 21, self.w - margen, 21)

    def footer(self):
        """Pie institucional: origen del documento y página actual."""
        if self.page_no() < 1:
            return
        self.set_y(-15)
        self.set_font(_FAMILIA, "", 7)
        self.set_text_color(*_TEXTO_SUAVE)
        ancho = self.w - 20
        self.cell(
            ancho,
            8,
            "SULPAA V2 · Corporación Sulpaa S.A.C. · Documento generado por el sistema",
            align="L",
        )
        self.cell(ancho, 8, f"Página {self.page_no()}", align="R")

    # ------------------------------------------------------------
    # Tablas con wrapping real
    # ------------------------------------------------------------

    def tabla(self, columnas, filas, col_anchos=None, alineaciones=None):
        """Tabla profesional con altura de fila dinámica y wrapping real.

        Usa la API ``table()`` de fpdf2: los textos se dividen en varias
        líneas dentro de su columna (por anchos configurados por
        ``col_anchos``), el encabezado se repite en cada página y los
        números se alinean a la derecha según ``alineaciones``.

        Medidas en milímetros sobre el ancho útil del A4 (190 mm).
        """
        ancho = self.w - 20
        n = max(len(columnas), 1)
        if not col_anchos:
            base = ancho / n
            col_anchos = [base] * n
        factor = ancho / sum(col_anchos)
        col_anchos = [valor * factor for valor in col_anchos]
        if not alineaciones:
            alineaciones = ["L"] * n

        from fpdf.fonts import FontFace

        self.set_font(_FAMILIA, "", 8)
        with self.table(
            col_widths=col_anchos,
            headings_style=FontFace(
                family=_FAMILIA,
                emphasis="BOLD",
                color=(255, 255, 255),
                fill_color=_VERDE_OSCURO,
            ),
            line_height=5.5,
            text_align="L",
            borders_layout="ALL",
            width=ancho,
            first_row_as_headings=True,
            repeat_headings=True,
        ) as tabla:
            fila_encabezado = tabla.row()
            for i, columna in enumerate(columnas):
                fila_encabezado.cell(
                    _normalizar(columna), align=alineaciones[i] or "L"
                )
            for indice, fila in enumerate(filas):
                fila_datos = tabla.row()
                for i, celda in enumerate(fila):
                    fila_datos.cell(
                        _normalizar(str(celda)),
                        align=alineaciones[i] or "L",
                        style=(
                            FontFace(fill_color=_FONDO_FILA)
                            if indice % 2 == 1 else None
                        ),
                    )

    def anexo(self, etiqueta, valor, nota=None):
        """Resumen o anexo posterior a la tabla con jerarquía visual."""
        self.ln(6)
        self.set_font(_FAMILIA, "B", 10)
        self.set_text_color(*_VERDE_OSCURO)
        self.cell(0, 8, _normalizar(f"{etiqueta}: {valor}"), ln=True)
        if nota:
            self.set_font(_FAMILIA, "", 9)
            self.set_text_color(*_TEXTO_OSCURO)
            self.multi_cell(0, 6, _normalizar(nota))


def _normalizar(texto):
    """Texto seguro (sin transformación, se conserva el Unicode real)."""
    return str(texto or "")
