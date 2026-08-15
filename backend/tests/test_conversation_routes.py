from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import Base
from app.routes.conversations import router
from tests.auth_support import principal


def _client() -> tuple[TestClient, Session]:
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
    app.dependency_overrides[get_current_user] = principal
    return TestClient(app), db


def test_conversation_create_get_and_delete_routes():
    client, db = _client()
    try:
        created = client.post("/conversations")
        assert created.status_code == 200
        conversation_id = created.json()["conversation_id"]

        loaded = client.get(f"/conversations/{conversation_id}")
        assert loaded.status_code == 200
        assert loaded.json()["turns"] == []

        deleted = client.delete(f"/conversations/{conversation_id}")
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "deleted"
        assert client.get(f"/conversations/{conversation_id}").status_code == 404
    finally:
        client.close()
        db.close()


def test_conversation_route_rejects_invalid_identifier():
    client, db = _client()
    try:
        assert client.get("/conversations/not-a-uuid").status_code == 404
        response = client.get(
            "/conversations/00000000-0000-0000-0000-000000000000",
        )
        assert response.status_code == 404
    finally:
        client.close()
        db.close()
