from datetime import date
from decimal import Decimal

import pytest

from app.services.einvoice_pdf import (
    EInvoicePdfData,
    normalize_einvoice_data,
    render_einvoice_pdf,
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


def test_render_einvoice_pdf_valid_bytes():
    pdf_bytes = render_einvoice_pdf(
        supplier_name="Tenaga Nasional Berhad",
        supplier_tin="C1234567890",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="TNB-2026-88213",
        issue_date="2026-08-10",
        currency="MYR",
        tax_type="SST",
        tax_rate="6%",
        total_amount="1240.00",
        status="validated",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_render_einvoice_pdf_from_full_schema(sample_full_invoice_payload):
    pdf_bytes = render_einvoice_pdf(sample_full_invoice_payload)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_render_einvoice_pdf_missing_optional_fields():
    pdf_bytes = render_einvoice_pdf(
        supplier_name="Simple Vendor",
        supplier_tin=None,
        buyer_name=None,
        invoice_no="SMP-001",
        issue_date="2026-08-11",
        currency="MYR",
        tax_type=None,
        tax_rate=None,
        total_amount="500.00",
        status="review",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_render_einvoice_pdf_multi_item_and_shipping(sample_full_invoice_payload):
    payload = dict(sample_full_invoice_payload)
    payload["shipping_recipient"] = {
        "name": "FINBRAIN Logistics Center",
        "address": "Port Klang Free Zone, 42000 Selangor",
        "tin": "C9876543210",
        "registration_no": "202401012345",
    }
    payload["document"]["currency_code"] = "USD"
    payload["document"]["exchange_rate"] = 4.45
    payload["document"]["original_einvoice_ref"] = "INV-2026-000"
    payload["line_items"] = [
        {
            "description": "Server Hosting & Cloud Storage Q3",
            "classification_code": "002",
            "quantity": 2,
            "unit_of_measure": "Month",
            "unit_price": 500.00,
            "discount_rate": 5,
            "discount_amount": 50.00,
            "tax_type": "SST",
            "tax_rate": 6.0,
            "tax_amount": 57.00,
            "tax_exemption_details": None,
            "amount_exempted": None,
            "line_subtotal": 1007.00,
        },
        {
            "description": "Premium 24/7 SLA Support Tier",
            "classification_code": "003",
            "quantity": 1,
            "unit_of_measure": "Month",
            "unit_price": 200.00,
            "discount_rate": 0,
            "discount_amount": 0.00,
            "tax_type": "SST",
            "tax_rate": 6.0,
            "tax_amount": 12.00,
            "tax_exemption_details": None,
            "amount_exempted": None,
            "line_subtotal": 212.00,
        },
    ]
    pdf_bytes = render_einvoice_pdf(payload)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_seed_module_reexport_compatibility():
    from seed.generate_einvoice_pdf import render_einvoice_pdf as seed_render

    pdf_bytes = seed_render(
        supplier_name="Grab Malaysia",
        supplier_tin="C9988776655",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="GRB-4471209",
        issue_date="2026-08-09",
        currency="MYR",
        tax_type="SST",
        tax_rate="0%",
        total_amount="86.40",
        status="submitted",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_einvoice_record_pdf_route():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.auth.dependencies import get_current_user
    from app.db import get_db
    from app.models import Base, EInvoiceRecord
    from app.routes.einvoice import router
    from app.schemas import UserRole
    from tests.auth_support import principal

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    record = EInvoiceRecord(
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
    db.add(record)
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: principal(UserRole.FINANCE_OPS)

    client = TestClient(app)
    response = client.get(f"/einvoice-records/{record.id}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")

    doc_response = client.get(f"/einvoice-readiness/{record.id}/document")
    assert doc_response.status_code == 200
    data = doc_response.json()
    assert "url" in data


def test_render_payment_receipt_pdf_valid_bytes():
    from app.services.einvoice_pdf import render_payment_receipt_pdf
    receipt_bytes = render_payment_receipt_pdf(
        supplier_name="Tenaga Nasional Berhad",
        supplier_tin="C1234567890",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="TNB-2026-88213",
        issue_date="2026-08-10",
        paid_at="2026-08-15",
        currency="MYR",
        total_amount="1240.00",
        uin="MY29A8F1Q3RT",
    )
    assert isinstance(receipt_bytes, bytes)
    assert receipt_bytes.startswith(b"%PDF-")
    assert len(receipt_bytes) > 1000


def test_einvoice_receipt_pdf_route():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.auth.dependencies import get_current_user
    from app.db import get_db
    from app.models import Base, EInvoiceRecord
    from app.routes.einvoice import router
    from app.schemas import UserRole
    from tests.auth_support import principal

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    record = EInvoiceRecord(
        supplier_name="Tenaga Nasional Berhad",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="TNB-2026-88213",
        issue_date=date(2026, 8, 10),
        paid_at=date(2026, 8, 15),
        currency="MYR",
        total_amount="1240.00",
        status="validated",
        uin="MY29A8F1Q3RT",
    )
    db.add(record)
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: principal(UserRole.FINANCE_OPS)

    client = TestClient(app)
    response = client.get(f"/einvoice-records/{record.id}/receipt/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")

