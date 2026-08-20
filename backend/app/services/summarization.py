import re

from app.config import get_settings
from app.schemas import ProtectedSummary, SummaryPriority
from app.security.detect import contains_known_pii
from app.services.gemini import gemini_client
from app.services.morpheus import morpheus_chat

TOKEN_PATTERN = re.compile(r"(?:AMOUNT_BAND_\d+_[0-9a-f]{10}|[A-Z]+_[0-9a-f]{10})")

SYSTEM_INSTRUCTION = (
    "Summarize the supplied protected business record as structured JSON. The record contains "
    "privacy tokens representing values you cannot see. An AMOUNT_BAND_n_xxxxxxxxxx token is an "
    "exact hidden amount whose band indicates only an approximate range. Preserve every token you "
    "use completely and exactly. Never expand, alter, infer, or invent a token or hidden value. "
    "Base the output only on the supplied record. Use a short snake_case category. "
    "For an email only, optionally report sender_identity_token when a PERSON_ or ORG_ token "
    "is explicitly the From display name or follows a first-person introduction such as "
    "'I am', 'I'm', 'My name is', or 'This is'. Set the matching sender_identity_basis and a "
    "0-to-1 confidence. Never treat a person merely mentioned in the message as the sender."
)


def _compact_excerpt(text: str, limit: int = 500) -> str:
    words = text.split()
    selected: list[str] = []
    length = 0
    for word in words:
        added = len(word) + (1 if selected else 0)
        if length + added > limit:
            break
        selected.append(word)
        length += added
    return " ".join(selected) or text[:limit]


def _offline_summary(text: str) -> ProtectedSummary:
    lowered = text.casefold()
    if any(term in lowered for term in ("overdue", "owe", "outstanding", "bounced")):
        category = "payment_attention"
        action_required = True
    elif any(term in lowered for term in ("invoice", "payment", "account")):
        category = "financial_record"
        action_required = False
    else:
        category = "general_record"
        action_required = False
    if any(term in lowered for term in ("urgent", "bounced", "overdue")):
        priority = SummaryPriority.HIGH
    elif action_required:
        priority = SummaryPriority.MEDIUM
    else:
        priority = SummaryPriority.LOW
    return ProtectedSummary(
        summary=_compact_excerpt(text),
        category=category,
        action_required=action_required,
        priority=priority,
    )


def _validate_summary(summary: ProtectedSummary, protected_text: str) -> None:
    serialized = summary.model_dump_json()
    if contains_known_pii(serialized):
        raise ValueError("The generated summary contains recognizable sensitive data")
    allowed_tokens = set(TOKEN_PATTERN.findall(protected_text))
    output_tokens = set(TOKEN_PATTERN.findall(serialized))
    if invented := output_tokens - allowed_tokens:
        raise ValueError(f"The generated summary contains unknown protected tokens: {invented}")
    identity_values = (
        summary.sender_identity_token,
        summary.sender_identity_basis,
        summary.sender_identity_confidence,
    )
    if any(value is not None for value in identity_values) and not all(
        value is not None for value in identity_values
    ):
        raise ValueError("Sender identity claim fields must be supplied together")
    if summary.sender_identity_token is not None:
        if not summary.sender_identity_token.startswith(("PERSON_", "ORG_")):
            raise ValueError("Sender identity claim must use a protected person or organization")
        if summary.sender_identity_token not in allowed_tokens:
            raise ValueError("Sender identity claim token is not present in the protected record")


def summarize_protected_text(text: str) -> tuple[ProtectedSummary, str]:
    """Summarize text only after the protected boundary has removed recognizable PII."""
    if contains_known_pii(text):
        raise ValueError("Refusing to summarize text containing recognized PII")
    settings = get_settings()
    if settings.morpheus_api_key:
        try:
            schema = ProtectedSummary.model_json_schema()
            response = morpheus_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            f"{SYSTEM_INSTRUCTION} Return only JSON matching this schema: {schema}"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
            )
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
            result = ProtectedSummary.model_validate_json(cleaned)
            _validate_summary(result, text)
            return result, "morpheus"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if settings.gemini_api_key:
        try:
            client = gemini_client()
            response = client.models.generate_content(
                model=settings.gemini_reasoning_model,
                contents=text,
                config={
                    "system_instruction": SYSTEM_INSTRUCTION,
                    "response_mime_type": "application/json",
                    "response_schema": ProtectedSummary,
                    "temperature": 0.1,
                },
            )
            if isinstance(response.parsed, ProtectedSummary):
                result = response.parsed
            elif response.parsed is not None:
                result = ProtectedSummary.model_validate(response.parsed)
            else:
                result = ProtectedSummary.model_validate_json(response.text or "")
            _validate_summary(result, text)
            return result, "gemini"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if not settings.allow_offline_demo:
        raise RuntimeError("A reasoning API key is required when offline demo mode is disabled")
    result = _offline_summary(text)
    _validate_summary(result, text)
    return result, "offline-demo"
