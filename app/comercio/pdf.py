"""Generación Unicode en memoria de la constancia informativa de compra."""

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from app.admin.reportes.pdf import RUTA_LOGO, registrar_fuentes


FAMILIA = "DejaVuSans"
VERDE = (1, 111, 70)
VERDE_CLARO = (236, 247, 240)
TEXTO = (28, 49, 42)
SUAVE = (91, 105, 99)
LINEA = (207, 221, 212)
ALERTA_FONDO = (255, 244, 214)
ALERTA_TEXTO = (111, 76, 0)
ADVERTENCIA = (
    "Documento informativo. No constituye comprobante de pago electrónico "
    "válido ante SUNAT."
)


def _texto(valor):
    return str(valor or "")


def _dinero(valor):
    return f"S/ {float(valor or 0):,.2f}"


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y %H:%M")
    return _texto(valor) or "No disponible"


class ConstanciaCompraPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=20)
        registrar_fuentes(self)
        self.set_title("Constancia de compra SULPAA")
        self.set_author("Corporación Sulpaa S.A.C.")
        self.set_creator("SULPAA V2")

    def header(self):
        if self.page_no() < 1:
            return
        if RUTA_LOGO.is_file():
            try:
                self.image(str(RUTA_LOGO), 12, 8, 14)
            except Exception:
                pass
        self.set_xy(30, 8)
        self.set_font(FAMILIA, "B", 11)
        self.set_text_color(*VERDE)
        self.cell(0, 5, "SULPAA", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(30)
        self.set_font(FAMILIA, "", 7.5)
        self.set_text_color(*SUAVE)
        self.cell(0, 4, "Corporación Sulpaa S.A.C.")
        self.set_draw_color(*LINEA)
        self.line(12, 24, 198, 24)
        self.set_y(29)

    def footer(self):
        self.set_y(-16)
        self.set_font(FAMILIA, "", 6.8)
        self.set_text_color(*SUAVE)
        self.cell(0, 4, "SULPAA V2 · Constancia generada bajo demanda", align="L")
        self.set_y(-16)
        self.cell(0, 4, f"Página {self.page_no()}", align="R")

    def seccion(self, titulo):
        self.ln(5)
        self.set_font(FAMILIA, "B", 10)
        self.set_text_color(*VERDE)
        self.cell(0, 6, titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def campo(self, etiqueta, valor):
        if valor in (None, ""):
            return
        self.set_font(FAMILIA, "B", 8)
        self.set_text_color(*SUAVE)
        self.cell(42, 5, etiqueta)
        self.set_font(FAMILIA, "", 8.5)
        self.set_text_color(*TEXTO)
        self.multi_cell(0, 5, _texto(valor), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generar_pdf_constancia(datos):
    pdf = ConstanciaCompraPDF()
    pdf.add_page()

    pdf.set_font(FAMILIA, "B", 19)
    pdf.set_text_color(*TEXTO)
    pdf.cell(0, 9, "CONSTANCIA DE COMPRA", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(FAMILIA, "", 9)
    pdf.set_text_color(*SUAVE)
    pdf.cell(
        0, 5, f"Pedido {_texto(datos.get('numero_pedido'))}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )

    pdf.ln(4)
    pdf.set_fill_color(*ALERTA_FONDO)
    pdf.set_text_color(*ALERTA_TEXTO)
    pdf.set_font(FAMILIA, "B", 8.5)
    pdf.multi_cell(
        0, 6, ADVERTENCIA, border=1, fill=True,
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )

    pdf.seccion("Información de la compra")
    pdf.campo("Número de pedido", datos.get("numero_pedido"))
    pdf.campo("Fecha", _fecha(datos.get("fecha")))
    pdf.campo("Cliente", datos.get("cliente"))
    pdf.campo("Estado", datos.get("estado"))
    pdf.campo("Método de pago", datos.get("metodo_pago"))
    pdf.campo("Modalidad", datos.get("modalidad_pago"))

    pdf.seccion("Productos adquiridos")
    filas = []
    for producto in datos.get("productos") or []:
        filas.append((
            _texto(producto.get("nombre")),
            str(int(producto.get("cantidad") or 0)),
            _dinero(producto.get("precio_unitario")),
            _dinero(producto.get("subtotal")),
        ))

    pdf.set_font(FAMILIA, "", 8)
    with pdf.table(
        col_widths=(100, 20, 32, 32),
        headings_style=FontFace(
            family=FAMILIA, emphasis="BOLD", color=(255, 255, 255),
            fill_color=VERDE,
        ),
        line_height=5.5,
        borders_layout="ALL",
        repeat_headings=True,
        width=186,
    ) as tabla:
        encabezado = tabla.row()
        for valor, alineacion in (
            ("Producto", "L"), ("Cant.", "C"),
            ("P. unitario", "R"), ("Subtotal", "R"),
        ):
            encabezado.cell(valor, align=alineacion)
        for fila in filas:
            row = tabla.row()
            row.cell(fila[0], align="L")
            row.cell(fila[1], align="C")
            row.cell(fila[2], align="R")
            row.cell(fila[3], align="R")

    pdf.ln(4)
    pdf.set_x(112)
    for etiqueta, valor, destacado in (
        ("Subtotal", datos.get("subtotal"), False),
        ("Descuento", datos.get("descuento"), False),
        ("Entrega", datos.get("costo_entrega"), False),
        ("TOTAL", datos.get("total"), True),
    ):
        pdf.set_x(112)
        pdf.set_font(FAMILIA, "B" if destacado else "", 9.5)
        pdf.set_text_color(*(VERDE if destacado else TEXTO))
        pdf.cell(43, 6, etiqueta)
        pdf.cell(43, 6, _dinero(valor), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    entrega = datos.get("entrega")
    if entrega:
        pdf.seccion("Entrega")
        pdf.campo("Modalidad", entrega.get("tipo"))
        pdf.campo("Estado", entrega.get("estado"))
        pdf.campo("Destino", entrega.get("destino"))
        pdf.campo("Dirección", entrega.get("direccion"))
        pdf.campo("Referencia", entrega.get("referencia"))
        pdf.campo("Transportista", entrega.get("transportista"))
        pdf.campo("Servicio", entrega.get("servicio"))

    pdf.ln(6)
    pdf.set_fill_color(*VERDE_CLARO)
    pdf.set_text_color(*TEXTO)
    pdf.set_font(FAMILIA, "", 8)
    pdf.multi_cell(
        0, 5.5,
        "Gracias por tu compra. Conserva esta constancia para consultar los "
        "datos informativos de tu pedido en SULPAA.",
        fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )

    return bytes(pdf.output())
