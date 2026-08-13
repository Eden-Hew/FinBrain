import asyncio
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.config import get_settings
from app.db import SessionLocal
from app.integrations.telegram.adapter import (
    RECORD_TYPES,
    canonical_record,
    short_reference,
)
from app.integrations.telegram.auth import actor_ref, operator_role
from app.integrations.telegram.drafts import draft_store, verify_callback
from app.integrations.telegram.extractors import ExtractionError, extract_document, extract_text
from app.integrations.telegram.keyboards import record_type_keyboard, review_keyboard
from app.integrations.telegram.receipts import claim_update, update_receipt
from app.integrations.telegram.service import enrich_in_background, protect
from app.integrations.telegram.types import CaptureDraft
from app.models import TokenizedContent
from app.security.detect import detect_spans, get_detector_status
from app.security.tokenize import tokenize_record

logger = logging.getLogger(__name__)
RESTRICTED = "This FinBrain bot is restricted to approved operators."
UNAVAILABLE = (
    "Protected capture is temporarily unavailable because the privacy detector is not ready."
)
PRIVACY = (
    "Telegram transports and may retain the original message. FinBrain does not persist raw "
    "content in its database; only protected text is sent to Morpheus and Gemini. Submit only "
    "information you are authorized to process."
)


def _identity(update: Update):
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None:
        return None, None, None
    return user, chat, operator_role(user.id, chat.type)


async def _require_authorized(update: Update) -> tuple[object, object, object] | None:
    user, chat, role = _identity(update)
    if user is None or chat is None or role is None:
        if update.effective_message:
            await update.effective_message.reply_text(RESTRICTED)
        return None
    return user, chat, role


