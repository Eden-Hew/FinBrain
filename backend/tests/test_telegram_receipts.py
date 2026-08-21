from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.integrations.telegram.receipts import claim_update, update_receipt
from app.models import Base, TelegramUpdateReceipt


def test_update_receipts_make_delivery_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert claim_update(
            db, update_id=123, actor_ref="actor", update_kind="message"
        )
        assert not claim_update(
            db, update_id=123, actor_ref="actor", update_kind="message"
        )
        update_receipt(
            db,
            123,
            status="protected",
            source_record_id="telegram:abc",
            customer_id=42,
            onboarding_session_id=7,
        )
        row = db.scalar(select(TelegramUpdateReceipt))
        assert row.status == "protected"
        assert row.source_record_id == "telegram:abc"
        assert row.customer_id == 42
        assert row.onboarding_session_id == 7
    engine.dispose()
