from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import get_db
from app.models import Base, IntegrationStatus
from app.routes.health import router
from app.services.health import heartbeat_rows, write_heartbeat


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
    return TestClient(app), db


def test_runtime_instance_defaults_to_local_and_uses_railway_service_id():
    assert Settings(_env_file=None).effective_service_instance_id == "local"
    railway = Settings(_env_file=None, railway_service_id="service-123")
    assert railway.effective_service_instance_id == "railway-service-123"
    explicit = Settings(_env_file=None, service_instance_id="Local Demo / Judge")
    assert explicit.effective_service_instance_id == "Local-Demo-Judge"


def test_status_page_lists_backend_and_disabled_workers(monkeypatch):
    from app.routes import health

    monkeypatch.setattr(
        health, "get_settings",
        lambda: _settings(telegram_bot_token=None, email_configured=False, vault=False),
    )
    client, _db = _client()
    try:
        response = client.get("/status")
        assert response.status_code == 200
        body = response.text
        assert "Backend API" in body
        assert "Telegram worker" in body
        assert "Email worker" in body
        assert "Vault rotation worker" in body
        assert "disabled" in body
    finally:
        _db.close()


def test_status_page_reports_uptime_for_running_worker(monkeypatch):
    from app.routes import health

    monkeypatch.setattr(
        health, "get_settings",
        lambda: _settings(telegram_bot_token="token", email_configured=False, vault=False),
    )
    client, db = _client()
    try:
        started = datetime.now(UTC) - timedelta(hours=1)
        db.add(IntegrationStatus(
            integration_key="local:telegram",
            status="healthy",
            mode="polling",
            detector_ready=True,
            started_at=started,
            last_heartbeat_at=datetime.now(UTC),
        ))
        db.commit()
        response = client.get("/status")
        assert response.status_code == 200
        assert "healthy" in response.text
        assert "1h 0m" in response.text
    finally:
        db.close()


def test_status_page_marks_stale_worker_offline(monkeypatch):
    from app.routes import health

    monkeypatch.setattr(
        health, "get_settings",
        lambda: _settings(telegram_bot_token="token", email_configured=False, vault=False),
    )
    client, db = _client()
    try:
        db.add(IntegrationStatus(
            integration_key="local:telegram",
            status="healthy",
            mode="polling",
            detector_ready=True,
            started_at=datetime.now(UTC) - timedelta(hours=2),
            last_heartbeat_at=datetime.now(UTC) - timedelta(minutes=10),
        ))
        db.commit()
        response = client.get("/status")
        assert response.status_code == 200
        assert "offline" in response.text
    finally:
        db.close()


def test_heartbeat_rows_are_isolated_by_runtime_instance():
    _client_instance, db = _client()
    try:
        now = datetime.now(UTC)
        write_heartbeat(
            db,
            key="telegram",
            instance_id="local",
            status="healthy",
            mode="polling",
            started_at=now,
            detector_ready=True,
            reset_started_at=True,
        )
        write_heartbeat(
            db,
            key="telegram",
            instance_id="railway-service-1",
            status="starting",
            mode="polling",
            started_at=now,
            reset_started_at=True,
        )

        assert heartbeat_rows(db, "local")["telegram"].status == "healthy"
        assert heartbeat_rows(db, "railway-service-1")["telegram"].status == "starting"
    finally:
        db.close()


def test_startup_heartbeat_replaces_previous_process_start_time():
    _client_instance, db = _client()
    try:
        previous = datetime.now(UTC) - timedelta(hours=2)
        current = datetime.now(UTC)
        write_heartbeat(
            db,
            key="telegram",
            instance_id="local",
            status="healthy",
            mode="polling",
            started_at=previous,
            reset_started_at=True,
        )
        write_heartbeat(
            db,
            key="telegram",
            instance_id="local",
            status="starting",
            mode="polling",
            started_at=current,
            reset_started_at=True,
        )
        row = heartbeat_rows(db, "local")["telegram"]
        started_at = row.started_at
        assert started_at is not None
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        assert abs((started_at - current).total_seconds()) < 1
    finally:
        db.close()


class _settings:
    def __init__(self, *, telegram_bot_token, email_configured, vault):
        self.telegram_bot_token = telegram_bot_token
        self.email_configured = email_configured
        self.vault_auto_rotation_enabled = vault
        self.telegram_heartbeat_seconds = 30
        self.email_sync_interval_seconds = 60
        self.vault_rotation_check_seconds = 60
        self.database_backend = "sqlite"
        self.effective_service_instance_id = "local"
