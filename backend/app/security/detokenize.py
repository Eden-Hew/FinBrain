import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TokenVaultEntry
from app.security.crypto import decrypt_value, derive_key
from app.services.audit import write_audit_entry

TOKEN_PATTERN = re.compile(r"(?:[A-Z]+_[0-9a-f]{10}|AMOUNT_BAND_\d+)")
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


def hash_query(question: str) -> str:
    return hashlib.sha256(question.encode()).hexdigest()[:16]


def _band_label(token: str) -> str:
    index = int(token.rsplit("_", 1)[-1])
    return BAND_LABELS[index] if index < len(BAND_LABELS) else BAND_LABELS[-1]


def detokenize_response(db: Session, text: str, role: str, query_hash: str) -> str:
    result = text
    for token in sorted(set(TOKEN_PATTERN.findall(text)), key=len, reverse=True):
        if token.startswith("AMOUNT_BAND_"):
            result = result.replace(token, _band_label(token))
            continue
        entry = db.scalar(select(TokenVaultEntry).where(TokenVaultEntry.token == token))
        if entry is None:
            continue
        authorized = role in json.loads(entry.allowed_roles)
        if authorized:
            key = derive_key(info=f"vault:{token}".encode())
            replacement = decrypt_value(entry.encrypted_value, entry.nonce, key)
        else:
            replacement = f"[{entry.entity_type.lower()} — restricted]"
        result = result.replace(token, replacement)
        write_audit_entry(db, role, token, authorized, query_hash)
    db.commit()
    return result
