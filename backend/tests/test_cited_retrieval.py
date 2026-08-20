from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, TokenizedContent
from app.services import reasoning
from app.services.reasoning import (
    answer_all_query_with_citations,
    answer_query_with_citations,
    structured_contact_lookup,
)
from app.services.retrieval import RetrievalHit, retrieve_hits, retrieve_hybrid_hits


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
    assert mode == "no-evidence"


def test_hybrid_retrieval_prioritizes_exact_protected_token_and_invoice_id():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                TokenizedContent(
                    source_record_id="email:DGT-4400",
                    source_system="email",
                    record_type="customer_email",
                    content_text="PERSON_aabbccddee asked about invoice DGT-4400.",
                    embedding=[0.0, 1.0],
                    processing_status="ready",
                ),
                TokenizedContent(
                    source_record_id="email:semantic",
                    source_system="email",
                    record_type="customer_email",
                    content_text="A semantically similar invoice approval record.",
                    embedding=[1.0, 0.0],
                    processing_status="ready",
                ),
            ]
        )
        db.commit()

        by_invoice = retrieve_hybrid_hits(db, "Explain DGT-4400", [1.0, 0.0], k=2)
        by_person = retrieve_hybrid_hits(db, "Find PERSON_aabbccddee", [1.0, 0.0], k=2)

        assert by_invoice[0].source_record_id == "email:DGT-4400"
        assert by_person[0].source_record_id == "email:DGT-4400"
        assert len(by_invoice) == 1
        assert len(by_person) == 1

        unknown_person = retrieve_hybrid_hits(
            db, "Find PERSON_ffeeddccbb", [1.0, 0.0], k=2
        )
        assert unknown_person == []


def test_provider_may_repeat_a_protected_token_from_the_question(monkeypatch):
    monkeypatch.setattr(
        reasoning,
        "get_settings",
        lambda: type(
            "MorpheusSettings",
            (),
            {
                "morpheus_api_key": "configured",
                "gemini_api_key": None,
                "allow_offline_demo": False,
            },
        )(),
    )
    monkeypatch.setattr(
        reasoning,
        "morpheus_chat",
        lambda *_args, **_kwargs: (
            '{"answer":"PERSON_aabbccddee is the requested customer [SOURCE-1].",'
            '"citations":["SOURCE-1"],"insufficient_evidence":false}'
        ),
    )
    hit = RetrievalHit(
        content_id=1,
        source_record_id="email:legacy-token",
        source_system="email",
        record_type="customer_email",
        occurred_at=None,
        protected_excerpt="PERSON_0011223344 requested a refund.",
        protected_summary=None,
        similarity=1.0,
    )

    answer, mode = reasoning.answer_query_with_citations(
        "Find customer PERSON_aabbccddee",
        [hit],
    )

    assert mode == "morpheus"
    assert "PERSON_aabbccddee" in answer.answer


def test_insufficient_provider_answer_drops_unrelated_citations(monkeypatch):
    monkeypatch.setattr(
        reasoning,
        "get_settings",
        lambda: type(
            "MorpheusSettings",
            (),
            {
                "morpheus_api_key": "configured",
                "gemini_api_key": None,
                "allow_offline_demo": False,
            },
        )(),
    )
    monkeypatch.setattr(
        reasoning,
        "morpheus_chat",
        lambda *_args, **_kwargs: (
            '{"answer":"There is not enough evidence.",'
            '"citations":["SOURCE-1"],"insufficient_evidence":true}'
        ),
    )
    hit = RetrievalHit(
        content_id=1,
        source_record_id="email:unrelated",
        source_system="email",
        record_type="customer_email",
        occurred_at=None,
        protected_excerpt="An unrelated protected record.",
        protected_summary=None,
        similarity=0.2,
    )

    answer, mode = reasoning.answer_query_with_citations("Find an unknown customer", [hit])

    assert mode == "morpheus"
    assert answer.insufficient_evidence
    assert answer.citations == []


