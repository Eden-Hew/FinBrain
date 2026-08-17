import hashlib
import os
import time
import uuid
from dataclasses import dataclass, field

from app.security.crypto import decrypt_value, derive_key_from_secret, encrypt_value


@dataclass(frozen=True, slots=True)
class DisclosureGrant:
    session_id: str
    token: str
    ciphertext: bytes
    nonce: bytes


@dataclass(slots=True)
class QueryDisclosureSession:
    query_hash: str
    actor_ref: str
    role: str
    turn_ref: str
    ttl_seconds: float = 30.0
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _secret: bytes | None = field(default_factory=lambda: os.urandom(32), repr=False)
    _created: float = field(default_factory=time.monotonic, repr=False)
    _consumed: set[str] = field(default_factory=set, repr=False)

    @property
    def public_ref(self) -> str:
        return hashlib.sha256(self.session_id.encode()).hexdigest()[:16]

    @property
    def consumed_count(self) -> int:
        return len(self._consumed)

    def _aad(self, token: str) -> bytes:
        return "\x1f".join(
            [
                "finbrain-query-disclosure-v1",
                self.session_id,
                self.query_hash,
                self.turn_ref,
                self.actor_ref,
                self.role,
                token,
            ]
        ).encode()

    def _grant_key(self, token: str) -> bytes:
        if self._secret is None:
            raise ValueError("disclosure_session_closed")
        if time.monotonic() - self._created > self.ttl_seconds:
            self.close()
            raise ValueError("disclosure_session_expired")
        return derive_key_from_secret(
            self._secret,
            info=f"finbrain:single-use-grant:{self.session_id}:{token}".encode(),
        )

    def issue(self, token: str, plaintext: str) -> DisclosureGrant:
        if token in self._consumed:
            raise ValueError("disclosure_grant_already_consumed")
        ciphertext, nonce = encrypt_value(
            plaintext,
            self._grant_key(token),
            self._aad(token),
        )
        return DisclosureGrant(self.session_id, token, ciphertext, nonce)

    def consume(self, grant: DisclosureGrant) -> str:
        if grant.session_id != self.session_id:
            raise ValueError("disclosure_grant_wrong_session")
        if grant.token in self._consumed:
            raise ValueError("disclosure_grant_replayed")
        plaintext = decrypt_value(
            grant.ciphertext,
            grant.nonce,
            self._grant_key(grant.token),
            self._aad(grant.token),
        )
        self._consumed.add(grant.token)
        return plaintext

    def close(self) -> None:
        self._secret = None


def new_disclosure_session(
    *,
    query_hash: str,
    actor_ref: str,
    role: str,
    turn_ref: str = "unbound",
) -> QueryDisclosureSession:
    return QueryDisclosureSession(
        query_hash=query_hash,
        actor_ref=actor_ref,
        role=role,
        turn_ref=turn_ref,
    )
