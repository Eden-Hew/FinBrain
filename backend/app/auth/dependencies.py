from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.jwt import AccessTokenError, verify_access_token
from app.auth.principal import AuthPrincipal
from app.db import get_db, set_rls_context
from app.models import AuthUserRole
from app.schemas import UserRole

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthPrincipal:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication_required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = verify_access_token(credentials.credentials)
        user_id = UUID(str(claims["sub"]))
    except (AccessTokenError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_access_token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    assignment = db.get(AuthUserRole, str(user_id))
    if assignment is None or not assignment.active:
        raise HTTPException(status_code=403, detail="user_not_provisioned")
    try:
        role = UserRole(assignment.user_role)
    except ValueError as error:
        raise HTTPException(status_code=403, detail="invalid_user_role") from error
    token_role = claims.get("user_role")
    if token_role is not None and token_role != role.value:
        raise HTTPException(status_code=403, detail="stale_user_role_claim")
    principal = AuthPrincipal(user_id=user_id, email=claims.get("email"), role=role)
    set_rls_context(
        db,
        user_id=str(principal.user_id),
        user_role=principal.role.value,
        actor_ref=principal.actor_ref,
    )
    return principal


CurrentUser = Annotated[AuthPrincipal, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[AuthPrincipal], AuthPrincipal]:
    allowed = frozenset(roles)

    def dependency(principal: CurrentUser) -> AuthPrincipal:
        if principal.role not in allowed:
            raise HTTPException(status_code=403, detail="insufficient_role")
        return principal

    return dependency