def _claim(update: Update, user_id: int, kind: str) -> bool:
    with SessionLocal() as db:
        return claim_update(
            db,
            update_id=update.update_id,
            actor_ref=actor_ref(user_id),
            update_kind=kind,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    identity = await _require_authorized(update)
    if identity is None:
        return
    _, _, role = identity
    await update.effective_message.reply_text(
        f"FinBrain Capture is connected. Your fixed role is {role.value}.\n\n{PRIVACY}",
        reply_markup=record_type_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "/capture - capture a record\n/status - recent protected records\n/cancel - cancel "
        "the active capture\n/privacy - data handling\n/whoami - show your setup ID"
    )


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(PRIVACY)


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    await update.effective_message.reply_text(
        f"Your Telegram setup ID is {user.id}. Add this numeric ID to FinBrain's "
        "local operator map."
    )


async def capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    identity = await _require_authorized(update)
    if identity is None:
        return
    user, _, _ = identity
    if not get_detector_status().loaded:
        await update.effective_message.reply_text(UNAVAILABLE)
        return
    draft_store.pop(user.id)
    context.user_data.pop("record_type", None)
    await update.effective_message.reply_text(
        "What kind of record are you capturing?", reply_markup=record_type_keyboard()
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        draft_store.pop(user.id)
        context.user_data.pop("record_type", None)
    await update.effective_message.reply_text("Capture cancelled.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    identity = await _require_authorized(update)
    if identity is None:
        return
    with SessionLocal() as db:
        rows = db.scalars(
            select(TokenizedContent)
            .where(TokenizedContent.source_system == "telegram")
            .order_by(TokenizedContent.created_at.desc())
            .limit(get_settings().telegram_status_limit)
        ).all()
    if not rows:
        await update.effective_message.reply_text("No Telegram records have been captured yet.")
        return
    lines = ["Recent protected records:"]
    for row in rows:
        detail = row.record_type or "record"
        if row.structured_summary:
            detail += f" · {row.structured_summary.get('priority', 'unknown')} priority"
        lines.append(
            f"{short_reference(row.source_record_id)} · {detail} · {row.processing_status}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    identity = await _require_authorized(update)
    if identity is None:
        await query.answer()
        return
    user, _, _ = identity
    await query.answer()
    data = query.data or ""
    if data == "cancel:selection":
        draft_store.pop(user.id)
        context.user_data.pop("record_type", None)
        await query.edit_message_text("Capture cancelled.")
        return
    _, selection = data.split(":", 1)
    record_type = RECORD_TYPES.get(selection)
    if record_type is None:
        await query.edit_message_text("That record type is not supported.")
        return
    context.user_data["record_type"] = record_type
    await query.edit_message_text(
        "Send or forward the text now. You can also upload TXT, Markdown, CSV, EML, PDF, or DOCX."
    )


async def content_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    identity = await _require_authorized(update)
    if identity is None:
        return
    user, chat, _ = identity
    if not _claim(update, user.id, "message"):
        return
    record_type = context.user_data.get("record_type")
    if record_type is None:
        with SessionLocal() as db:
            update_receipt(db, update.update_id, status="ignored", failure_code="no_active_capture")
        await update.effective_message.reply_text("Use /capture first and select a record type.")
        return
    if not get_detector_status().loaded:
        await update.effective_message.reply_text(UNAVAILABLE)
        return
    message = update.effective_message
    forwarded = message.forward_origin is not None
    try:
        if message.document:
            file_size = message.document.file_size
            if file_size and file_size > get_settings().telegram_max_file_bytes:
                raise ExtractionError("file_too_large")
            telegram_file = await message.document.get_file()
            data = bytes(await telegram_file.download_as_bytearray())
            extracted = await asyncio.to_thread(
                extract_document,
                data,
                filename=message.document.file_name or "document",
                mime_type=message.document.mime_type or "application/octet-stream",
            )
            stable_ref = message.document.file_unique_id
        elif message.text:
            extracted = extract_text(message.text, forwarded=forwarded)
            stable_ref = "text"
        else:
            raise ExtractionError("unsupported_input")
        record = canonical_record(
            chat_id=chat.id,
            message_id=message.message_id,
            record_type=record_type,
            occurred_at=message.date,
            extracted=extracted,
            stable_content_ref=stable_ref,
            forwarded=forwarded,
            caption=message.caption,
        )
        protected_preview, _ = tokenize_record(
            record.text, detect_spans(record.text), record.source_record_id
        )
        nonce = draft_store.new_nonce()
        draft_store.put(
            CaptureDraft(
                nonce=nonce,
                telegram_user_id=user.id,
                telegram_chat_id=chat.id,
                telegram_message_id=message.message_id,
                telegram_update_id=update.update_id,
                record_type=record_type,
                canonical_record=record,
                protected_preview=protected_preview,
                source_kind=extracted.input_kind,
                created_at=datetime.now(UTC),
                expires_at_monotonic=time.monotonic() + get_settings().telegram_draft_ttl_seconds,
            )
        )
        with SessionLocal() as db:
            update_receipt(
                db,
                update.update_id,
                status="drafted",
                source_record_id=record.source_record_id,
            )
        preview = protected_preview[: get_settings().telegram_preview_chars]
        await message.reply_text(
            f"Ready to protect\n\nType: {record_type.replace('_', ' ')}\nInput: "
            f"{extracted.input_kind}\nCharacters: {len(record.text)}\n\n"
            f"Protected preview:\n{preview}\n\n"
            "The original text will not be stored by FinBrain.",
            reply_markup=review_keyboard(nonce, user.id),
        )
    except ExtractionError as error:
        with SessionLocal() as db:
            update_receipt(db, update.update_id, status="failed", failure_code=str(error))
        await message.reply_text(f"The content could not be accepted ({error}).")


async def review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    identity = await _require_authorized(update)
    if identity is None:
        await query.answer()
        return
    user, _, _ = identity
    parsed = verify_callback(query.data or "", user.id)
    if parsed is None:
        await query.answer("Invalid or expired action.", show_alert=True)
        return
    action, nonce = parsed
    if action == "change":
        draft_store.pop(user.id, nonce)
        context.user_data.pop("record_type", None)
        await query.answer()
        await query.edit_message_text(
            "Choose a new record type.", reply_markup=record_type_keyboard()
        )
        return
    draft = draft_store.pop(user.id, nonce)
    if draft is None:
        await query.answer("This draft expired. Please use /capture again.", show_alert=True)
        return
    if action == "cancel":
        context.user_data.pop("record_type", None)
        await query.answer()
        await query.edit_message_text("Capture cancelled.")
        return
    if action != "confirm":
        await query.answer("Unsupported action.", show_alert=True)
        return
    await query.answer()
    await query.edit_message_text("Protecting record…")
    try:
        result = await asyncio.to_thread(protect, draft.canonical_record)
    except Exception:
        logger.error("telegram_protect_failed", extra={"event_code": "protect_failed"})
        await query.edit_message_text(
            "FinBrain could not safely persist this record. Please try again."
        )
        return
    context.user_data.pop("record_type", None)
    reference = short_reference(result.source_record_id)
    with SessionLocal() as db:
        update_receipt(
            db,
            draft.telegram_update_id,
            status="protected",
            source_record_id=result.source_record_id,
        )
    await query.edit_message_text(
        f"Record protected\n\nReference: {reference}\nStatus: Enriching\n\n"
        "Only protected text has been stored and sent for AI enrichment."
    )
    if get_settings().telegram_delete_source_after_ingest:
        try:
            await context.bot.delete_message(
                chat_id=draft.telegram_chat_id,
                message_id=draft.telegram_message_id,
            )
        except Exception:
            logger.warning(
                "telegram_source_delete_failed",
                extra={"event_code": "source_delete_failed"},
            )

    async def notify(enriched) -> None:
        with SessionLocal() as db:
            update_receipt(
                db,
                draft.telegram_update_id,
                status="ready" if enriched.processing_status == "ready" else "failed",
                source_record_id=enriched.source_record_id,
                failure_code=(
                    None if enriched.processing_status == "ready" else "enrichment_failed"
                ),
            )
        if enriched.processing_status == "ready":
            await query.message.reply_text(
                f"Record ready\n\nReference: {reference}\nStatus: ready"
            )
        else:
            await query.message.reply_text(
                f"Record protected, enrichment pending\n\nReference: {reference}\n"
                "Your protected record is safe. FinBrain can retry enrichment later."
            )

    context.application.create_task(enrich_in_background(result.source_record_id, notify))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("telegram_handler_failed", extra={"event_code": "handler_failed"})
