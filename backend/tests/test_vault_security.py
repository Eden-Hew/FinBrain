from types import SimpleNamespace

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import DEFAULT_TENANT_ID, Base, TokenVaultEntry, VaultKeyVersion, WorkflowAuditEntry
from app.security.detect import detect_spans
from app.security.detokenize import detokenize_response_with_trace
from app.security.disclosure import new_disclosure_session
from app.security.keyring import decrypt_vault_entry
from app.security.rotation import rotate_batch, rotate_if_due, run_rotation, start_rotation
from app.security.tokenize import tokenize_record
from app.services.workflow_audit import verify_workflow_chain


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_production_readiness_requires_three_distinct_security_secrets():
    secure = Settings(
        _env_file=None,
        token_root_secret="a" * 32,
        token_hash_secret="b" * 32,
        vault_master_key="c" * 32,
    )
    assert secure.production_secret_configured
    assert not secure.model_copy(update={"vault_master_key": None}).production_secret_configured
    assert not secure.model_copy(
        update={"vault_master_key": secure.token_hash_secret}
    ).production_secret_configured


def test_query_bound_grant_is_single_use_and_context_authenticated():
    session = new_disclosure_session(
        query_hash="query-a",
        actor_ref="user-a",
        role="finance_ops",
        turn_ref="turn-1",
    )
    grant = session.issue("AMOUNT_1234567890", "RM 4,500")
    assert session.consume(grant) == "RM 4,500"
    with pytest.raises(ValueError, match="replayed"):
        session.consume(grant)

    other = new_disclosure_session(
        query_hash="query-b",
        actor_ref="user-a",
        role="finance_ops",
        turn_ref="turn-1",
    )
    with pytest.raises(ValueError, match="wrong_session"):
        other.consume(grant)


def test_vault_ciphertext_is_bound_to_row_context():
    engine, db = _database()
    try:
        raw = "IC 901231-14-5566"
        _protected, entries = tokenize_record(
            raw, detect_spans(raw), "source-a", DEFAULT_TENANT_ID, db=db
        )
        db.add_all(entries)
        db.commit()
        entry = db.scalar(select(TokenVaultEntry))
        assert entry is not None
        assert decrypt_vault_entry(db, entry) == "901231-14-5566"
        entry.source_record_id = "source-b"
        with pytest.raises(InvalidTag):
            decrypt_vault_entry(db, entry)
    finally:
        db.close()
        engine.dispose()


def test_masked_role_never_receives_exact_value_and_trace_records_session():
    engine, db = _database()
    try:
        raw = "IC 901231-14-5566; payment RM 4,500."
        protected, entries = tokenize_record(
            raw, detect_spans(raw), "masked", DEFAULT_TENANT_ID, db=db
        )
        db.add_all(entries)
        db.commit()
        employee = detokenize_response_with_trace(
            db,
            protected,
            "general_employee",
            "masked-query",
            actor_ref="employee-a",
            turn_ref="42",
        )
        assert "901231-14-5566" not in employee.text
        assert "******-**-****" in employee.text
        assert "RM2.5K–5K" in employee.text
        assert employee.single_use_grants == 0
        assert len(employee.disclosure_session_ref) == 16

        compliance = detokenize_response_with_trace(
            db,
            protected,
            "compliance",
            "exact-query",
            actor_ref="compliance-a",
            turn_ref="43",
        )
        assert "901231-14-5566" in compliance.text
        assert "RM 4,500" in compliance.text
        assert compliance.single_use_grants == 2
    finally:
        db.close()
        engine.dispose()


def test_rotation_is_resumable_and_preserves_tokens(monkeypatch):
    engine, db = _database()
    try:
        for index, raw in enumerate(["RM 4,500", "RM 850"]):
            _protected, entries = tokenize_record(
                raw,
                detect_spans(raw),
                f"rotation-{index}",
                DEFAULT_TENANT_ID,
                db=db,
            )
            db.add_all(entries)
        db.commit()
        before = {
            row.token: decrypt_vault_entry(db, row)
            for row in db.scalars(select(TokenVaultEntry)).all()
        }
        initial_version = db.scalar(
            select(VaultKeyVersion.version).where(VaultKeyVersion.status == "active")
        )
        monkeypatch.setattr(
            "app.security.rotation.get_settings",
            lambda: SimpleNamespace(vault_rotation_batch_size=1),
        )
        job = start_rotation(db)
        rotate_batch(db, job)
        assert job.status == "running"
        assert job.rows_rotated == 1

        completed = run_rotation(db)
        assert completed.status == "completed"
        assert completed.rows_rotated == 2
        after_rows = list(db.scalars(select(TokenVaultEntry)).all())
        assert {row.token for row in after_rows} == set(before)
        assert all(row.key_version != initial_version for row in after_rows)
        assert {row.token: decrypt_vault_entry(db, row) for row in after_rows} == before
        assert db.query(WorkflowAuditEntry).count() == 2
        assert verify_workflow_chain(db)
    finally:
        db.close()
        engine.dispose()


def test_automatic_rotation_resumes_an_unfinished_job(monkeypatch):
    engine, db = _database()
    try:
        _protected, entries = tokenize_record(
            "RM 4,500", detect_spans("RM 4,500"), "auto", DEFAULT_TENANT_ID, db=db
        )
        db.add_all(entries)
        db.commit()
        monkeypatch.setattr(
            "app.security.rotation.get_settings",
            lambda: SimpleNamespace(
                vault_auto_rotation_enabled=True,
                vault_rotation_batch_size=1,
            ),
        )
        job = start_rotation(db)
        assert job.status == "running"
        completed = rotate_if_due(db)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.rows_rotated == 1
    finally:
        db.close()
        engine.dispose()


def test_rotation_recovers_rows_stranded_by_a_premature_completion(monkeypatch):
    engine, db = _database()
    try:
        _protected, entries = tokenize_record(
            "RM 4,500", detect_spans("RM 4,500"), "recovery", DEFAULT_TENANT_ID, db=db
        )
        db.add_all(entries)
        db.commit()
        monkeypatch.setattr(
            "app.security.rotation.get_settings",
            lambda: SimpleNamespace(vault_rotation_batch_size=10),
        )
        job = start_rotation(db)
        old_key = db.get(VaultKeyVersion, job.from_version)
        assert old_key is not None
        old_key.status = "retired"
        job.status = "completed"
        job.completed_at = job.started_at
        db.commit()

        recovered = run_rotation(db)
        assert recovered.id == job.id
        assert recovered.status == "completed"
        assert recovered.rows_rotated == 1
        assert db.scalar(select(TokenVaultEntry.key_version)) == recovered.to_version
        assert decrypt_vault_entry(db, db.scalar(select(TokenVaultEntry))) == "RM 4,500"
    finally:
        db.close()
        engine.dispose()
