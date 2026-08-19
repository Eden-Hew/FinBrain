from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.principal import AuthPrincipal
from app.db import get_db
from app.schemas import FinanceSummaryResponse, UserRole
from app.services.finance import revenue_summary

router = APIRouter(tags=["finance"])

_FINANCE_ROLES = (UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE)


@router.get("/finance/summary", response_model=FinanceSummaryResponse)
def finance_summary(
    period: Literal["month", "quarter", "year"] = Query(default="month"),
    offset: int = Query(default=0, le=0),
    principal: AuthPrincipal = Depends(require_roles(*_FINANCE_ROLES)),
    db: Session = Depends(get_db),
) -> FinanceSummaryResponse:
    return revenue_summary(db, str(principal.tenant_id), period=period, offset=offset)
