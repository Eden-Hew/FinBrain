import hashlib
import hmac
import secrets
import threading
import time

from app.config import get_settings
from app.integrations.telegram.types import CaptureDraft


class DraftStore:
    def __init__(self) -> None:
        self._drafts: dict[int, CaptureDraft] = {}
        self._lock = threading.Lock()

    def new_nonce(self) -> str:
        return secrets.token_urlsafe(9)

    def put(self, draft: CaptureDraft) -> None:
        with self._lock:
            self._prune_locked()
            self._drafts[draft.telegram_user_id] = draft

    def get(self, user_id: int) -> CaptureDraft | None:
        with self._lock:
            self._prune_locked()
            return self._drafts.get(user_id)

    def pop(self, user_id: int, nonce: str | None = None) -> CaptureDraft | None:
        with self._lock:
            self._prune_locked()
            draft = self._drafts.get(user_id)
            if draft is None or (nonce is not None and draft.nonce != nonce):
                return None
            return self._drafts.pop(user_id)

    def clear(self) -> None:
        with self._lock:
            self._drafts.clear()

    def _prune_locked(self) -> None:
        now = time.monotonic()
        expired = [key for key, draft in self._drafts.items() if draft.expires_at_monotonic <= now]
        for key in expired:
            self._drafts.pop(key, None)


def sign_callback(action: str, nonce: str, user_id: int) -> str:
    message = f"{action}:{nonce}:{user_id}"
    signature = hmac.new(
        get_settings().token_root_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()[:12]
    return f"{action}:{nonce}:{signature}"


def verify_callback(data: str, user_id: int) -> tuple[str, str] | None:
    try:
        action, nonce, signature = data.split(":", 2)
    except ValueError:
        return None
    expected = sign_callback(action, nonce, user_id).rsplit(":", 1)[1]
    if not secrets.compare_digest(signature, expected):
        return None
    return action, nonce


draft_store = DraftStore()
