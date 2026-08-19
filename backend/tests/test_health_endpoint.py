from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app


class _BrokenSession:
    def execute(self, *_args, **_kwargs):
        raise RuntimeError("database unreachable")


def test_health_reports_ok_when_database_reachable():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db = Session(engine)
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database_reachable"] is True
    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)


def test_health_reports_degraded_when_database_unreachable():
    app.dependency_overrides[get_db] = lambda: _BrokenSession()
    try:
        response = TestClient(app).get("/health")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["database_reachable"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)
