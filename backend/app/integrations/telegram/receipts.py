from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import TelegramUpdateReceipt


def claim_update(
    db: Session,
    *,
    update_id: int,
    actor_ref: str,
    update_kind: str,
    message_ref_hash: str | None = None,
) -> bool:
    db.add(
        TelegramUpdateReceipt(
            update_id=update_id,
            actor_ref=actor_ref,
            update_kind=update_kind,
            message_ref_hash=message_ref_hash,
            status="received",
        )
    )
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def update_receipt(
    db: Session,
    update_id: int,
    *,
    status: str,
    source_record_id: str | None = None,
    failure_code: str | None = None,
) -> None:
    row = db.get(TelegramUpdateReceipt, update_id)
    if row is None:
        return
    row.status = status
    row.source_record_id = source_record_id or row.source_record_id
    row.failure_code = failure_code
    db.commit()
