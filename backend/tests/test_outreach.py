from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Customer, CustomerEndpoint, OutreachAction, Tenant
from app.schemas import UserRole
from app.services.outreach import (
    create_action,
    register_email_endpoint,
    transition_action,
    verify_endpoint,
)

TENANT = "00000000-0000-0000-0000-000000000001"
USER = "30000000-0000-0000-0000-000000000003"


def _session() -> tuple[Session, Customer]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Test", slug="test"))
    customer = Customer(tenant_id=TENANT, canonical_name="Demo", normalized_name="DEMO")
    db.add(customer)
    db.commit()
    return db, customer


def test_endpoint_is_protected_and_requires_verification_before_submit():
    db, customer = _session()
    try:
        endpoint = register_email_endpoint(
            db, tenant_id=TENANT, customer_id=customer.id, value="demo@example.com"
        )
        assert endpoint.endpoint_token.startswith("EMAIL_")
        assert "example.com" not in endpoint.endpoint_token
        action = create_action(
            db, tenant_id=TENANT, customer_id=customer.id, endpoint_id=endpoint.id,
            subject="Hello Demo", body="Please reply to demo@example.com",
            idempotency_key="test-action-0001", evidence_ids=[],
            created_by_user_id=USER, actor_role=UserRole.FINANCE_OPS.value,
            actor_ref="actor",
        )
        assert action.status == "draft"
        try:
            transition_action(
                db, action.id, "submit", tenant_id=TENANT,
                role=UserRole.FINANCE_OPS, user_id=USER, actor_ref="actor",
            )
        except ValueError as error:
            assert str(error) == "verified_email_endpoint_required"
        else:
            raise AssertionError("unverified endpoint was accepted")
        verify_endpoint(db, endpoint.id, tenant_id=TENANT, reviewer_id=USER)
        submitted = transition_action(
            db, action.id, "submit", tenant_id=TENANT,
            role=UserRole.FINANCE_OPS, user_id=USER, actor_ref="actor",
        )
        assert submitted.status == "pending_approval"
    finally:
        db.close()


def test_outreach_creation_is_idempotent_and_owner_controls_approval():
    db, customer = _session()
    try:
        endpoint = CustomerEndpoint(
            tenant_id=TENANT, customer_id=customer.id, channel="email",
            endpoint_token="EMAIL_0123456789", verification_status="verified",
        )
        db.add(endpoint)
        db.commit()
        kwargs = dict(
            tenant_id=TENANT, customer_id=customer.id, endpoint_id=endpoint.id,
            subject="Subject", body="Body", idempotency_key="test-action-0002",
            evidence_ids=[], created_by_user_id=USER,
            actor_role=UserRole.FINANCE_OPS.value, actor_ref="actor",
        )
        first = create_action(db, **kwargs)
        second = create_action(db, **kwargs)
        assert first.id == second.id
        transition_action(
            db, first.id, "submit", tenant_id=TENANT,
            role=UserRole.FINANCE_OPS, user_id=USER, actor_ref="actor",
        )
        try:
            transition_action(
                db, first.id, "approve", tenant_id=TENANT,
                role=UserRole.FINANCE_OPS, user_id=USER, actor_ref="actor",
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("finance role approved outreach")
        approved = transition_action(
            db, first.id, "approve", tenant_id=TENANT,
            role=UserRole.OWNER_DIRECTOR, user_id=USER, actor_ref="owner",
        )
        assert approved.status == "approved"
        assert db.query(OutreachAction).count() == 1
    finally:
        db.close()
