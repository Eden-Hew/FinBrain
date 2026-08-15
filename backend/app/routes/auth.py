from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.schemas import AuthMeResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthMeResponse)
def me(principal: CurrentUser) -> AuthMeResponse:
    return AuthMeResponse(
        user_id=str(principal.user_id),
        email=principal.email,
        role=principal.role,
    )
