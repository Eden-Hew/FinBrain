from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.principal import AuthPrincipal
from app.db import get_db
from app.schemas import PrivacyEraseResponse, PrivacyTokenResponse, UserRole
from app.security.detokenize import hash_query
from app.services.privacy import erase_token, export_token

router = APIRouter(tags=["privacy"])


@router.get("/privacy/tokens/{token}", response_model=PrivacyTokenResponse)
def get_privacy_token(
    token: str,
    principal: AuthPrincipal = Depends(require_roles(UserRole.COMPLIANCE)),
    db: Session = Depends(get_db),
) -> PrivacyTokenResponse:
    try:
        return export_token(
            db,
            token,
            str(principal.tenant_id),
            role=principal.role,
            query_hash=hash_query(f"privacy-export:{token}"),
            actor_ref=principal.actor_ref,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/privacy/tokens/{token}/erase", response_model=PrivacyEraseResponse)
def erase_privacy_token(
    token: str,
    principal: AuthPrincipal = Depends(require_roles(UserRole.COMPLIANCE)),
    db: Session = Depends(get_db),
) -> PrivacyEraseResponse:
    try:
        return erase_token(
            db,
            token,
            str(principal.tenant_id),
            role=principal.role,
            actor_ref=principal.actor_ref,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
