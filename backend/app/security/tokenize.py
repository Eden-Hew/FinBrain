import hashlib
import hmac
import re
from decimal import Decimal, InvalidOperation

from app.config import get_settings
from app.models import TokenVaultEntry
from app.security.crypto import derive_key, encrypt_value

LABEL_TOKEN_MAP = {
    "person": "PERSON",
    "national id": "NRIC",
    "phone number": "PHONE",
    "email": "EMAIL",
    "bank account number": "BANKACC",
    "credit card number": "CARD",
    "address": "ADDR",
    "amount of money": "AMOUNT",
    "company name": "ORG",
}

ACL_POLICY = {
    "NRIC": ["compliance", "owner_director"],
    "CARD": ["compliance"],
    "BANKACC": ["finance_ops", "owner_director", "compliance"],
    "PHONE": ["finance_ops", "owner_director", "compliance", "general_employee"],
    "PERSON": ["finance_ops", "owner_director", "compliance", "general_employee"],
    "ADDR": ["compliance", "owner_director"],
    "EMAIL": ["finance_ops", "owner_director", "compliance", "general_employee"],
    "ORG": ["finance_ops", "owner_director", "compliance", "general_employee"],
    "AMOUNT": ["finance_ops", "owner_director", "compliance"],
}

AMOUNT_BANDS = [500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]


def _parse_amount(text: str) -> Decimal:
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    try:
        return Decimal(match.group().replace(",", "")) if match else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def _band_index(value: Decimal) -> int:
    for index, upper in enumerate(AMOUNT_BANDS):
        if value < upper:
            return index
    return len(AMOUNT_BANDS)


def amount_band_index(value: Decimal) -> int:
    """Return the documented non-sensitive range index for a validated amount."""
    return _band_index(value)


def _canonical_amount(text: str) -> str:
    return f"MYR:{_parse_amount(text).quantize(Decimal('0.01'))}"


def _display_amount(text: str) -> str:
    value = _parse_amount(text).quantize(Decimal("0.01"))
    return f"RM {value:,.0f}" if value == value.to_integral() else f"RM {value:,.2f}"


def _token_for(span) -> str:
    label = LABEL_TOKEN_MAP.get(span.label, "MISC")
    if label == "AMOUNT":
        canonical = _canonical_amount(span.text)
        digest = hmac.new(
            get_settings().token_root_secret.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()[:10]
        return f"AMOUNT_BAND_{_band_index(_parse_amount(span.text))}_{digest}"
    digest = hmac.new(
        get_settings().token_root_secret.encode(),
        span.text.strip().casefold().encode(),
        hashlib.sha256,
    ).hexdigest()[:10]
    return f"{label}_{digest}"


def tokenize_record(
    text: str, spans: list, source_record_id: str
) -> tuple[str, list[TokenVaultEntry]]:
    sanitized = text
    vault_entries: dict[str, TokenVaultEntry] = {}
    for span in sorted(spans, key=lambda item: item.start, reverse=True):
        token = _token_for(span)
        sanitized = f"{sanitized[: span.start]}{token}{sanitized[span.end :]}"
        label = LABEL_TOKEN_MAP.get(span.label, "MISC")
        if token in vault_entries:
            continue
        key = derive_key(info=f"vault:{token}".encode())
        vault_value = _display_amount(span.text) if label == "AMOUNT" else span.text
        ciphertext, nonce = encrypt_value(vault_value, key)
        vault_entries[token] = TokenVaultEntry(
            token=token,
            entity_type=label,
            encrypted_value=ciphertext,
            nonce=nonce,
            allowed_roles=ACL_POLICY.get(label, ["compliance"]),
            sensitivity="high" if label in {"NRIC", "CARD"} else "medium",
            source_record_id=source_record_id,
        )
    return sanitized, list(vault_entries.values())
