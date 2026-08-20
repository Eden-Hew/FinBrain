from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth.principal import AuthPrincipal
from app.models import (
    Base,
    Customer,
    CustomerEndpoint,
    OutreachAction,
    Tenant,
    WorkflowAuditEntry,
)
from app.routes.outreach import _endpoint_response
from app.schemas import UserRole
from app.services.outreach import (
    create_action,
    register_email_endpoint,
    revoke_endpoint,
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


def test_only_owner_receives_audited_authorized_endpoint_value():
    db, customer = _session()
    try:
        endpoint = register_email_endpoint(
            db, tenant_id=TENANT, customer_id=customer.id, value="owner-view@example.com"
        )
        finance = AuthPrincipal(
            user_id=UUID(USER), email="finance@example.com",
            role=UserRole.FINANCE_OPS, tenant_id=UUID(TENANT),
        )
        owner = AuthPrincipal(
            user_id=UUID(USER), email="owner@example.com",
            role=UserRole.OWNER_DIRECTOR, tenant_id=UUID(TENANT),
        )

        finance_response = _endpoint_response(db, endpoint, finance)
        owner_response = _endpoint_response(db, endpoint, owner)

        assert finance_response.authorized_value is None
        assert finance_response.masked_value == "*****@*******.***"
        assert owner_response.authorized_value == "owner-view@example.com"
        assert owner_response.masked_value == "*****@*******.***"
    finally:
        db.close()


def test_revoked_endpoint_blocks_approval_and_requires_explicit_restore():
    db, customer = _session()
    try:
        endpoint = register_email_endpoint(
            db, tenant_id=TENANT, customer_id=customer.id, value="revoke@example.com"
        )
        verify_endpoint(db, endpoint.id, tenant_id=TENANT, reviewer_id=USER)
        action = create_action(
            db, tenant_id=TENANT, customer_id=customer.id, endpoint_id=endpoint.id,
            subject="Protected subject", body="Protected body",
            idempotency_key="test-action-revoke", evidence_ids=[],
            created_by_user_id=USER, actor_role=UserRole.FINANCE_OPS.value,
            actor_ref="finance",
        )
        transition_action(
            db, action.id, "submit", tenant_id=TENANT,
            role=UserRole.FINANCE_OPS, user_id=USER, actor_ref="finance",
        )

        revoked = revoke_endpoint(
            db, endpoint.id, tenant_id=TENANT,
            actor_role=UserRole.OWNER_DIRECTOR.value, actor_ref="owner",
        )
        assert revoked.verification_status == "revoked"
        try:
            transition_action(
                db, action.id, "approve", tenant_id=TENANT,
                role=UserRole.OWNER_DIRECTOR, user_id=USER, actor_ref="owner",
            )
        except ValueError as error:
            assert str(error) == "verified_email_endpoint_required"
        else:
            raise AssertionError("revoked endpoint was approved for delivery")

        restored = register_email_endpoint(
            db, tenant_id=TENANT, customer_id=customer.id,
            value="revoke@example.com", actor_role=UserRole.OWNER_DIRECTOR.value,
            actor_ref="owner",
        )
        assert restored.id == endpoint.id
        assert restored.verification_status == "observed"
        assert restored.verified_by_user_id is None
        assert restored.verified_at is None
        event_types = set(db.scalars(select(WorkflowAuditEntry.event_type)).all())
        assert "customer_endpoint_revoked" in event_types
        assert "customer_endpoint_restored" in event_types
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


def test_provisional_or_conflicted_customer_cannot_enter_outreach_queue():
    db, customer = _session()
    try:
        endpoint = CustomerEndpoint(
            tenant_id=TENANT, customer_id=customer.id, channel="email",
            endpoint_token="EMAIL_0123456789", verification_status="verified",
            origin="inbound_email",
        )
        db.add(endpoint)
        db.commit()
        action = create_action(
            db, tenant_id=TENANT, customer_id=customer.id, endpoint_id=endpoint.id,
            subject="Subject", body="Body", idempotency_key="identity-gate-test",
            evidence_ids=[], created_by_user_id=USER,
            actor_role=UserRole.FINANCE_OPS.value, actor_ref="actor",
        )
        customer.profile_status = "provisional"
        db.commit()
        with pytest.raises(ValueError, match="confirmed_customer_required"):
            transition_action(
                db, action.id, "submit", tenant_id=TENANT,
                role=UserRole.FINANCE_OPS, user_id=USER, actor_ref="actor",
            )
        customer.profile_status = "confirmed"
        customer.identity_review_status = "review_required"
        db.commit()
        with pytest.raises(ValueError, match="customer_identity_review_required"):
            transition_action(
                db, action.id, "submit", tenant_id=TENANT,
                role=UserRole.FINANCE_OPS, user_id=USER, actor_ref="actor",
            )
    finally:
        db.close()
