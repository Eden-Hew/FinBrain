import hashlib
import hmac

from app.config import get_settings
from app.schemas import UserRole


def operator_role(user_id: int, chat_type: str) -> UserRole | None:
    settings = get_settings()
    if chat_type not in settings.telegram_allowed_chat_type_set:
        return None
    return settings.telegram_operator_role_map.get(user_id)


def actor_ref(user_id: int) -> str:
    digest = hmac.new(
        get_settings().token_root_secret.encode(),
        f"telegram-actor:{user_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]
