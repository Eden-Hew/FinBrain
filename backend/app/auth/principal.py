import hashlib
import hmac
from dataclasses import dataclass
from uuid import UUID

from app.config import get_settings
from app.schemas import UserRole


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    user_id: UUID
    email: str | None
    role: UserRole
    tenant_id: UUID

    @property
    def actor_ref(self) -> str:
        return hmac.new(
            get_settings().token_root_secret.encode(),
            f"auth-user:{self.user_id}".encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
