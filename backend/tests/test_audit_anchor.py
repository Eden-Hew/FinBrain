from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.models import DEFAULT_TENANT_ID, AuditLogEntry, Base, Tenant, WorkflowAuditEntry
from app.services.audit import write_audit_entry
from app.services.audit_anchor import (
    GENESIS,
    ChainAnchor,
    all_chain_anchors,
    all_tenant_ids,
    anchor_is_still_present,
    chain_tail_hashes,
)
from app.services.workflow_audit import write_workflow_event

TENANT_A = "00000000-0000-0000-0000-0000000000a1"


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_chain_tail_hashes_is_genesis_for_an_empty_chain():
    engine, db = _database()
    try:
        anchors = chain_tail_hashes(db, DEFAULT_TENANT_ID)
        assert {a.chain: a.tail_hash for a in anchors} == {
            "disclosure": GENESIS,
            "workflow": GENESIS,
        }
    finally:
        db.close()
        engine.dispose()


def test_chain_tail_hashes_matches_the_latest_written_event():
    engine, db = _database()
    try:
        write_audit_entry(
            db, "compliance", "NRIC_aabbccddee", True, "hash-1", tenant_id=DEFAULT_TENANT_ID
        )
        db.commit()
        expected = db.scalar(
            select(AuditLogEntry.event_hash)
            .where(AuditLogEntry.tenant_id == DEFAULT_TENANT_ID)
            .order_by(AuditLogEntry.id.desc())
            .limit(1)
        )

        anchors = chain_tail_hashes(db, DEFAULT_TENANT_ID)

        assert next(a.tail_hash for a in anchors if a.chain == "disclosure") == expected
    finally:
        db.close()
        engine.dispose()


def test_all_chain_anchors_covers_the_system_chain_and_every_tenant():
    engine, db = _database()
    try:
        db.add(Tenant(id=TENANT_A, name="Tenant A", slug="tenant-a"))
        db.commit()
        write_workflow_event(
            db,
            event_type="vault_key_rotated",
            actor_role="system_worker",
            actor_ref="rotation-worker",
            resource_type="vault",
            resource_id="1",
            event_payload={},
            tenant_id=None,
        )
        db.commit()

        anchors = all_chain_anchors(db)

        tenant_ids = {anchor.tenant_id for anchor in anchors}
        assert None in tenant_ids  # system chain
        assert TENANT_A in tenant_ids
        assert set(all_tenant_ids(db)) == {TENANT_A}
    finally:
        db.close()
        engine.dispose()


def test_anchor_is_still_present_for_genesis():
    engine, db = _database()
    try:
        anchor = ChainAnchor(tenant_id=DEFAULT_TENANT_ID, chain="disclosure", tail_hash=GENESIS)
        assert anchor_is_still_present(db, anchor) is True
    finally:
        db.close()
        engine.dispose()


def test_anchor_is_still_present_when_the_chain_is_unmodified():
    engine, db = _database()
    try:
        write_audit_entry(
            db, "compliance", "NRIC_aabbccddee", True, "hash-1", tenant_id=DEFAULT_TENANT_ID
        )
        db.commit()
        [anchor] = [a for a in chain_tail_hashes(db, DEFAULT_TENANT_ID) if a.chain == "disclosure"]

        assert anchor_is_still_present(db, anchor) is True
    finally:
        db.close()
        engine.dispose()


def test_anchor_detects_tampering_when_the_anchored_row_is_deleted():
    engine, db = _database()
    try:
        write_audit_entry(
            db, "compliance", "NRIC_aabbccddee", True, "hash-1", tenant_id=DEFAULT_TENANT_ID
        )
        db.commit()
        [anchor] = [a for a in chain_tail_hashes(db, DEFAULT_TENANT_ID) if a.chain == "disclosure"]

        # Simulate an attacker rewriting the chain after the anchor was taken.
        db.execute(delete(AuditLogEntry).where(AuditLogEntry.tenant_id == DEFAULT_TENANT_ID))
        db.commit()

        assert anchor_is_still_present(db, anchor) is False
    finally:
        db.close()
        engine.dispose()


def test_anchor_detects_tampering_when_the_anchored_hash_is_edited():
    engine, db = _database()
    try:
        write_workflow_event(
            db,
            event_type="recommendation_generated",
            actor_role="owner_director",
            actor_ref="test-actor",
            resource_type="process_recommendation",
            resource_id="1",
            event_payload={},
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.commit()
        [anchor] = [a for a in chain_tail_hashes(db, DEFAULT_TENANT_ID) if a.chain == "workflow"]

        row = db.scalar(
            select(WorkflowAuditEntry).where(WorkflowAuditEntry.tenant_id == DEFAULT_TENANT_ID)
        )
        row.event_hash = "tampered" * 8
        db.commit()

        assert anchor_is_still_present(db, anchor) is False
    finally:
        db.close()
        engine.dispose()
