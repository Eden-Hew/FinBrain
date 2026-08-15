import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.models import Base
from app.routes.audit_log import audit_log, workflow_audit
from app.routes.recommendations import approve, recommendations
from app.schemas import RecommendationDecisionRequest, UserRole
from tests.auth_support import principal


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (UserRole.GENERAL_EMPLOYEE, False),
        (UserRole.FINANCE_OPS, True),
        (UserRole.COMPLIANCE, True),
        (UserRole.OWNER_DIRECTOR, True),
    ],
)
def test_recommendation_visibility_uses_verified_principal(role, allowed):
    dependency = require_roles(
        UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE
    )
    if allowed:
        assert dependency(principal(role)).role is role
    else:
        with pytest.raises(HTTPException) as error:
            dependency(principal(role))
        assert error.value.status_code == 403


def test_only_owner_director_can_decide_recommendations():
    dependency = require_roles(UserRole.OWNER_DIRECTOR)
    for role in (
        UserRole.GENERAL_EMPLOYEE,
        UserRole.FINANCE_OPS,
        UserRole.COMPLIANCE,
    ):
        with pytest.raises(HTTPException) as error:
            dependency(principal(role))
        assert error.value.status_code == 403

    engine, db = _database()
    try:
        with pytest.raises(HTTPException) as error:
            approve(
                999,
                RecommendationDecisionRequest(),
                principal(UserRole.OWNER_DIRECTOR),
                db,
            )
        assert error.value.status_code == 404
    finally:
        db.close()
        engine.dispose()


def test_only_compliance_can_view_both_audit_chains():
    dependency = require_roles(UserRole.COMPLIANCE)
    for role in (
        UserRole.GENERAL_EMPLOYEE,
        UserRole.FINANCE_OPS,
        UserRole.OWNER_DIRECTOR,
    ):
        with pytest.raises(HTTPException) as error:
            dependency(principal(role))
        assert error.value.status_code == 403

    engine, db = _database()
    try:
        compliance = principal(UserRole.COMPLIANCE)
        assert audit_log(compliance, db).chain_valid
        assert workflow_audit(compliance, db).chain_valid
        assert recommendations(compliance, db) == []
    finally:
        db.close()
        engine.dispose()
