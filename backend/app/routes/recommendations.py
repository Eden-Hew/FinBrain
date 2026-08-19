from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.principal import AuthPrincipal
from app.db import get_db
from app.schemas import (
    ProcessAnalysisRequest,
    QueryRecommendationRequest,
    RecommendationDecisionRequest,
    RecommendationResponse,
    UserRole,
)
from app.services.recommendations import (
    analyze_processes,
    create_recommendation_from_turn,
    decide_recommendation,
    list_recommendations,
)

router = APIRouter(tags=["process-optimization"])


@router.post(
    "/query-turns/{turn_id}/recommendations",
    response_model=RecommendationResponse,
)
def create_from_query(
    turn_id: int,
    payload: QueryRecommendationRequest,
    principal: AuthPrincipal = Depends(
        require_roles(UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)
    ),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    try:
        return create_recommendation_from_turn(
            db,
            turn_id,
            role=principal.role,
            tenant_id=str(principal.tenant_id),
            action_id=payload.action_id,
            suggested_owner=payload.suggested_owner,
            actor_ref=principal.actor_ref,
            created_by_user_id=str(principal.user_id),
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/process-analysis", response_model=RecommendationResponse)
def process_analysis(
    payload: ProcessAnalysisRequest,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    try:
        return analyze_processes(
            db,
            payload,
            role=principal.role,
            tenant_id=str(principal.tenant_id),
            actor_ref=principal.actor_ref,
            created_by_user_id=str(principal.user_id),
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/recommendations", response_model=list[RecommendationResponse])
def recommendations(
    principal: AuthPrincipal = Depends(
        require_roles(UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE)
    ),
    db: Session = Depends(get_db),
) -> list[RecommendationResponse]:
    return list_recommendations(db, str(principal.tenant_id))


def _decision(
    recommendation_id: int,
    decision: str,
    payload: RecommendationDecisionRequest,
    principal: AuthPrincipal,
    db: Session,
) -> RecommendationResponse:
    try:
        return decide_recommendation(
            db,
            recommendation_id,
            decision=decision,
            role=principal.role,
            tenant_id=str(principal.tenant_id),
            comment=payload.comment,
            actor_ref=principal.actor_ref,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/recommendations/{recommendation_id}/approve", response_model=RecommendationResponse)
def approve(
    recommendation_id: int,
    payload: RecommendationDecisionRequest,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    return _decision(recommendation_id, "approved", payload, principal, db)


@router.post("/recommendations/{recommendation_id}/reject", response_model=RecommendationResponse)
def reject(
    recommendation_id: int,
    payload: RecommendationDecisionRequest,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    return _decision(recommendation_id, "rejected", payload, principal, db)


@router.post(
    "/recommendations/{recommendation_id}/mark-implemented",
    response_model=RecommendationResponse,
)
def mark_implemented(
    recommendation_id: int,
    payload: RecommendationDecisionRequest,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    return _decision(recommendation_id, "implemented", payload, principal, db)
