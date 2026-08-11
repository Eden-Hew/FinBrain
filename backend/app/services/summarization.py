import re

from app.config import get_settings
from app.schemas import ProtectedSummary, SummaryPriority
from app.security.detect import contains_known_pii

TOKEN_PATTERN = re.compile(r"(?:[A-Z]+_[0-9a-f]{10}|AMOUNT_BAND_\d+)")

SYSTEM_INSTRUCTION = (
    "Summarize the supplied protected business record as structured JSON. The record contains "
    "privacy tokens representing values you cannot see. Preserve any token you use exactly as "
    "written. Never expand, alter, infer, or invent a token or hidden value. Base the output only "
    "on the supplied record. Use a short snake_case category."
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


def summarize_protected_text(text: str) -> tuple[ProtectedSummary, str]:
    """Summarize text only after the protected boundary has removed recognizable PII."""
    if contains_known_pii(text):
        raise ValueError("Refusing to summarize text containing recognized PII")
    settings = get_settings()
    if settings.gemini_api_key:
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
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
        raise RuntimeError("GEMINI_API_KEY is required when offline demo mode is disabled")
    result = _offline_summary(text)
    _validate_summary(result, text)
    return result, "offline-demo"
