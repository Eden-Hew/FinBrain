from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import Base, EInvoiceRecord, WorkflowAuditEntry
from app.routes.einvoice import router
from app.schemas import EInvoiceUpdatePayload, UserRole
from app.services.einvoice_readiness import (
    get_record,
    list_records,
    update_record,
)
from tests.auth_support import TENANT_A, TENANT_B, principal

TENANT_A_STR = str(TENANT_A)
TENANT_B_STR = str(TENANT_B)


def _setup_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_list_records_and_get_record_return_classified_reasons():
    db = _setup_db()
    try:
        # Record missing TIN
        r_review = EInvoiceRecord(
            tenant_id=TENANT_A_STR,
            supplier_name="Office Supplies Sdn Bhd",
            supplier_tin=None,
            buyer_name="FINBRAIN Sdn Bhd",
            invoice_no="OS-1001",
            issue_date=date(2026, 8, 1),
            total_amount=Decimal("500.00"),
            status="review",
            tax_type="SST",
            tax_rate="6%",
        )
        # Compliant record
        r_valid = EInvoiceRecord(
            tenant_id=TENANT_A_STR,
            supplier_name="Tenaga Nasional Berhad",
            supplier_tin="C1234567890",
            buyer_name="FINBRAIN Sdn Bhd",
            invoice_no="TNB-2001",
            issue_date=date(2026, 8, 2),
            total_amount=Decimal("1200.00"),
            status="pending",
            tax_type="SST",
            tax_rate="6%",
        )
        db.add_all([r_review, r_valid])
        db.commit()

        records = list_records(db, TENANT_A_STR)
        assert len(records) == 2

        by_id = {r.id: r for r in records}
        assert "Missing supplier Tax Identification Number" in by_id[r_review.id].readiness_reason
        assert by_id[r_valid.id].readiness_reason == "All required fields present."

        # get_record also returns accurate readiness reason
        single_review = get_record(db, r_review.id, TENANT_A_STR)
        assert "Missing supplier Tax Identification Number" in single_review.readiness_reason

        single_valid = get_record(db, r_valid.id, TENANT_A_STR)
        assert single_valid.readiness_reason == "All required fields present."
    finally:
        db.close()


def test_update_record_resolves_review_status_and_updates_workflow_event():
    db = _setup_db()
    try:
        record = EInvoiceRecord(
            tenant_id=TENANT_A_STR,
            supplier_name="Office Supplies Sdn Bhd",
            supplier_tin=None,
            buyer_name="FINBRAIN Sdn Bhd",
            invoice_no="OS-4471",
            issue_date=date(2026, 8, 7),
            due_date=date(2026, 8, 25),
            currency="MYR",
            tax_type="SST",
            tax_rate="6%",
            total_amount=Decimal("545.90"),
            status="review",
        )
        db.add(record)
        db.commit()

        # Initial check
        initial_resp = get_record(db, record.id, TENANT_A_STR)
        assert initial_resp.status == "review"
        assert "Missing supplier Tax Identification Number" in initial_resp.readiness_reason

        # Update supplier_tin
        payload = EInvoiceUpdatePayload(supplier_tin="C9988776655")
        updated_resp = update_record(
            db,
            record.id,
            payload,
            role=UserRole.FINANCE_OPS,
            actor_ref="finops@finbrain.test",
            tenant_id=TENANT_A_STR,
        )

        assert updated_resp.supplier_tin == "C9988776655"
        assert updated_resp.status == "pending"
        assert updated_resp.readiness_reason == "All required fields present."

        # Verify database record updated
        db.refresh(record)
        assert record.supplier_tin == "C9988776655"
        assert record.status == "pending"

        # Verify workflow audit event written
        events = db.scalars(
            select(WorkflowAuditEntry)
            .where(
                WorkflowAuditEntry.tenant_id == TENANT_A_STR,
                WorkflowAuditEntry.event_type == "einvoice_record_updated",
            )
        ).all()
        assert len(events) >= 1
        event = events[-1]
        assert event.resource_type == "einvoice_record"
        assert event.resource_id == str(record.id)
        assert event.actor_role == UserRole.FINANCE_OPS.value
        assert event.event_payload["supplier_tin"] == "C9988776655"
        assert event.event_payload["status"] == "pending"
    finally:
        db.close()


