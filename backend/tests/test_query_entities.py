from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import DEFAULT_TENANT_ID, Base, ProtectedTokenRegistry
from app.security.detect import Span
from app.security.query_entities import resolve_registered_entity_spans
from app.security.tokenize import derive_token, tokenize_record


def test_lowercase_customer_name_resolves_through_tenant_registry():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    token = derive_token("PERSON", "Sheng Kai", DEFAULT_TENANT_ID)
    with Session(engine) as db:
        db.add(
            ProtectedTokenRegistry(
                token=token,
                tenant_id=DEFAULT_TENANT_ID,
                entity_type="PERSON",
                masked_value="[person — restricted]",
            )
        )
        db.commit()

        spans = resolve_registered_entity_spans(
            db,
            "find sheng kai",
            DEFAULT_TENANT_ID,
            [],
        )
        protected, _entries = tokenize_record(
            "find sheng kai",
            spans,
            "query:test",
            DEFAULT_TENANT_ID,
            db=None,
        )

    assert [(span.text, span.label, span.source) for span in spans] == [
        ("sheng kai", "person", "token-registry")
    ]
    assert protected == f"find {token}"


def test_registry_resolution_is_tenant_scoped():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    other_tenant = "00000000-0000-0000-0000-000000000002"
    token = derive_token("PERSON", "Sheng Kai", other_tenant)
    with Session(engine) as db:
        db.add(
            ProtectedTokenRegistry(
                token=token,
                tenant_id=other_tenant,
                entity_type="PERSON",
                masked_value="[person — restricted]",
            )
        )
        db.commit()

        spans = resolve_registered_entity_spans(
            db,
            "find sheng kai",
            DEFAULT_TENANT_ID,
            [],
        )

    assert spans == []


def test_registered_name_outranks_an_overextended_gliner_span():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    token = derive_token("PERSON", "Sheng Kai", DEFAULT_TENANT_ID)
    with Session(engine) as db:
        db.add(
            ProtectedTokenRegistry(
                token=token,
                tenant_id=DEFAULT_TENANT_ID,
                entity_type="PERSON",
                masked_value="[person — restricted]",
            )
        )
        db.commit()

        spans = resolve_registered_entity_spans(
            db,
            "show sheng kai contact",
            DEFAULT_TENANT_ID,
            [Span(5, 22, "sheng kai contact", "person", "gliner")],
        )

    assert [(span.text, span.source) for span in spans] == [("sheng kai", "token-registry")]
