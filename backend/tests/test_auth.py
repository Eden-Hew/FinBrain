from types import SimpleNamespace
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import dependencies
from app.auth import jwt as jwt_service
from app.models import DEFAULT_TENANT_ID, AuthUserRole, Base
from app.schemas import UserRole
from app.services.conversations import create_conversation, get_active_conversation

USER_ID = UUID("50000000-0000-0000-0000-000000000005")
TENANT_A = DEFAULT_TENANT_ID
TENANT_B = "00000000-0000-0000-0000-000000000002"


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token")


def test_principal_uses_database_role_and_rejects_stale_claim(monkeypatch):
    engine, db = _database()
    try:
        db.add(
            AuthUserRole(
                user_id=str(USER_ID),
                tenant_id=TENANT_A,
                user_role=UserRole.FINANCE_OPS.value,
                active=True,
            )
        )
        db.commit()
        monkeypatch.setattr(
            dependencies,
            "verify_access_token",
            lambda _token: {
                "sub": str(USER_ID),
                "email": "finance@finbrain.test",
                "role": "authenticated",
                "user_role": "finance_ops",
                "tenant_id": TENANT_A,
            },
        )
        principal = dependencies.get_current_user(_credentials(), db)
        assert principal.user_id == USER_ID
        assert principal.role is UserRole.FINANCE_OPS
        assert str(principal.tenant_id) == TENANT_A
        assert "finance@finbrain.test" not in principal.actor_ref

        monkeypatch.setattr(
            dependencies,
            "verify_access_token",
            lambda _token: {
                "sub": str(USER_ID),
                "role": "authenticated",
                "user_role": "owner_director",
                "tenant_id": TENANT_A,
            },
        )
        with pytest.raises(HTTPException) as error:
            dependencies.get_current_user(_credentials(), db)
        assert error.value.status_code == 403
        assert error.value.detail == "stale_user_role_claim"
    finally:
        db.close()
        engine.dispose()


def test_missing_token_and_unprovisioned_user_are_denied(monkeypatch):
    engine, db = _database()
    try:
        with pytest.raises(HTTPException) as missing:
            dependencies.get_current_user(None, db)
        assert missing.value.status_code == 401

        monkeypatch.setattr(
            dependencies,
            "verify_access_token",
            lambda _token: {"sub": str(USER_ID), "role": "authenticated", "tenant_id": TENANT_A},
        )
        with pytest.raises(HTTPException) as unprovisioned:
            dependencies.get_current_user(_credentials(), db)
        assert unprovisioned.value.status_code == 403
        assert unprovisioned.value.detail == "user_not_provisioned"
    finally:
        db.close()
        engine.dispose()


def test_jwt_verification_checks_signature_issuer_audience_and_role(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
        supabase_jwt_algorithm_list=["RS256"],
        supabase_jwt_audience="authenticated",
        effective_supabase_jwt_issuer="https://project.supabase.co/auth/v1",
    )
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    monkeypatch.setattr(
        jwt_service,
        "_jwks_client",
        lambda _url: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
        ),
    )
    claims = {
        "sub": str(USER_ID),
        "iss": settings.effective_supabase_jwt_issuer,
        "aud": "authenticated",
        "exp": 4_102_444_800,
        "role": "authenticated",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})
    assert jwt_service.verify_access_token(token)["sub"] == str(USER_ID)

    wrong_audience = jwt.encode(
        {**claims, "aud": "other"}, private_key, algorithm="RS256", headers={"kid": "test"}
    )
    with pytest.raises(jwt_service.AccessTokenError):
        jwt_service.verify_access_token(wrong_audience)


def test_conversation_owner_cannot_be_crossed():
    engine, db = _database()
    try:
        conversation = create_conversation(db, TENANT_A, str(USER_ID))
        assert (
            get_active_conversation(db, conversation.id, TENANT_A, str(USER_ID)).id
            == conversation.id
        )
        with pytest.raises(ValueError, match="conversation_not_found"):
            get_active_conversation(
                db,
                conversation.id,
                TENANT_A,
                "60000000-0000-0000-0000-000000000006",
            )
    finally:
        db.close()
        engine.dispose()


def test_conversation_tenant_cannot_be_crossed():
    """A principal from tenant B must never be able to read tenant A's conversation,
    even with the correct conversation id and no created_by_user_id mismatch."""
    engine, db = _database()
    try:
        conversation = create_conversation(db, TENANT_A, str(USER_ID))
        assert get_active_conversation(db, conversation.id, TENANT_A).id == conversation.id
        with pytest.raises(ValueError, match="conversation_not_found"):
            get_active_conversation(db, conversation.id, TENANT_B)
    finally:
        db.close()
        engine.dispose()
