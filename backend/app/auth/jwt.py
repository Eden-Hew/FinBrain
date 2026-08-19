from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.config import get_settings


class AccessTokenError(ValueError):
    pass


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=600)


def verify_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_url:
        raise AccessTokenError("supabase_auth_not_configured")
    try:
        signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=settings.supabase_jwt_algorithm_list,
            audience=settings.supabase_jwt_audience,
            issuer=settings.effective_supabase_jwt_issuer,
            leeway=30,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as error:
        raise AccessTokenError("invalid_access_token") from error
    if claims.get("role") != "authenticated":
        raise AccessTokenError("invalid_supabase_role")
    return claims