def test_compact_lookup_instruction_requests_a_natural_short_answer(monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        reasoning,
        "get_settings",
        lambda: type(
            "MorpheusSettings",
            (),
            {
                "morpheus_api_key": "configured",
                "gemini_api_key": None,
                "allow_offline_demo": False,
            },
        )(),
    )

    def fake_chat(messages, **_kwargs):
        captured["system"] = messages[0]["content"]
        return (
            '{"answer":"The protected contact is EMAIL_aabbccddee.",'
            '"citations":["SOURCE-1"],"insufficient_evidence":false}'
        )

    monkeypatch.setattr(reasoning, "morpheus_chat", fake_chat)
    hit = RetrievalHit(
        content_id=1,
        source_record_id="email:contact",
        source_system="email",
        record_type="email",
        occurred_at=None,
        protected_excerpt="Contact EMAIL_aabbccddee.",
        protected_summary=None,
        similarity=1.0,
    )

    answer, mode = reasoning.answer_query_with_citations(
        "Show the contact",
        [hit],
        response_style="compact",
    )

    assert mode == "morpheus"
    assert answer.citations == ["SOURCE-1"]
    assert "one or two sentences" in captured["system"]
    assert "Do not recommend actions" in captured["system"]


def test_structured_contact_lookup_pairs_summary_customer_and_contact():
    hits = [
        RetrievalHit(
            content_id=1,
            source_record_id="email:sheng",
            source_system="email",
            record_type="email",
            occurred_at=None,
            protected_excerpt=(
                "From PERSON_1111111111 <EMAIL_1111111111> to EMAIL_2222222222. "
                "Customer PERSON_aaaaaaaaaa. Contact EMAIL_bbbbbbbbbb."
            ),
            protected_summary=(
                "Customer PERSON_aaaaaaaaaa requested a refund. Contact EMAIL_bbbbbbbbbb."
            ),
            similarity=1.0,
        ),
        RetrievalHit(
            content_id=2,
            source_record_id="telegram:wong",
            source_system="telegram",
            record_type="customer_message",
            occurred_at=None,
            protected_excerpt="PERSON_cccccccccc requested contact at PHONE_dddddddddd.",
            protected_summary=None,
            similarity=1.0,
        ),
    ]

    direct = structured_contact_lookup("What is his contact?", hits[:1])
    phones = structured_contact_lookup("Show all phone numbers with their name", hits)
    respectively = structured_contact_lookup("Who are they for respectively?", hits)

    assert direct is not None
    assert direct.answer == "PERSON_aaaaaaaaaa can be contacted at EMAIL_bbbbbbbbbb."
    assert direct.citations == ["SOURCE-1"]
    assert phones is not None
    assert phones.answer == "PERSON_cccccccccc can be contacted at PHONE_dddddddddd."
    assert phones.citations == ["SOURCE-2"]
    assert respectively is not None
    assert "PERSON_aaaaaaaaaa — EMAIL_bbbbbbbbbb" in respectively.answer
    assert "PERSON_cccccccccc — PHONE_dddddddddd" in respectively.answer
    assert respectively.citations == ["SOURCE-1", "SOURCE-2"]


def test_structured_contact_lookup_derives_output_from_unseen_tokens():
    hit = RetrievalHit(
        content_id=99,
        source_record_id="connector:arbitrary",
        source_system="custom_connector",
        record_type="arbitrary_record",
        occurred_at=None,
        protected_excerpt="Unrelated transport metadata.",
        protected_summary=(
            "ORG_0123456789 requested follow-up from PERSON_fedcba9876 at PHONE_abcdef0123."
        ),
        similarity=0.73,
    )

    answer = structured_contact_lookup("Return every phone number with its name", [hit])

    assert answer is not None
    assert answer.answer == "PERSON_fedcba9876 can be contacted at PHONE_abcdef0123."
    assert answer.citations == ["SOURCE-1"]


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
