from decimal import Decimal
from datetime import date
import pytest

from app.services.einvoice_pdf import (
    normalize_einvoice_data,
    EInvoicePdfData,
    DocumentInfo,
    SupplierInfo,
    BuyerInfo,
    LineItemInfo,
    TotalsInfo,
    PaymentInfo,
)


@pytest.fixture
def sample_full_invoice_payload():
    return {
        "document": {
            "einvoice_version": "1.1",
            "einvoice_type": "Invoice",
            "einvoice_code": "INV-2026-001",
            "original_einvoice_ref": None,
            "issue_date": "2026-08-19",
            "issue_time": "14:30:00",
            "irbm_unique_id": "MY29A123456",
            "validation_datetime": "2026-08-19T14:35:00Z",
            "currency_code": "MYR",
            "exchange_rate": None,
        },
        "supplier": {
            "name": "Tenaga Nasional Berhad",
            "tin": "C1234567890",
            "registration_no": "199001009999",
            "sst_registration_no": "W10-1808-32000018",
            "tourism_tax_no": None,
            "address": "No. 129, Jalan Bangsar, 59200 Kuala Lumpur",
            "contact": "+603-2296 5566",
            "email": "billing@tnb.com.my",
            "msic_code": "35101",
            "business_activity": "Electric power generation, transmission and distribution",
        },
        "buyer": {
            "name": "FINBRAIN SDN BHD",
            "tin": "C9876543210",
            "registration_no": "202401012345",
            "sst_registration_no": None,
            "address": "Level 20, Menara FinTech, 50450 Kuala Lumpur",
            "contact": "+603-2111 2222",
            "email": "finance@finbrain.os",
        },
        "shipping_recipient": None,
        "line_items": [
            {
                "description": "Commercial Electricity Tariff C1 (Peak/Off-Peak)",
                "classification_code": "001",
                "quantity": 1,
                "unit_of_measure": "kWh",
                "unit_price": 1169.81,
                "discount_rate": 0,
                "discount_amount": 0,
                "tax_type": "SST",
                "tax_rate": 6.0,
                "tax_amount": 70.19,
                "tax_exemption_details": None,
                "amount_exempted": None,
                "line_subtotal": 1240.00,
            }
        ],
        "totals": {
            "subtotal": 1169.81,
            "total_discount": 0.00,
            "total_excluding_tax": 1169.81,
            "total_tax": 70.19,
            "total_including_tax": 1240.00,
            "total_payable": 1240.00,
        },
        "payment": {
            "mode": "Bank Transfer",
            "bank_account_no": "Maybank 514011223344",
            "terms": "Net 30 Days",
            "due_date": "2026-09-18",
            "payment_reference_no": "PAY-88213",
            "bill_reference_no": "BIL-9910",
        },
    }


def test_normalize_full_dict_schema(sample_full_invoice_payload):
    normalized = normalize_einvoice_data(sample_full_invoice_payload)
    assert isinstance(normalized, EInvoicePdfData)
    assert normalized.document.einvoice_code == "INV-2026-001"
    assert normalized.supplier.name == "Tenaga Nasional Berhad"
    assert normalized.supplier.tin == "C1234567890"
    assert normalized.buyer.name == "FINBRAIN SDN BHD"
    assert len(normalized.line_items) == 1
    assert normalized.totals.total_payable == Decimal("1240.00")
    assert normalized.payment.mode == "Bank Transfer"


def test_normalize_legacy_kwargs_record():
    normalized = normalize_einvoice_data(
        supplier_name="Tenaga Nasional Berhad",
        supplier_tin="C1234567890",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="TNB-2026-88213",
        issue_date=date(2026, 8, 10),
        currency="MYR",
        tax_type="SST",
        tax_rate="6%",
        total_amount="1240.00",
        status="validated",
    )
    assert isinstance(normalized, EInvoicePdfData)
    assert normalized.supplier.name == "Tenaga Nasional Berhad"
    assert normalized.buyer.name == "FINBRAIN Sdn Bhd"
    assert normalized.document.einvoice_code == "TNB-2026-88213"
    assert normalized.totals.total_payable == Decimal("1240.00")
    assert len(normalized.line_items) == 1
