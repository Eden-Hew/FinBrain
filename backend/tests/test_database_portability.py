from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.db import _sqlalchemy_url, set_worker_context
from app.models import Base, TokenizedContent, TokenVaultEntry
from app.services import ingestion
from app.services.retrieval import retrieve_top_k


def test_postgres_urls_use_psycopg_three():
    assert _sqlalchemy_url("postgres://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )
    assert _sqlalchemy_url("postgresql://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )


def test_embedding_type_compiles_to_pgvector():
    column_type = TokenizedContent.__table__.c.embedding.type
    postgres_type = column_type.load_dialect_impl(postgresql.dialect())
    assert str(postgres_type) == "VECTOR(768)"


def test_role_list_compiles_to_postgres_jsonb():
    column_type = TokenVaultEntry.__table__.c.allowed_roles.type
    postgres_type = column_type.load_dialect_impl(postgresql.dialect())
    assert isinstance(postgres_type, JSONB)


def test_worker_context_carries_every_key_the_after_begin_listener_needs(monkeypatch):
    """Regression test: set_worker_context() used to omit "tenant_id" from
    session.info entirely, which raised a missing-bind-parameter error the moment
    a worker session opened a second transaction (e.g. after any db.commit())
    against real Postgres, since _restore_rls_context's query always references
    :tenant_id. SQLite can't run set_config(), so the dialect check is spoofed and
    execute() is captured rather than actually run against the database.
    """
    engine = create_engine("sqlite:///:memory:")
    db = Session(engine)
    monkeypatch.setattr(engine.dialect, "name", "postgresql")
    monkeypatch.setattr(db, "execute", lambda *args, **kwargs: None)

    set_worker_context(db, actor_ref="test-scheduler", tenant_id="tenant-x")

    context = db.info["finbrain_rls_context"]
    assert context["actor_ref"] == "test-scheduler"
    assert context["tenant_id"] == "tenant-x"
    assert context["database_role"] == "finbrain_worker"
    assert {"user_id", "user_role", "actor_ref", "tenant_id"} <= set(context)


def test_optional_object_values_are_stored_as_sql_null():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            TokenizedContent(
                source_record_id="protected-only",
                content_text="Protected content awaiting enrichment.",
                structured_summary=None,
            )
        )
        db.commit()

        assert db.scalar(
            text(
                "select structured_summary is null "
                "from tokenized_content where source_record_id = :source_record_id"
            ),
            {"source_record_id": "protected-only"},
        ) == 1


def test_sqlite_retrieval_uses_portable_embedding_values():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                TokenizedContent(
                    source_record_id="finance",
                    content_text="finance record",
                    embedding=[1.0, 0.0],
                    processing_status="ready",
                ),
                TokenizedContent(
                    source_record_id="shipping",
                    content_text="shipping record",
                    embedding=[0.0, 1.0],
                    processing_status="ready",
                ),
            ]
        )
        db.commit()
        assert retrieve_top_k(db, [1.0, 0.0], k=1) == ["finance record"]


def test_retrieval_keeps_protected_summary_and_source_together():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            TokenizedContent(
                source_record_id="customer-message",
                content_text="PERSON_0011223344 has an overdue invoice.",
                summary="PERSON_0011223344 needs payment attention.",
                embedding=[1.0, 0.0],
                processing_status="ready",
            )
        )
        db.commit()

        assert retrieve_top_k(db, [1.0, 0.0], k=1) == [
            "Protected summary: PERSON_0011223344 needs payment attention.\n"
            "Protected source: PERSON_0011223344 has an overdue invoice."
        ]


def test_ingestion_refresh_updates_existing_record(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(ingestion, "detect_spans", lambda _text: [])
    monkeypatch.setattr(
        ingestion,
        "tokenize_record",
        lambda raw_text, _spans, _source_id, _tenant_id, db=None: (f"sanitized:{raw_text}", []),
    )
    monkeypatch.setattr(ingestion, "contains_known_pii", lambda _text: False)
    monkeypatch.setattr(ingestion, "embed_text", lambda text: ([float(len(text))], False))

    with Session(engine) as db:
        ingestion.ingest_record(db, "record-1", "payment", "first")
        unchanged = ingestion.ingest_record(db, "record-1", "payment", "first")
        refreshed = ingestion.ingest_record(
            db,
            "record-1",
            "conversation",
            "second",
            refresh=True,
        )

        records = db.scalars(select(TokenizedContent)).all()
        assert unchanged == "sanitized:first"
        assert refreshed == "sanitized:second"
        assert len(records) == 1
        assert records[0].content_text == "sanitized:second"
        assert records[0].record_type == "conversation"