def test_update_record_updates_all_editable_fields():
    db = _setup_db()
    try:
        record = EInvoiceRecord(
            tenant_id=TENANT_A_STR,
            supplier_name="Old Supplier",
            supplier_tin="C1111111111",
            buyer_name="Old Buyer",
            invoice_no="INV-001",
            issue_date=date(2026, 8, 1),
            due_date=date(2026, 8, 15),
            currency="MYR",
            tax_type="SST",
            tax_rate="6%",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        db.add(record)
        db.commit()

        payload = EInvoiceUpdatePayload(
            supplier_name="New Supplier Sdn Bhd",
            supplier_tin="C2222222222",
            buyer_name="New Buyer Sdn Bhd",
            invoice_no="INV-999",
            issue_date=date(2026, 8, 10),
            due_date=date(2026, 8, 30),
            currency="USD",
            tax_type="SST",
            tax_rate="8%",
            total_amount=Decimal("250.50"),
        )

        resp = update_record(
            db,
            record.id,
            payload,
            role=UserRole.OWNER_DIRECTOR,
            actor_ref="owner@finbrain.test",
            tenant_id=TENANT_A_STR,
        )

        assert resp.supplier_name == "New Supplier Sdn Bhd"
        assert resp.supplier_tin == "C2222222222"
        assert resp.buyer_name == "New Buyer Sdn Bhd"
        assert resp.invoice_no == "INV-999"
        assert resp.issue_date == date(2026, 8, 10)
        assert resp.due_date == date(2026, 8, 30)
        assert resp.currency == "USD"
        assert resp.tax_type == "SST"
        assert resp.tax_rate == "8%"
        assert resp.total_amount == Decimal("250.50")
        assert resp.status == "pending"
    finally:
        db.close()


def test_update_record_does_not_override_validated_status():
    db = _setup_db()
    try:
        record = EInvoiceRecord(
            tenant_id=TENANT_A_STR,
            supplier_name="Tenaga Nasional Berhad",
            supplier_tin="C1234567890",
            buyer_name="FINBRAIN Sdn Bhd",
            invoice_no="TNB-2026",
            issue_date=date(2026, 8, 10),
            total_amount=Decimal("1240.00"),
            status="validated",
            tax_type="SST",
            tax_rate="6%",
        )
        db.add(record)
        db.commit()

        payload = EInvoiceUpdatePayload(invoice_no="TNB-2026-REVISED")
        resp = update_record(
            db,
            record.id,
            payload,
            role=UserRole.FINANCE_OPS,
            actor_ref="finops@finbrain.test",
            tenant_id=TENANT_A_STR,
        )
        assert resp.status == "validated"
        assert resp.invoice_no == "TNB-2026-REVISED"
    finally:
        db.close()


def test_update_record_errors_on_not_found_or_cross_tenant():
    db = _setup_db()
    try:
        record = EInvoiceRecord(
            tenant_id=TENANT_A_STR,
            supplier_name="Tenant A Supplier",
            supplier_tin="C1111111111",
            total_amount=Decimal("100.00"),
            status="review",
        )
        db.add(record)
        db.commit()

        # Non-existent ID
        with pytest.raises(LookupError):
            update_record(
                db,
                99999,
                EInvoiceUpdatePayload(supplier_tin="C9999999999"),
                role=UserRole.FINANCE_OPS,
                actor_ref="finops@test",
                tenant_id=TENANT_A_STR,
            )

        # Cross-tenant access
        with pytest.raises(LookupError):
            update_record(
                db,
                record.id,
                EInvoiceUpdatePayload(supplier_tin="C9999999999"),
                role=UserRole.FINANCE_OPS,
                actor_ref="finops@test",
                tenant_id=TENANT_B_STR,
            )
    finally:
        db.close()


def test_api_patch_and_put_einvoice_record():
    db = _setup_db()
    record = EInvoiceRecord(
        tenant_id=TENANT_A_STR,
        supplier_name="Hardware Store Sdn Bhd",
        supplier_tin=None,
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="HS-332",
        issue_date=date(2026, 8, 5),
        total_amount=Decimal("350.00"),
        status="review",
        tax_type="SST",
        tax_rate="6%",
    )
    db.add(record)
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db

    # 1. Test PATCH as FINANCE_OPS
    app.dependency_overrides[get_current_user] = lambda: principal(
        role=UserRole.FINANCE_OPS, tenant_id=TENANT_A
    )
    client = TestClient(app)

    patch_resp = client.patch(
        f"/einvoice-records/{record.id}",
        json={"supplier_tin": "C8877665544"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["supplier_tin"] == "C8877665544"
    assert data["status"] == "pending"
    assert data["readiness_reason"] == "All required fields present."

    # 2. Test PUT as OWNER_DIRECTOR
    app.dependency_overrides[get_current_user] = lambda: principal(
        role=UserRole.OWNER_DIRECTOR, tenant_id=TENANT_A
    )
    put_resp = client.put(
        f"/einvoice-records/{record.id}",
        json={
            "supplier_name": "Hardware Store Pro Sdn Bhd",
            "invoice_no": "HS-332-V2",
            "total_amount": "400.00",
        },
    )
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["supplier_name"] == "Hardware Store Pro Sdn Bhd"
    assert put_data["invoice_no"] == "HS-332-V2"
    assert put_data["total_amount"] == "400.00"

    # 3. Test 403 Forbidden for GENERAL_EMPLOYEE
    app.dependency_overrides[get_current_user] = lambda: principal(
        role=UserRole.GENERAL_EMPLOYEE, tenant_id=TENANT_A
    )
    emp_resp = client.patch(
        f"/einvoice-records/{record.id}",
        json={"supplier_tin": "C9999999999"},
    )
    assert emp_resp.status_code == 403

    # 4. Test 404 for non-existent record
    app.dependency_overrides[get_current_user] = lambda: principal(
        role=UserRole.FINANCE_OPS, tenant_id=TENANT_A
    )
    not_found_resp = client.patch(
        "/einvoice-records/99999",
        json={"supplier_tin": "C9999999999"},
    )
    assert not_found_resp.status_code == 404
