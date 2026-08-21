from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.integrations.telegram.drafts import sign_callback


def record_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Customer message", callback_data="type:customer"),
                InlineKeyboardButton("Transaction note", callback_data="type:transaction"),
            ],
            [
                InlineKeyboardButton("Email", callback_data="type:email"),
                InlineKeyboardButton("Document text", callback_data="type:document"),
            ],
            [InlineKeyboardButton("Cancel", callback_data="cancel:selection")],
        ]
    )


def review_keyboard(nonce: str, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Confirm and ingest", callback_data=sign_callback("confirm", nonce, user_id)
                )
            ],
            [
                InlineKeyboardButton(
                    "Change type", callback_data=sign_callback("change", nonce, user_id)
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data=sign_callback("cancel", nonce, user_id)
                ),
            ],
        ]
    )


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Share my phone number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_reply_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
