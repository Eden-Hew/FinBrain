from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, TokenizedContent
from app.services import reasoning
from app.services.reasoning import answer_all_query_with_citations, answer_query_with_citations
from app.services.retrieval import RetrievalHit, retrieve_hits


def test_structured_retrieval_preserves_cross_source_provenance(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("MORPHEUS_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with Session(engine) as db:
        db.add_all(
            [
                TokenizedContent(
                    source_record_id="telegram:one",
                    source_system="telegram",
                    record_type="customer_message",
                    content_text="PERSON_aabbccddee reported an overdue approval.",
                    summary="Approval delay requires attention.",
                    embedding=[1.0, 0.0],
                    processing_status="ready",
                ),
                TokenizedContent(
                    source_record_id="email:two",
                    source_system="email",
                    record_type="email",
                    content_text="The invoice approval remains overdue.",
                    summary="A second approval delay requires attention.",
                    embedding=[0.9, 0.1],
                    processing_status="ready",
                ),
            ]
        )
        db.commit()

        hits = retrieve_hits(db, [1.0, 0.0], k=2)
        answer, mode = answer_query_with_citations("Why are approvals delayed?", hits)

        assert {hit.source_system for hit in hits} == {"telegram", "email"}
        assert answer.citations == ["SOURCE-1", "SOURCE-2"]
        assert not answer.insufficient_evidence
        assert mode == "offline-demo"


def test_cited_answer_reports_insufficient_evidence_without_hits():
    answer, mode = answer_query_with_citations("What is recurring?", [])

    assert answer.insufficient_evidence
    assert answer.citations == []
    assert mode == "offline-demo"


def test_analyze_all_batches_every_eligible_record(monkeypatch):
    monkeypatch.setattr(
        reasoning,
        "get_settings",
        lambda: type(
            "OfflineSettings",
            (),
            {
                "morpheus_api_key": None,
                "gemini_api_key": None,
                "allow_offline_demo": True,
            },
        )(),
    )
    hits = [
        RetrievalHit(
            content_id=index,
            source_record_id=f"email:{index}",
            source_system="email",
            record_type="email",
            occurred_at=None,
            protected_excerpt=f"Protected email record {index}.",
            protected_summary=f"Summary {index}.",
            similarity=1.0,
        )
        for index in range(1, 22)
    ]

    answer, mode = answer_all_query_with_citations("Summarize all email records", hits)

    assert mode == "offline-demo"
    assert answer.citations == [f"SOURCE-{index}" for index in range(1, 22)]
    assert "Protected email record 21" in answer.answer
