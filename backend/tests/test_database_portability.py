from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.db import _sqlalchemy_url
from app.models import Base, TokenizedContent, TokenVaultEntry
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
                ),
                TokenizedContent(
                    source_record_id="shipping",
                    content_text="shipping record",
                    embedding=[0.0, 1.0],
                ),
            ]
        )
        db.commit()
        assert retrieve_top_k(db, [1.0, 0.0], k=1) == ["finance record"]
