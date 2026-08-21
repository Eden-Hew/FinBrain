import asyncio
from types import SimpleNamespace

import pytest

from app.integrations.telegram import runner

TENANT = "00000000-0000-0000-0000-000000000001"


class StopLoop(Exception):
    pass


class SessionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *_args):
        return None


def test_outbound_loop_dispatches_without_running_reminder_planner(monkeypatch):
    settings = SimpleNamespace(
        telegram_customer_tenant_id=TENANT,
        telegram_outbound_batch_size=3,
        telegram_outbound_interval_seconds=5,
    )
    db = object()
    contexts = []
    dispatches = []
    sleeps = []

    monkeypatch.setattr(runner, "get_settings", lambda: settings)
    monkeypatch.setattr(runner, "SessionLocal", lambda: SessionContext(db))
    monkeypatch.setattr(
        runner,
        "set_worker_context",
        lambda current_db, **kwargs: contexts.append((current_db, kwargs)),
    )
    monkeypatch.setattr(
        runner,
        "plan_due_reminders",
        lambda *_args, **_kwargs: pytest.fail("outbound loop planned reminders"),
    )

    async def dispatch(current_db, bot):
        dispatches.append((current_db, bot))
        return SimpleNamespace(id="sent") if len(dispatches) == 1 else None

    async def sleep(seconds):
        sleeps.append(seconds)
        raise StopLoop

    monkeypatch.setattr(runner, "dispatch_one", dispatch)
    monkeypatch.setattr(runner.asyncio, "sleep", sleep)

    with pytest.raises(StopLoop):
        asyncio.run(runner._outbound_loop("bot"))

    assert contexts == [
        (
            db,
            {"actor_ref": "telegram-outbound-worker", "tenant_id": TENANT},
        )
    ]
    assert dispatches == [(db, "bot"), (db, "bot")]
    assert sleeps == [5]


def test_reminder_loop_plans_without_dispatching_messages(monkeypatch):
    settings = SimpleNamespace(
        telegram_customer_tenant_id=TENANT,
        telegram_reminder_interval_seconds=3600,
    )
    db = object()
    planned = []

    monkeypatch.setattr(runner, "get_settings", lambda: settings)
    monkeypatch.setattr(runner, "SessionLocal", lambda: SessionContext(db))
    monkeypatch.setattr(runner, "set_worker_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "plan_due_reminders",
        lambda current_db, tenant_id, today: planned.append((current_db, tenant_id, today)),
    )

    async def dispatch(*_args, **_kwargs):
        pytest.fail("reminder loop dispatched a message")

    async def sleep(seconds):
        assert seconds == 3600
        raise StopLoop

    monkeypatch.setattr(runner, "dispatch_one", dispatch)
    monkeypatch.setattr(runner.asyncio, "sleep", sleep)

    with pytest.raises(StopLoop):
        asyncio.run(runner._reminder_loop("bot"))

    assert len(planned) == 1
    assert planned[0][0] is db
    assert planned[0][1] == TENANT
