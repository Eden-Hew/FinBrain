"""Render a single EInvoiceRecord or dictionary as a LHDN/MyInvois compliant e-Invoice PDF.

Re-exports the core generator from app.services.einvoice_pdf for backwards compatibility.
"""

from app.services.einvoice_pdf import normalize_einvoice_data, render_einvoice_pdf

__all__ = ["render_einvoice_pdf", "normalize_einvoice_data"]
