import hashlib
import hmac
import re
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ProtectedTokenRegistry, TokenVaultEntry
from app.security.keyring import encrypt_vault_value

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
    "TGUSER": ["finance_ops", "owner_director", "compliance"],
    "TGCHAT": ["compliance"],
}

AMOUNT_BANDS = [500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]


def _pending_token(db: Session, model: type, token: str) -> bool:
    """Return whether this session already stages the token before a flush."""
    return any(isinstance(row, model) and getattr(row, "token", None) == token for row in db.new)


def _has_token(db: Session, model: type, token: str) -> bool:
    return _pending_token(db, model, token) or db.get(model, token) is not None


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


def _masked_value(label: str, text: str, token: str) -> str:
    if label == "AMOUNT":
        return f"AMOUNT_BAND_{_band_index(_parse_amount(text))}"
    return {
        "NRIC": "******-**-****",
        "PHONE": "01*-***-****",
        "EMAIL": "*****@*******.***",
        "BANKACC": "****-****-****",
        "CARD": "**** **** **** ****",
        "ADDR": "[address — restricted]",
        "PERSON": "[person — restricted]",
        "ORG": "[organization — restricted]",
    }.get(label, f"[{label.lower()} — restricted]")


def derive_token(entity_type: str, text: str, tenant_id: str) -> str:
    """Derive a tenant-scoped token without persisting or encrypting the value."""
    label = entity_type.upper()
    if label == "AMOUNT":
        canonical = f"{tenant_id}:{_canonical_amount(text)}"
        digest = hmac.new(
            get_settings().token_identity_secret.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()[:10]
        return f"AMOUNT_BAND_{_band_index(_parse_amount(text))}_{digest}"
    canonical = f"{tenant_id}:{text.strip().casefold()}"
    digest = hmac.new(
        get_settings().token_identity_secret.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()[:10]
    return f"{label}_{digest}"


def _token_for(span, tenant_id: str) -> str:
    """Derive a token that is unique per (tenant, raw value), not just per raw value —
    otherwise two tenants sharing the same name/phone/amount would collide on the same
    token, and the second tenant's value would silently never be stored (see
    persist_vault_entries' idempotent-by-token insert)."""
    label = LABEL_TOKEN_MAP.get(span.label, "MISC")
    return derive_token(label, span.text, tenant_id)


def tokenize_record(
    text: str,
    spans: list,
    source_record_id: str,
    tenant_id: str,
    db: Session | None = None,
) -> tuple[str, list[TokenVaultEntry]]:
    sanitized = text
    vault_entries: dict[str, TokenVaultEntry] = {}
    for span in sorted(spans, key=lambda item: item.start, reverse=True):
        token = _token_for(span, tenant_id)
        sanitized = f"{sanitized[: span.start]}{token}{sanitized[span.end :]}"
        label = LABEL_TOKEN_MAP.get(span.label, "MISC")
        if token in vault_entries or db is None:
            continue
        vault_value = _display_amount(span.text) if label == "AMOUNT" else span.text
        ciphertext, nonce, key_version = encrypt_vault_value(
            db,
            token=token,
            entity_type=label,
            source_record_id=source_record_id,
            value=vault_value,
        )
        vault_entries[token] = TokenVaultEntry(
            token=token,
            tenant_id=tenant_id,
            entity_type=label,
            encrypted_value=ciphertext,
            nonce=nonce,
            key_version=key_version,
            masked_value=_masked_value(label, span.text, token),
            encryption_algorithm="AES-256-GCM",
            allowed_roles=ACL_POLICY.get(label, ["compliance"]),
            sensitivity="high" if label in {"NRIC", "CARD"} else "medium",
            source_record_id=source_record_id,
        )
        if not _has_token(db, ProtectedTokenRegistry, token):
            db.add(
                ProtectedTokenRegistry(
                    token=token,
                    tenant_id=tenant_id,
                    entity_type=label,
                    masked_value=_masked_value(label, span.text, token),
                )
            )
    return sanitized, list(vault_entries.values())


def persist_vault_entries(db: Session, entries: list[TokenVaultEntry]) -> None:
    """Persist ciphertext and safe public token metadata idempotently."""
    for entry in entries:
        if not _has_token(db, TokenVaultEntry, entry.token):
            db.add(entry)


def protect_scalar(
    db: Session,
    *,
    entity_type: str,
    value: str,
    source_record_id: str,
    tenant_id: str,
) -> str:
    """Protect one explicitly classified value that detectors cannot safely infer."""
    label = entity_type.upper()
    token = derive_token(label, value, tenant_id)
    masked = {
        "TGUSER": "telegram-user-********",
        "TGCHAT": "telegram-chat-********",
        "PERSON": "[person — restricted]",
        "EMAIL": "*****@*******.***",
        "PHONE": "01*-***-****",
    }.get(label, f"[{label.lower()} — restricted]")
    if not _has_token(db, TokenVaultEntry, token):
        ciphertext, nonce, key_version = encrypt_vault_value(
            db,
            token=token,
            entity_type=label,
            source_record_id=source_record_id,
            value=value,
        )
        db.add(
            TokenVaultEntry(
                token=token,
                tenant_id=tenant_id,
                entity_type=label,
                encrypted_value=ciphertext,
                nonce=nonce,
                key_version=key_version,
                masked_value=masked,
                encryption_algorithm="AES-256-GCM",
                allowed_roles=ACL_POLICY.get(label, ["compliance"]),
                sensitivity="medium",
                source_record_id=source_record_id,
            )
        )
    if not _has_token(db, ProtectedTokenRegistry, token):
        db.add(
            ProtectedTokenRegistry(
                token=token,
                tenant_id=tenant_id,
                entity_type=label,
                masked_value=masked,
            )
        )
    return token
