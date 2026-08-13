import logging
import re
from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
    text: str
    label: str
    source: str


@dataclass(frozen=True, slots=True)
class DetectorStatus:
    configured: bool
    loaded: bool
    device: str
    model_name: str
    failure_code: str | None = None


REGEX_PATTERNS = [
    (re.compile(r"\b\d{6}-\d{2}-\d{4}\b"), "national id"),
    (re.compile(r"\b(?:\+?60|0)1[0-46-9][\-\s]?\d{3,4}[\-\s]?\d{4}\b"), "phone number"),
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "email"),
    (re.compile(r"\b(?:\d[ -]?){9,16}\b"), "bank account number"),
    (re.compile(r"\bRM\s?\d[\d,]*(?:\.\d{1,2})?\b", re.IGNORECASE), "amount of money"),
]

PII_LABELS = [
    "person",
    "phone number",
    "email",
    "address",
    "amount of money",
    "bank account number",
    "credit card number",
    "national id",
    "company name",
]

_model = None
_model_failed = False
logger = logging.getLogger(__name__)


def _get_model():
    global _model, _model_failed
    if _model is None and not _model_failed:
        try:
            import torch
            from gliner import GLiNER

            settings = get_settings()
            device = settings.gliner_device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            _model = GLiNER.from_pretrained(settings.gliner_model_name).to(device)
            _model.eval()
            logger.info("GLiNER loaded on %s", device)
        except Exception:
            logger.exception("GLiNER failed to load; regex-only detection remains active")
            _model_failed = True
    return _model


def _regex_detect(text: str) -> list[Span]:
    spans: list[Span] = []
    for pattern, label in REGEX_PATTERNS:
        spans.extend(
            Span(m.start(), m.end(), m.group(), label, "regex") for m in pattern.finditer(text)
        )
    return spans


def _gliner_detect(text: str, threshold: float = 0.4) -> list[Span]:
    if not get_settings().enable_gliner or not (model := _get_model()):
        return []
    return [
        Span(entity["start"], entity["end"], entity["text"], entity["label"], "gliner")
        for entity in model.predict_entities(text, PII_LABELS, threshold=threshold)
    ]


def _overlaps(left: Span, right: Span) -> bool:
    return left.start < right.end and right.start < left.end


def detect_spans(text: str) -> list[Span]:
    """Return non-overlapping spans, preferring deterministic regex matches."""
    accepted: list[Span] = []
    candidates = _regex_detect(text) + _gliner_detect(text)
    # REGEX_PATTERNS is ordered from most to least specific. Stable sorting by
    # position preserves that precedence when a generic account match overlaps
    # a phone number or NRIC.
    candidates.sort(key=lambda span: (span.source != "regex", span.start))
    for candidate in candidates:
        if not any(_overlaps(candidate, current) for current in accepted):
            accepted.append(candidate)
    return sorted(accepted, key=lambda span: span.start)


def contains_known_pii(text: str) -> bool:
    """Fast safety-net used immediately before any external model call."""
    return bool(_regex_detect(text))


def warm_detector() -> DetectorStatus:
    settings = get_settings()
    if not settings.enable_gliner:
        return DetectorStatus(
            configured=False,
            loaded=False,
            device=settings.gliner_device,
            model_name=settings.gliner_model_name,
            failure_code="disabled",
        )
    model = _get_model()
    return DetectorStatus(
        configured=True,
        loaded=model is not None,
        device=settings.gliner_device,
        model_name=settings.gliner_model_name,
        failure_code=None if model is not None else "model_load_failed",
    )


def get_detector_status() -> DetectorStatus:
    settings = get_settings()
    return DetectorStatus(
        configured=settings.enable_gliner,
        loaded=_model is not None,
        device=settings.gliner_device,
        model_name=settings.gliner_model_name,
        failure_code="model_load_failed" if _model_failed else None,
    )
