import re

from app.config import get_settings
from app.schemas import CitedAnswer
from app.security.detect import contains_known_pii
from app.services.morpheus import morpheus_chat
from app.services.retrieval import RetrievalHit

SYSTEM_INSTRUCTION = (
    "You are FinBrain OS's reasoning assistant. Answer only from the supplied context. "
    "Never invent values. Placeholders matching TYPE_xxxxxxxxxx or AMOUNT_BAND_n represent "
    "hidden values. Copy every relevant token exactly; never guess or reformat it."
)

TOKEN_PATTERN = re.compile(r"(?:[A-Z]+_[0-9a-f]{10}|AMOUNT_BAND_\d+)")


def _offline_answer(question: str, chunks: list[str]) -> str:
    if not chunks:
        return "No matching records are available yet. Run the seed command first."
    return (
        "Offline demo mode is active. The most relevant protected records are:\n\n- "
        + "\n- ".join(chunks)
    )


def answer_query(question: str, chunks: list[str]) -> tuple[str, str]:
    context = "\n\n".join(chunks)
    if contains_known_pii(question) or contains_known_pii(context):
        raise ValueError("Refusing to send recognized PII to the reasoning service")
    settings = get_settings()
    if settings.morpheus_api_key:
        try:
            response = morpheus_chat(
                [
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {
                        "role": "user",
                        "content": f"Context:\n{context}\n\nQuestion: {question}",
                    },
                ]
            )
            return response, "morpheus"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if settings.gemini_api_key:
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
            response = client.models.generate_content(
                model=settings.gemini_reasoning_model,
                contents=f"Context:\n{context}\n\nQuestion: {question}",
                config={"system_instruction": SYSTEM_INSTRUCTION},
            )
            return response.text or "No answer was generated.", "gemini"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if not settings.allow_offline_demo:
        raise RuntimeError("A reasoning API key is required when offline demo mode is disabled")
    return _offline_answer(question, chunks), "offline-demo"


def unknown_tokens(text: str, known_tokens: set[str]) -> set[str]:
    output_tokens = {
        token for token in TOKEN_PATTERN.findall(text) if not token.startswith("AMOUNT_BAND_")
    }
    return output_tokens - known_tokens


def _cited_context(hits: list[RetrievalHit]) -> tuple[str, set[str]]:
    blocks: list[str] = []
    citation_ids: set[str] = set()
    for index, hit in enumerate(hits, 1):
        citation_id = f"SOURCE-{index}"
        citation_ids.add(citation_id)
        occurred_at = hit.occurred_at.isoformat() if hit.occurred_at else "unknown"
        blocks.append(
            f"[{citation_id}]\nSystem: {hit.source_system}\nType: "
            f"{hit.record_type or 'record'}\nDate: {occurred_at}\n{hit.retrieval_text}"
        )
    return "\n\n".join(blocks), citation_ids


def _validate_cited_answer(
    answer: CitedAnswer, *, allowed_citations: set[str], protected_context: str
) -> None:
    citations = set(answer.citations)
    if citations - allowed_citations:
        raise ValueError("The reasoning service returned an unknown citation")
    if not answer.insufficient_evidence and allowed_citations and not citations:
        raise ValueError("A grounded answer must include at least one citation")
    if contains_known_pii(answer.model_dump_json()):
        raise ValueError("The reasoning service returned recognizable sensitive data")
    allowed_tokens = set(TOKEN_PATTERN.findall(protected_context))
    if unknown_tokens(answer.answer, allowed_tokens):
        raise ValueError("The reasoning service returned an unknown protected token")


def answer_query_with_citations(
    question: str, hits: list[RetrievalHit]
) -> tuple[CitedAnswer, str]:
    context, allowed_citations = _cited_context(hits)
    if contains_known_pii(question) or contains_known_pii(context):
        raise ValueError("Refusing to send recognized PII to the reasoning service")
    if not hits:
        return CitedAnswer(
            answer="No matching protected records are available.",
            citations=[],
            insufficient_evidence=True,
        ), "offline-demo"

    settings = get_settings()
    instruction = (
        f"{SYSTEM_INSTRUCTION} Return only JSON with keys answer, citations, and "
        "insufficient_evidence. citations must contain only supplied SOURCE-n identifiers. "
        "Set insufficient_evidence true when the context cannot support the answer."
    )
    if settings.morpheus_api_key:
        try:
            response = morpheus_chat(
                [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
                ]
            )
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
            result = CitedAnswer.model_validate_json(cleaned)
            _validate_cited_answer(
                result, allowed_citations=allowed_citations, protected_context=context
            )
            return result, "morpheus"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if settings.gemini_api_key:
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
            response = client.models.generate_content(
                model=settings.gemini_reasoning_model,
                contents=f"Context:\n{context}\n\nQuestion: {question}",
                config={
                    "system_instruction": instruction,
                    "response_mime_type": "application/json",
                    "response_schema": CitedAnswer,
                    "temperature": 0.1,
                },
            )
            result = (
                response.parsed
                if isinstance(response.parsed, CitedAnswer)
                else CitedAnswer.model_validate(response.parsed)
                if response.parsed is not None
                else CitedAnswer.model_validate_json(response.text or "")
            )
            _validate_cited_answer(
                result, allowed_citations=allowed_citations, protected_context=context
            )
            return result, "gemini"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if not settings.allow_offline_demo:
        raise RuntimeError("A reasoning API key is required when offline demo mode is disabled")
    result = CitedAnswer(
        answer=_offline_answer(question, [hit.retrieval_text for hit in hits]),
        citations=[f"SOURCE-{index}" for index in range(1, len(hits) + 1)],
        insufficient_evidence=False,
    )
    _validate_cited_answer(result, allowed_citations=allowed_citations, protected_context=context)
    return result, "offline-demo"
