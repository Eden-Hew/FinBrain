from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

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
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    try:
        return create_recommendation_from_turn(
            db,
            turn_id,
            role=payload.role,
            action_id=payload.action_id,
            suggested_owner=payload.suggested_owner,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/process-analysis", response_model=RecommendationResponse)
def process_analysis(
    payload: ProcessAnalysisRequest, db: Session = Depends(get_db)
) -> RecommendationResponse:
    try:
        return analyze_processes(db, payload)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/recommendations", response_model=list[RecommendationResponse])
def recommendations(
    role: UserRole = Query(...), db: Session = Depends(get_db)
) -> list[RecommendationResponse]:
    if role not in {UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE}:
        raise HTTPException(status_code=403, detail="Role cannot view process recommendations")
    return list_recommendations(db)


def _decision(
    recommendation_id: int,
    decision: str,
    payload: RecommendationDecisionRequest,
    db: Session,
) -> RecommendationResponse:
    try:
        return decide_recommendation(
            db,
            recommendation_id,
            decision=decision,
            role=payload.role,
            comment=payload.comment,
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
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    return _decision(recommendation_id, "approved", payload, db)


@router.post("/recommendations/{recommendation_id}/reject", response_model=RecommendationResponse)
def reject(
    recommendation_id: int,
    payload: RecommendationDecisionRequest,
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    return _decision(recommendation_id, "rejected", payload, db)


@router.post(
    "/recommendations/{recommendation_id}/mark-implemented",
    response_model=RecommendationResponse,
)
def mark_implemented(
    recommendation_id: int,
    payload: RecommendationDecisionRequest,
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    return _decision(recommendation_id, "implemented", payload, db)
