import logging
import re

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.schemas import CitedAnswer
from app.security.detect import contains_known_pii
from app.services.gemini import gemini_client
from app.services.morpheus import morpheus_chat
from app.services.retrieval import RetrievalHit

SYSTEM_INSTRUCTION = (
    "You are FinBrain OS's reasoning assistant. Answer only from the supplied context. "
    "Answer the user's latest question directly in natural language. For a simple lookup, use "
    "one or two concise sentences. Do not restate the context, describe your reasoning process, "
    "or mention SOURCE identifiers in the answer prose because citations are rendered separately. "
    "Do not recommend actions unless the user asks for analysis, risks, or recommendations. "
    "If the user asks to draft or suggest a response or reply, write a concise ready-to-send "
    "message grounded in the cited evidence; do not merely summarize the request. If the user "
    "asks for an action, give the specific next step supported by the selected evidence. "
    "Conversation history is background only: never preserve an earlier source filter unless the "
    "latest question explicitly refers to that source. "
    "Bad style: 'The customer is found in SOURCE-1, where they requested a refund.' "
    "Good style: 'The customer requested a refund after cancelling the order.' "
    "Treat each supplied System field as authoritative source metadata; do not infer source "
    "identity from words inside the protected record. "
    "Never invent values. Placeholders matching TYPE_xxxxxxxxxx represent hidden values. "
    "AMOUNT_BAND_n_xxxxxxxxxx is a hidden exact amount whose BAND_n component reveals only an "
    "approximate range. Copy every relevant token completely and exactly; never guess or "
    "reformat it."
)

ANALYZE_ALL_BATCH_SIZE = 20
logger = logging.getLogger(__name__)


def _provider_error_code(error: Exception) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "provider_timeout"
    if isinstance(error, httpx.HTTPStatusError):
        return "provider_http_error"
    if isinstance(error, ValidationError):
        return "provider_schema_violation"
    message = str(error).casefold()
    if "empty response" in message or "no answer was generated" in message:
        return "provider_empty_response"
    if "unknown citation" in message:
        return "provider_unknown_citation"
    if "at least one citation" in message:
        return "provider_missing_citation"
    if "sensitive data" in message or "recognized pii" in message:
        return "provider_pii_violation"
    if "unknown protected token" in message:
        return "provider_unknown_token"
    return "provider_invalid_response"


def _log_provider_failure(provider: str, error: Exception) -> None:
    """Log only a safe failure class; provider messages may contain echoed content."""
    logger.warning(
        "reasoning_provider_failed provider=%s error_code=%s error_type=%s",
        provider,
        _provider_error_code(error),
        type(error).__name__,
    )


def structured_record_listing(hits: list[RetrievalHit]) -> CitedAnswer:
    if not hits:
        return CitedAnswer(
            answer="No records match the requested source-system filter.",
            citations=[],
            insufficient_evidence=True,
        )
    source_names = ", ".join(sorted({hit.source_system for hit in hits}))
    return CitedAnswer(
        answer=(
            f"Found {len(hits)} ready record(s) from {source_names}. "
            "Select a cited source to inspect its authorized evidence."
        ),
        citations=[f"SOURCE-{index}" for index in range(1, len(hits) + 1)],
        insufficient_evidence=False,
    )


TOKEN_PATTERN = re.compile(r"(?:AMOUNT_BAND_\d+_[0-9a-f]{10}|[A-Z]+_[0-9a-f]{10})")
_PERSON_PATTERN = re.compile(r"PERSON_[0-9a-f]{10}")
_ORG_PATTERN = re.compile(r"ORG_[0-9a-f]{10}")
_PHONE_PATTERN = re.compile(r"PHONE_[0-9a-f]{10}")
_EMAIL_PATTERN = re.compile(r"EMAIL_[0-9a-f]{10}")
_CONTACT_QUESTION_PATTERN = re.compile(
    r"\b(?:contact|phone numbers?|email addresses?|sender(?:'s)? email(?: address)?|"
    r"(?:his|her|their|customer(?:'s)?) email(?: address)?|"
    r"who (?:is|are) (?:it|they|these|those) for|"
    r"who do (?:it|they|these|those) belong to)\b",
    re.IGNORECASE,
)
_CONTACT_ENUMERATION_PATTERN = re.compile(
    r"\b(?:show|list|give|return)\b.*\b(?:all|every|each)\b.*"
    r"\b(?:contacts?|phone numbers?|email addresses?)\b",
    re.IGNORECASE,
)
_CUSTOMER_NAME_QUESTION_PATTERN = re.compile(
    r"\b(?:show|list|give|tell|what|who)\b.*\b(?:customer(?:'s)? )?names?\b|"
    r"\bwho (?:is|was) (?:the )?(?:customer|sender)\b",
    re.IGNORECASE,
)


