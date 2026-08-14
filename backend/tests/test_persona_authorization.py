from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.routes.audit_log import audit_log, workflow_audit
from app.routes.recommendations import approve, process_analysis, recommendations
from app.schemas import (
    ProcessAnalysisRequest,
    RecommendationDecisionRequest,
    UserRole,
)


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _expect_403(call) -> None:
    try:
        call()
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("Unauthorized demo persona was accepted")


def test_recommendation_visibility_matches_demo_personas():
    engine, db = _database()
    try:
        _expect_403(lambda: recommendations(UserRole.GENERAL_EMPLOYEE, db))
        assert recommendations(UserRole.FINANCE_OPS, db) == []
        assert recommendations(UserRole.COMPLIANCE, db) == []
        assert recommendations(UserRole.OWNER_DIRECTOR, db) == []
    finally:
        db.close()
        engine.dispose()


def test_only_owner_director_can_analyze_or_decide_recommendations():
    engine, db = _database()
    try:
        for role in (
            UserRole.GENERAL_EMPLOYEE,
            UserRole.FINANCE_OPS,
            UserRole.COMPLIANCE,
        ):
            _expect_403(
                lambda role=role: process_analysis(
                    ProcessAnalysisRequest(role=role), db
                )
            )
            _expect_403(
                lambda role=role: approve(
                    999,
                    RecommendationDecisionRequest(role=role),
                    db,
                )
            )
        try:
            approve(
                999,
                RecommendationDecisionRequest(role=UserRole.OWNER_DIRECTOR),
                db,
            )
        except HTTPException as error:
            assert error.status_code == 404
        else:
            raise AssertionError("Missing recommendation was not reported")
    finally:
        db.close()
        engine.dispose()


def test_only_compliance_can_view_both_audit_chains():
    engine, db = _database()
    try:
        for role in (
            UserRole.GENERAL_EMPLOYEE,
            UserRole.FINANCE_OPS,
            UserRole.OWNER_DIRECTOR,
        ):
            _expect_403(lambda role=role: audit_log(role, db))
            _expect_403(lambda role=role: workflow_audit(role, db))
        assert audit_log(UserRole.COMPLIANCE, db).chain_valid
        assert workflow_audit(UserRole.COMPLIANCE, db).chain_valid
    finally:
        db.close()
        engine.dispose()
