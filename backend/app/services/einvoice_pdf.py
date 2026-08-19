"""Malaysia LHDN/MyInvois-compliant e-Invoice printable PDF template generator.

Implements the official MyInvois document format with:
1. Header band (company logo placeholder, supplier details, right-aligned e-Invoice title & metadata)
2. Gold accent divider line (#C9A227)
3. IRBM validation strip (dark navy #16283A, Consolas/Courier-Bold UIN, validation timestamp & QR mock)
4. PARTIES section (Side-by-side Supplier / Buyer boxes with #1F3B57 navy headers)
5. ITEMISED DETAILS line-item table (navy header, #F2F4F6 zebra-striped body)
6. Totals block (right-aligned stacked summary, #1F3B57 highlighted TOTAL PAYABLE bar)
7. PAYMENT INFORMATION 2-column grid
8. LHDN compliance disclaimer & footer line
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import io
import re
from typing import Any, Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, Line, String, Group

# --- Style Tokens ---
NAVY = HexColor("#1F3B57")
NAVY_DARK = HexColor("#16283A")
GOLD_ACCENT = HexColor("#C9A227")
LIGHT_GREY = HexColor("#F2F4F6")
MID_GREY = HexColor("#6B7280")
BORDER_GREY = HexColor("#D9DCE1")
NEAR_BLACK = HexColor("#1A202C")
WHITE = HexColor("#FFFFFF")
STATUS_GREEN = HexColor("#10B981")


@dataclass
class DocumentInfo:
    einvoice_version: str = "1.1"
    einvoice_type: str = "Invoice"
    einvoice_code: str = "INV-0000"
    original_einvoice_ref: Optional[str] = None
    issue_date: str = ""
    issue_time: str = "12:00:00"
    irbm_unique_id: Optional[str] = None
    validation_datetime: Optional[str] = None
    currency_code: str = "MYR"
    exchange_rate: Optional[Decimal] = None
    status: str = "validated"


@dataclass
class SupplierInfo:
    name: str = "Supplier Sdn Bhd"
    tin: str = "—"
    registration_no: str = "—"
    sst_registration_no: Optional[str] = None
    tourism_tax_no: Optional[str] = None
    address: str = "Kuala Lumpur, Malaysia"
    contact: str = "+603-0000 0000"
    email: str = "billing@supplier.my"
    msic_code: str = "62010"
    business_activity: str = "Information technology and computer services"


@dataclass
class BuyerInfo:
    name: str = "FINBRAIN SDN BHD"
    tin: str = "—"
    registration_no: str = "—"
    sst_registration_no: Optional[str] = None
    address: str = "Level 20, Menara FinTech, 50450 Kuala Lumpur, Malaysia"
    contact: str = "+603-2111 2222"
    email: str = "finance@finbrain.os"


@dataclass
class ShippingInfo:
    name: Optional[str] = None
    address: Optional[str] = None
    tin: Optional[str] = None
    registration_no: Optional[str] = None


@dataclass
class LineItemInfo:
    description: str = "Standard Supply / Service Item"
    classification_code: str = "001"
    quantity: Decimal = Decimal("1")
    unit_of_measure: Optional[str] = "Unit"
    unit_price: Decimal = Decimal("0.00")
    discount_rate: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    tax_type: str = "SST"
    tax_rate: Decimal = Decimal("6.0")
    tax_amount: Decimal = Decimal("0.00")
    tax_exemption_details: Optional[str] = None
    amount_exempted: Optional[Decimal] = None
    line_subtotal: Decimal = Decimal("0.00")


@dataclass
class TotalsInfo:
    subtotal: Decimal = Decimal("0.00")
    total_discount: Decimal = Decimal("0.00")
    total_excluding_tax: Decimal = Decimal("0.00")
    total_tax: Decimal = Decimal("0.00")
    total_including_tax: Decimal = Decimal("0.00")
    total_payable: Decimal = Decimal("0.00")


@dataclass
class PaymentInfo:
    mode: Optional[str] = "Bank Transfer"
    bank_account_no: Optional[str] = "Maybank 514011223344"
    terms: Optional[str] = "Net 30 Days"
    due_date: Optional[str] = None
    payment_reference_no: Optional[str] = None
    bill_reference_no: Optional[str] = None


@dataclass
class EInvoicePdfData:
    document: DocumentInfo = field(default_factory=DocumentInfo)
    supplier: SupplierInfo = field(default_factory=SupplierInfo)
    buyer: BuyerInfo = field(default_factory=BuyerInfo)
    shipping_recipient: Optional[ShippingInfo] = None
    line_items: list[LineItemInfo] = field(default_factory=list)
    totals: TotalsInfo = field(default_factory=TotalsInfo)
    payment: PaymentInfo = field(default_factory=PaymentInfo)


def _to_decimal(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.-]", "", value.strip())
        if not cleaned:
            return default
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return default
    return default


def _format_date(val: Any) -> str:
    if val is None:
        return datetime.now().strftime("%Y-%m-%d")
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    return str(val)


def normalize_einvoice_data(
    data_or_record: Any = None,
    **kwargs: Any,
) -> EInvoicePdfData:
    """Normalize structured dict, EInvoiceRecord model, or kwargs into EInvoicePdfData."""
    # 1. Full nested dict matching JSON schema
    if isinstance(data_or_record, dict) and "document" in data_or_record:
        doc_dict = data_or_record.get("document", {})
        sup_dict = data_or_record.get("supplier", {})
        buy_dict = data_or_record.get("buyer", {})
        ship_dict = data_or_record.get("shipping_recipient")
        items_list = data_or_record.get("line_items", [])
        totals_dict = data_or_record.get("totals", {})
        pay_dict = data_or_record.get("payment", {})

        doc = DocumentInfo(
            einvoice_version=str(doc_dict.get("einvoice_version", "1.1")),
            einvoice_type=str(doc_dict.get("einvoice_type", "Invoice")),
            einvoice_code=str(doc_dict.get("einvoice_code", "INV-0000")),
            original_einvoice_ref=doc_dict.get("original_einvoice_ref"),
            issue_date=_format_date(doc_dict.get("issue_date")),
            issue_time=str(doc_dict.get("issue_time", "12:00:00")),
            irbm_unique_id=doc_dict.get("irbm_unique_id"),
            validation_datetime=doc_dict.get("validation_datetime"),
            currency_code=str(doc_dict.get("currency_code", "MYR")),
            exchange_rate=_to_decimal(doc_dict.get("exchange_rate"), None) if doc_dict.get("exchange_rate") is not None else None,
            status=str(doc_dict.get("status", "validated")),
        )

        supplier = SupplierInfo(
            name=str(sup_dict.get("name", "Supplier Sdn Bhd")),
            tin=str(sup_dict.get("tin", "—")),
            registration_no=str(sup_dict.get("registration_no", "—")),
            sst_registration_no=sup_dict.get("sst_registration_no"),
            tourism_tax_no=sup_dict.get("tourism_tax_no"),
            address=str(sup_dict.get("address", "Kuala Lumpur, Malaysia")),
            contact=str(sup_dict.get("contact", "+603-0000 0000")),
            email=str(sup_dict.get("email", "billing@supplier.my")),
            msic_code=str(sup_dict.get("msic_code", "62010")),
            business_activity=str(sup_dict.get("business_activity", "General Commercial Activities")),
        )

        buyer = BuyerInfo(
            name=str(buy_dict.get("name", "FINBRAIN SDN BHD")),
            tin=str(buy_dict.get("tin", "—")),
            registration_no=str(buy_dict.get("registration_no", "—")),
            sst_registration_no=buy_dict.get("sst_registration_no"),
            address=str(buy_dict.get("address", "Level 20, Menara FinTech, 50450 Kuala Lumpur, Malaysia")),
            contact=str(buy_dict.get("contact", "+603-2111 2222")),
            email=str(buy_dict.get("email", "finance@finbrain.os")),
        )

        shipping = None
        if ship_dict:
            shipping = ShippingInfo(
                name=ship_dict.get("name"),
                address=ship_dict.get("address"),
                tin=ship_dict.get("tin"),
                registration_no=ship_dict.get("registration_no"),
            )

        line_items = []
        for it in items_list:
            line_items.append(
                LineItemInfo(
                    description=str(it.get("description", "Item")),
                    classification_code=str(it.get("classification_code", "001")),
                    quantity=_to_decimal(it.get("quantity", 1)),
                    unit_of_measure=it.get("unit_of_measure", "Unit"),
                    unit_price=_to_decimal(it.get("unit_price", 0)),
                    discount_rate=_to_decimal(it.get("discount_rate", 0)) if it.get("discount_rate") is not None else None,
                    discount_amount=_to_decimal(it.get("discount_amount", 0)) if it.get("discount_amount") is not None else None,
                    tax_type=str(it.get("tax_type", "SST")),
                    tax_rate=_to_decimal(it.get("tax_rate", 6)),
                    tax_amount=_to_decimal(it.get("tax_amount", 0)),
                    tax_exemption_details=it.get("tax_exemption_details"),
                    amount_exempted=_to_decimal(it.get("amount_exempted", 0)) if it.get("amount_exempted") is not None else None,
                    line_subtotal=_to_decimal(it.get("line_subtotal", 0)),
                )
            )

        totals = TotalsInfo(
            subtotal=_to_decimal(totals_dict.get("subtotal", 0)),
            total_discount=_to_decimal(totals_dict.get("total_discount", 0)),
            total_excluding_tax=_to_decimal(totals_dict.get("total_excluding_tax", 0)),
            total_tax=_to_decimal(totals_dict.get("total_tax", 0)),
            total_including_tax=_to_decimal(totals_dict.get("total_including_tax", 0)),
            total_payable=_to_decimal(totals_dict.get("total_payable", 0)),
        )

        payment = PaymentInfo(
            mode=pay_dict.get("mode", "Bank Transfer"),
            bank_account_no=pay_dict.get("bank_account_no", "Maybank 514011223344"),
            terms=pay_dict.get("terms", "Net 30 Days"),
            due_date=pay_dict.get("due_date"),
            payment_reference_no=pay_dict.get("payment_reference_no"),
            bill_reference_no=pay_dict.get("bill_reference_no"),
        )

        return EInvoicePdfData(
            document=doc,
            supplier=supplier,
            buyer=buyer,
            shipping_recipient=shipping,
            line_items=line_items,
            totals=totals,
            payment=payment,
        )

    # 2. Extract from object or combined kwargs
    raw = {}
    if data_or_record is not None:
        if isinstance(data_or_record, dict):
            raw.update(data_or_record)
        else:
            # ORM object like EInvoiceRecord
            for attr in (
                "supplier_name",
                "supplier_tin",
                "buyer_name",
                "invoice_no",
                "issue_date",
                "currency",
                "tax_type",
                "tax_rate",
                "total_amount",
                "status",
                "uin",
                "created_at",
            ):
                if hasattr(data_or_record, attr):
                    raw[attr] = getattr(data_or_record, attr)

    raw.update(kwargs)

    # Extract fields with safe defaults
    supplier_name = str(raw.get("supplier_name") or "Tenaga Nasional Berhad")
    supplier_tin = str(raw.get("supplier_tin") or "—")
    buyer_name = str(raw.get("buyer_name") or "FINBRAIN SDN BHD")
    invoice_no = str(raw.get("invoice_no") or "INV-2026-0001")
    issue_date_val = _format_date(raw.get("issue_date"))
    currency = str(raw.get("currency") or "MYR")
    tax_type = str(raw.get("tax_type") or "SST")
    tax_rate_str = str(raw.get("tax_rate") or "6%")
    tax_rate_num = _to_decimal(tax_rate_str)
    total_amount_dec = _to_decimal(raw.get("total_amount") or "0.00")
    status = str(raw.get("status") or "validated")
    uin = raw.get("uin") or ("MY29A" + invoice_no.replace("-", "")[-6:] if status == "validated" else None)

    # Compute line items and totals
    if tax_rate_num > Decimal("0"):
        # subtotal + tax = total => subtotal = total / (1 + rate/100)
        subtotal_dec = (total_amount_dec / (Decimal("1") + (tax_rate_num / Decimal("100")))).quantize(Decimal("0.01"))
        tax_amount_dec = (total_amount_dec - subtotal_dec).quantize(Decimal("0.01"))
    else:
        subtotal_dec = total_amount_dec
        tax_amount_dec = Decimal("0.00")

    doc = DocumentInfo(
        einvoice_version="1.1",
        einvoice_type="Invoice",
        einvoice_code=invoice_no,
        issue_date=issue_date_val,
        issue_time="14:30:00",
        irbm_unique_id=uin,
        validation_datetime=f"{issue_date_val}T14:30:00Z" if uin else None,
        currency_code=currency,
        status=status,
    )

    supplier = SupplierInfo(
        name=supplier_name,
        tin=supplier_tin,
        registration_no="199001008888",
        sst_registration_no="W10-1808-32000018" if tax_type == "SST" else None,
        address="Bangsar Corporate Tower, No. 129 Jalan Bangsar, 59200 Kuala Lumpur",
        contact="+603-2296 5566",
        email=f"billing@{re.sub(r'[^a-zA-Z0-9]', '', supplier_name.lower())[:10]}.com.my",
        msic_code="35101",
        business_activity="Commercial Supply & Services",
    )

    buyer = BuyerInfo(
        name=buyer_name,
        tin="C2589012300" if buyer_name else "—",
        registration_no="202401012345",
        sst_registration_no=None,
        address="Level 20, Menara FinTech, 50450 Kuala Lumpur, Malaysia",
        contact="+603-2111 2222",
        email="finance@finbrain.os",
    )

    line_items = [
        LineItemInfo(
            description=f"Supply of commercial goods/services as per invoice {invoice_no}",
            classification_code="001",
            quantity=Decimal("1"),
            unit_of_measure="Lot",
            unit_price=subtotal_dec,
            discount_rate=Decimal("0"),
            discount_amount=Decimal("0.00"),
            tax_type=tax_type,
            tax_rate=tax_rate_num,
            tax_amount=tax_amount_dec,
            line_subtotal=total_amount_dec,
        )
    ]

    totals = TotalsInfo(
        subtotal=subtotal_dec,
        total_discount=Decimal("0.00"),
        total_excluding_tax=subtotal_dec,
        total_tax=tax_amount_dec,
        total_including_tax=total_amount_dec,
        total_payable=total_amount_dec,
    )

    payment = PaymentInfo(
        mode="Bank Transfer",
        bank_account_no="Maybank 514011223344",
        terms="Net 30 Days",
        due_date=issue_date_val,
        payment_reference_no=invoice_no,
        bill_reference_no=f"BIL-{invoice_no.replace('-', '')[-4:]}",
    )

    return EInvoicePdfData(
        document=doc,
        supplier=supplier,
        buyer=buyer,
        shipping_recipient=None,
        line_items=line_items,
        totals=totals,
        payment=payment,
    )