def _offline_answer(question: str, chunks: list[str]) -> str:
    if not chunks:
        return "No matching records are available yet. Run the seed command first."
    return (
        "Offline demo mode is active. The most relevant protected records are:\n\n- "
        + "\n- ".join(chunks)
    )


def is_contact_lookup(question: str) -> bool:
    return bool(_CONTACT_QUESTION_PATTERN.search(question))


def is_contact_enumeration(question: str) -> bool:
    return bool(_CONTACT_ENUMERATION_PATTERN.search(question))


def is_customer_profile_lookup(question: str) -> bool:
    """Return true only for direct identity/contact fields in selected-customer scope."""
    return bool(
        _CUSTOMER_NAME_QUESTION_PATTERN.search(question)
        or _CONTACT_QUESTION_PATTERN.search(question)
    )


def structured_customer_profile_lookup(
    question: str,
    hits: list[RetrievalHit],
    *,
    name_token: str | None,
    email_token: str | None,
    email_mask: str | None,
    reveal_email: bool,
) -> CitedAnswer | None:
    """Resolve selected-customer identity fields from authoritative protected state.

    The verified customer endpoint is authoritative for email. Evidence rows are
    used only to attach citations and to resolve phone tokens; this prevents an
    inbound message's recipient header from being mistaken for the customer.
    """
    if not is_customer_profile_lookup(question):
        return None
    lowered = question.casefold()
    generic_contact = "contact" in lowered and "email" not in lowered and "phone" not in lowered
    wants_email = "email" in lowered or generic_contact
    wants_phone = "phone" in lowered or generic_contact
    wants_name = bool(_CUSTOMER_NAME_QUESTION_PATTERN.search(question))
    answers: list[str] = []
    citation_indexes: set[int] = set()

    if wants_name:
        answers.append(
            f"The selected customer is {name_token}."
            if name_token
            else "The selected customer's name has not been verified yet."
        )
        if name_token:
            citation_indexes.update(
                index for index, hit in enumerate(hits, 1) if name_token in hit.retrieval_text
            )

    if wants_email:
        email_value = email_token if reveal_email and email_token else email_mask
        answers.append(
            f"The selected customer's verified email address is {email_value}."
            if email_value
            else "The selected customer does not have a verified email address."
        )
        if email_token:
            citation_indexes.update(
                index for index, hit in enumerate(hits, 1) if email_token in hit.retrieval_text
            )

    if wants_phone:
        phone_rows: list[tuple[str, int]] = []
        seen_phones: set[str] = set()
        for index, hit in enumerate(hits, 1):
            text = hit.protected_summary or hit.protected_excerpt
            for phone in _PHONE_PATTERN.findall(text):
                if phone not in seen_phones:
                    seen_phones.add(phone)
                    phone_rows.append((phone, index))
        if phone_rows:
            label = name_token or "The selected customer"
            answers.append(f"{label} can be contacted at {', '.join(p for p, _ in phone_rows)}.")
            citation_indexes.update(index for _phone, index in phone_rows)
        else:
            answers.append("The selected customer does not have a phone number in linked evidence.")

    if not answers:
        return None
    return CitedAnswer(
        answer="\n".join(answers),
        citations=[f"SOURCE-{index}" for index in sorted(citation_indexes)],
        insufficient_evidence=not any(
            (
                name_token if wants_name else None,
                email_token if wants_email else None,
                citation_indexes,
            )
        ),
    )


