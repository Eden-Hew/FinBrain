"""Render a single EInvoiceRecord as a realistic-looking Malaysian tax invoice PDF.

Missing fields (no TIN, no buyer name, no tax type) are rendered as a blank line rather than
an explicit "missing" label, matching how an actual under-specified invoice would look.
"""
import io
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _field(value: str | None) -> str:
    return value if value else "—"


def render_einvoice_pdf(
    *,
    supplier_name: str,
    supplier_tin: str | None,
    buyer_name: str | None,
    invoice_no: str | None,
    issue_date: str,
    currency: str | None,
    tax_type: str | None,
    tax_rate: str | None,
    total_amount: Decimal | str,
    status: str,
) -> bytes:
    buf = io.BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buf, pagesize=A4)

    margin = 20 * mm
    y = page_h - margin

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, supplier_name)
    c.setFont("Helvetica", 9)
    c.drawRightString(page_w - margin, y, "TAX INVOICE")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, f"Supplier TIN: {_field(supplier_tin)}")
    y -= 10 * mm

    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.line(margin, y, page_w - margin, y)
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Bill To")
    c.drawString(page_w / 2, y, "Invoice Details")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(margin, y, _field(buyer_name))
    c.drawString(page_w / 2, y, f"Invoice No: {_field(invoice_no)}")
    y -= 5.5 * mm
    c.drawString(page_w / 2, y, f"Issue Date: {issue_date}")
    y -= 5.5 * mm
    c.drawString(page_w / 2, y, f"Currency: {_field(currency)}")
    y -= 5.5 * mm
    tax_line = f"{_field(tax_type)}" + (f" ({tax_rate})" if tax_type and tax_rate else "")
    c.drawString(page_w / 2, y, f"Tax Type: {tax_line}")
    y -= 15 * mm

    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.line(margin, y, page_w - margin, y)
    y -= 12 * mm

    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, y, "Total Amount")
    amount_label = f"{_field(currency) if currency else 'RM'} {total_amount}"
    c.drawRightString(page_w - margin, y, amount_label)
    y -= 10 * mm

    c.setFont("Helvetica-Oblique", 9)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(margin, y, f"Status: {status}")

    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.55, 0.55, 0.55)
    c.drawString(margin, margin, "Generated demo document — FinBrain OS e-Invoice Readiness")

    c.showPage()
    c.save()
    return buf.getvalue()
