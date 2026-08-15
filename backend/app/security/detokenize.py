import hashlib
import hmac
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TokenVaultEntry
from app.security.crypto import decrypt_value, derive_key
from app.services.audit import write_audit_entry

TOKEN_PATTERN = re.compile(r"(?:AMOUNT_BAND_\d+_[0-9a-f]{10}|[A-Z]+_[0-9a-f]{10})")
BAND_LABELS = [
    "<RM500",
    "RM500–1K",
    "RM1K–2.5K",
    "RM2.5K–5K",
    "RM5K–10K",
    "RM10K–25K",
    "RM25K–50K",
    "RM50K–100K",
    "RM100K+",
]


@dataclass(frozen=True, slots=True)
class DetokenizationTrace:
    text: str
    restored_tokens: int
    withheld_tokens: int
    decisions: tuple["DisclosureDecision", ...] = ()


@dataclass(frozen=True, slots=True)
class DisclosureDecision:
    token: str
    entity_type: str
    authorized: bool


def hash_query(question: str) -> str:
    return hmac.new(
        get_settings().token_root_secret.encode(),
        question.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


def _band_label(token: str) -> str:
    match = re.fullmatch(r"AMOUNT_BAND_(\d+)_[0-9a-f]{10}", token)
    if match is None:
        raise ValueError("Invalid protected amount token")
    index = int(match.group(1))
    return BAND_LABELS[index] if index < len(BAND_LABELS) else BAND_LABELS[-1]


def detokenize_response_with_trace(
    db: Session,
    text: str,
    role: str,
    query_hash: str,
    actor_ref: str = "legacy",
) -> DetokenizationTrace:
    result = text
    restored = 0
    withheld = 0
    decisions: list[DisclosureDecision] = []
    for token in sorted(set(TOKEN_PATTERN.findall(text)), key=len, reverse=True):
        entry = db.scalar(select(TokenVaultEntry).where(TokenVaultEntry.token == token))
        if entry is None:
            if token.startswith("AMOUNT_BAND_"):
                result = result.replace(token, _band_label(token))
            continue
        authorized = role in entry.allowed_roles
        if authorized:
            key = derive_key(info=f"vault:{token}".encode())
            replacement = decrypt_value(entry.encrypted_value, entry.nonce, key)
            restored += 1
        else:
            replacement = (
                _band_label(token)
                if entry.entity_type == "AMOUNT"
                else f"[{entry.entity_type.lower()} — restricted]"
            )
            withheld += 1
        result = result.replace(token, replacement)
        decisions.append(
            DisclosureDecision(
                token=token,
                entity_type=entry.entity_type,
                authorized=authorized,
            )
        )
        write_audit_entry(db, role, token, authorized, query_hash, actor_ref=actor_ref)
    db.commit()
    return DetokenizationTrace(
        text=result,
        restored_tokens=restored,
        withheld_tokens=withheld,
        decisions=tuple(decisions),
    )


def detokenize_response(
    db: Session,
    text: str,
    role: str,
    query_hash: str,
    actor_ref: str = "legacy",
) -> str:
    return detokenize_response_with_trace(
        db, text, role, query_hash, actor_ref=actor_ref
    ).text