def structured_contact_lookup(question: str, hits: list[RetrievalHit]) -> CitedAnswer | None:
    """Associate protected people/organizations with contacts from the same evidence row."""
    if not is_contact_lookup(question):
        return None
    lowered = question.casefold()
    wants_phone = "phone" in lowered
    wants_email = "email" in lowered
    associations: list[tuple[str, list[str], str]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for index, hit in enumerate(hits, 1):
        # Prefer the focused protected summary. Email source bodies also contain
        # transport sender/recipient tokens that are not the customer's contact.
        text = hit.protected_summary or hit.protected_excerpt
        people = list(dict.fromkeys(_PERSON_PATTERN.findall(text)))
        organizations = list(dict.fromkeys(_ORG_PATTERN.findall(text)))
        contacts: list[str] = []
        if wants_phone or not wants_email:
            contacts.extend(_PHONE_PATTERN.findall(text))
        if wants_email or not wants_phone:
            contacts.extend(_EMAIL_PATTERN.findall(text))
        contacts = list(dict.fromkeys(contacts))
        if not contacts:
            continue
        name = people[0] if people else organizations[0] if organizations else "Contact"
        key = (name, tuple(contacts))
        if key in seen:
            continue
        seen.add(key)
        associations.append((name, contacts, f"SOURCE-{index}"))
    if not associations:
        return None

    citations = [citation for _name, _contacts, citation in associations]
    if len(associations) == 1:
        name, contacts, _citation = associations[0]
        answer = f"{name} can be contacted at {', '.join(contacts)}."
    else:
        answer = "\n".join(
            f"{name} — {', '.join(contacts)}" for name, contacts, _citation in associations
        )
    return CitedAnswer(answer=answer, citations=citations, insufficient_evidence=False)


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
        except Exception as error:
            _log_provider_failure("morpheus", error)
            if not settings.allow_offline_demo:
                raise
    if settings.gemini_api_key:
        try:
            client = gemini_client()
            response = client.models.generate_content(
                model=settings.gemini_reasoning_model,
                contents=f"Context:\n{context}\n\nQuestion: {question}",
                config={"system_instruction": SYSTEM_INSTRUCTION},
            )
            return response.text or "No answer was generated.", "gemini"
        except Exception as error:
            _log_provider_failure("gemini", error)
            if not settings.allow_offline_demo:
                raise
    if not settings.allow_offline_demo:
        raise RuntimeError("A reasoning API key is required when offline demo mode is disabled")
    return _offline_answer(question, chunks), "offline-demo"


def unknown_tokens(text: str, known_tokens: set[str]) -> set[str]:
    output_tokens = set(TOKEN_PATTERN.findall(text))
    return output_tokens - known_tokens


def _cited_context(hits: list[RetrievalHit], *, citation_offset: int = 0) -> tuple[str, set[str]]:
    blocks: list[str] = []
    citation_ids: set[str] = set()
    for index, hit in enumerate(hits, 1 + citation_offset):
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


def _normalize_insufficient_citations(answer: CitedAnswer) -> CitedAnswer:
    """Do not present retrieved neighbors as supporting citations for no-evidence answers."""
    if answer.insufficient_evidence and answer.citations:
        return answer.model_copy(update={"citations": []})
    return answer


def _answer_cited_context(
    question: str,
    context: str,
    allowed_citations: set[str],
    *,
    offline_chunks: list[str],
    protected_context: str | None = None,
    response_style: str = "analysis",
) -> tuple[CitedAnswer, str]:
    settings = get_settings()
    style_instruction = (
        "This is a compact lookup. Put the requested value or fact first and keep the answer to "
        "one or two sentences. "
        if response_style == "compact"
        else "This is an analytical request. Synthesize the evidence clearly but concisely. "
    )
    instruction = (
        f"{SYSTEM_INSTRUCTION} Return only JSON with keys answer, citations, and "
        "insufficient_evidence. citations must contain only supplied SOURCE-n identifiers. "
        "Set insufficient_evidence true when the context cannot support the answer. "
        f"{style_instruction}"
    )
    # Tokens supplied by the user are legitimate protected values too. During a
    # tenant-token migration they may differ from legacy evidence tokens, and a
    # provider is allowed to repeat the protected question without that being an
    # invented-token violation.
    validation_base = protected_context if protected_context is not None else context
    validation_context = f"{validation_base}\n{question}"
    if settings.morpheus_api_key:
        try:
            response = morpheus_chat(
                [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
                ]
            )
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
            result = _normalize_insufficient_citations(CitedAnswer.model_validate_json(cleaned))
            _validate_cited_answer(
                result,
                allowed_citations=allowed_citations,
                protected_context=validation_context,
            )
            return result, "morpheus"
        except Exception as error:
            _log_provider_failure("morpheus", error)
            if not settings.allow_offline_demo:
                raise
    if settings.gemini_api_key:
        try:
            client = gemini_client()
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
            result = _normalize_insufficient_citations(result)
            _validate_cited_answer(
                result,
                allowed_citations=allowed_citations,
                protected_context=validation_context,
            )
            return result, "gemini"
        except Exception as error:
            _log_provider_failure("gemini", error)
            if not settings.allow_offline_demo:
                raise
    if not settings.allow_offline_demo:
        raise RuntimeError("A reasoning API key is required when offline demo mode is disabled")
    result = CitedAnswer(
        answer=_offline_answer(question, offline_chunks),
        citations=sorted(
            allowed_citations,
            key=lambda value: int(value.removeprefix("SOURCE-")),
        ),
        insufficient_evidence=False,
    )
    _validate_cited_answer(
        result,
        allowed_citations=allowed_citations,
        protected_context=validation_context,
    )
    return result, "offline-demo"


def answer_query_with_citations(
    question: str,
    hits: list[RetrievalHit],
    *,
    response_style: str = "analysis",
) -> tuple[CitedAnswer, str]:
    context, allowed_citations = _cited_context(hits)
    if contains_known_pii(question) or contains_known_pii(context):
        raise ValueError("Refusing to send recognized PII to the reasoning service")
    if not hits:
        return CitedAnswer(
            answer="No matching protected records are available.",
            citations=[],
            insufficient_evidence=True,
        ), "no-evidence"

    return _answer_cited_context(
        question,
        context,
        allowed_citations,
        offline_chunks=[hit.retrieval_text for hit in hits],
        response_style=response_style,
    )


def answer_all_query_with_citations(
    question: str,
    hits: list[RetrievalHit],
    *,
    response_style: str = "analysis",
) -> tuple[CitedAnswer, str]:
    """Analyze every SQL-eligible record, batching before synthesis when necessary."""
    if len(hits) <= ANALYZE_ALL_BATCH_SIZE:
        return answer_query_with_citations(question, hits, response_style=response_style)

    full_context, _all_citations = _cited_context(hits)
    partial_answers: list[CitedAnswer] = []
    modes: list[str] = []
    for offset in range(0, len(hits), ANALYZE_ALL_BATCH_SIZE):
        batch = hits[offset : offset + ANALYZE_ALL_BATCH_SIZE]
        batch_context, batch_citations = _cited_context(batch, citation_offset=offset)
        partial, mode = _answer_cited_context(
            (
                "Produce a concise partial analysis for this batch. Preserve important protected "
                f"tokens and evidence needed to answer: {question}"
            ),
            batch_context,
            batch_citations,
            offline_chunks=[hit.retrieval_text for hit in batch],
            response_style=response_style,
        )
        partial_answers.append(partial)
        modes.append(mode)

    synthesis_context = "\n\n".join(
        f"Batch {index} analysis:\n{partial.answer}\nEvidence: {', '.join(partial.citations)}"
        for index, partial in enumerate(partial_answers, 1)
    )
    synthesis_citations = {
        citation for partial in partial_answers for citation in partial.citations
    }
    result, final_mode = _answer_cited_context(
        question,
        synthesis_context,
        synthesis_citations,
        offline_chunks=[partial.answer for partial in partial_answers],
        protected_context=full_context,
        response_style=response_style,
    )
    modes.append(final_mode)
    mode = final_mode if len(set(modes)) == 1 else "mixed"
    return result, mode
