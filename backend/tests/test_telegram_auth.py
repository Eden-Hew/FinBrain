from types import SimpleNamespace

from app.integrations.telegram import auth
from app.schemas import UserRole


def test_operator_authorization_uses_numeric_id_and_private_chat(monkeypatch):
    settings = SimpleNamespace(
        telegram_allowed_chat_type_set={"private"},
        telegram_operator_role_map={123: UserRole.OWNER_DIRECTOR},
        token_root_secret="test-secret",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    assert auth.operator_role(123, "private") is UserRole.OWNER_DIRECTOR
    assert auth.operator_role(123, "group") is None
    assert auth.operator_role(999, "private") is None
    assert "123" not in auth.actor_ref(123)
