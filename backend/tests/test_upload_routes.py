from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import Base
from app.routes.uploads import router
from app.schemas import ProtectedSummary, SummaryPriority, UserRole
from app.services import ingestion
from app.services.upload_ingestion import upload_digest
from tests.auth_support import principal

CSV = (
    b"invoice_id,customer,amount,status,assigned_owner,due_date\n"
    b"INV-1,customer@example.com,380,overdue,,2026-08-20\n"
)


def _client(monkeypatch, *, authenticated: bool = True) -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: principal(UserRole.FINANCE_OPS)
    monkeypatch.setattr(
        ingestion,
        "summarize_protected_text",
        lambda _text: (
            ProtectedSummary(
                summary="Protected upload accepted.",
                category="invoice",
                action_required=False,
                priority=SummaryPriority.LOW,
            ),
            "test",
        ),
    )
    monkeypatch.setattr(ingestion, "embed_text", lambda _text: ([1.0], "test"))
    return TestClient(app), db


def _headers(**updates) -> dict[str, str]:
    headers = {
        "Content-Type": "text/csv",
        "X-FinBrain-Filename": "invoices.csv",
        "X-FinBrain-Record-Type": "invoice_register",
    }
    headers.update(updates)
    return headers


def test_upload_preview_and_commit_routes(monkeypatch):
    client, db = _client(monkeypatch)
    try:
        preview = client.post("/uploads/preview", content=CSV, headers=_headers())
        assert preview.status_code == 200
        digest = preview.json()["preview_digest"]

        commit = client.post(
            "/uploads/commit",
            content=CSV,
            headers=_headers(**{"X-FinBrain-Preview-Digest": digest}),
        )
        assert commit.status_code == 200
        assert commit.json()["ready_rows"] == 1
    finally:
        client.close()
        db.close()


def test_upload_route_rejects_stale_digest_and_missing_authentication(monkeypatch):
    client, db = _client(monkeypatch)
    try:
        stale = client.post(
            "/uploads/commit",
            content=CSV,
            headers=_headers(**{"X-FinBrain-Preview-Digest": upload_digest(b"other")}),
        )
        assert stale.status_code == 409
        anonymous_client, anonymous_db = _client(monkeypatch, authenticated=False)
        try:
            response = anonymous_client.post("/uploads/preview", content=CSV, headers=_headers())
            assert response.status_code == 401
        finally:
            anonymous_client.close()
            anonymous_db.close()
    finally:
        client.close()
        db.close()
