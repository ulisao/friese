"""PDF de QRs de productos para imprimir y pegar en la góndola (tarea 11.5).

El QR se dibuja módulo por módulo con `pdf.rect()`, no como imagen: `qrcode` da
la matriz de módulos (`QRCode.get_matrix()`) sin pasar por ningún factory de
imagen, así que no hace falta convertirla a PNG/SVG antes de meterla en el PDF
(mismo motivo que en `users/invites.py` para el QR de la invitación: un
cuadradito en blanco y negro no necesita una librería de imágenes de por
medio).
"""

import qrcode
from fpdf import FPDF

PAGE_MARGIN_MM = 8
COLUMNS = 3
ROWS = 8
CELL_PADDING_MM = 2


def _qr_matrix(data):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.get_matrix()


def _draw_qr(pdf, matrix, x, y, size):
    modules = len(matrix)
    module_size = size / modules
    pdf.set_fill_color(0, 0, 0)
    for row_index, row in enumerate(matrix):
        for col_index, is_dark in enumerate(row):
            if is_dark:
                pdf.rect(
                    x + col_index * module_size,
                    y + row_index * module_size,
                    module_size,
                    module_size,
                    style="F",
                )


def _draw_label(pdf, product, x, y, cell_w, cell_h):
    pdf.set_draw_color(200, 200, 200)
    pdf.rect(x, y, cell_w, cell_h)

    qr_size = cell_h - 2 * CELL_PADDING_MM
    _qr_data = product.barcode or str(product.id)
    _draw_qr(pdf, _qr_matrix(_qr_data), x + CELL_PADDING_MM, y + CELL_PADDING_MM, qr_size)

    text_x = x + CELL_PADDING_MM + qr_size + CELL_PADDING_MM
    text_w = cell_w - (text_x - x) - CELL_PADDING_MM

    pdf.set_xy(text_x, y + CELL_PADDING_MM)
    pdf.set_font("Helvetica", "B", 8)
    pdf.multi_cell(text_w, 3.2, product.name, align="L")

    pdf.set_xy(text_x, pdf.get_y())
    pdf.set_font("Helvetica", "", 7)
    pdf.multi_cell(text_w, 3, product.get_unit_display(), align="L")

    pdf.set_xy(text_x, y + cell_h - CELL_PADDING_MM - 3)
    pdf.set_font("Helvetica", "", 6)
    pdf.cell(text_w, 3, "Cant. góndola: ______", align="L")


def build_qr_pdf(products):
    """PDF en A4 con un QR por producto, en grilla de `COLUMNS` x `ROWS` por hoja."""
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(False)
    pdf.set_margins(PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM)

    if not products:
        pdf.add_page()
        pdf.set_font("Helvetica", "", 12)
        pdf.set_xy(PAGE_MARGIN_MM, PAGE_MARGIN_MM)
        pdf.cell(0, 10, "No hay productos cargados.")
        return bytes(pdf.output())

    usable_w = pdf.w - 2 * PAGE_MARGIN_MM
    usable_h = pdf.h - 2 * PAGE_MARGIN_MM
    cell_w = usable_w / COLUMNS
    cell_h = usable_h / ROWS
    per_page = COLUMNS * ROWS

    for index, product in enumerate(products):
        position = index % per_page
        if position == 0:
            pdf.add_page()
        row, col = divmod(position, COLUMNS)
        x = PAGE_MARGIN_MM + col * cell_w
        y = PAGE_MARGIN_MM + row * cell_h
        _draw_label(pdf, product, x, y, cell_w, cell_h)

    return bytes(pdf.output())
