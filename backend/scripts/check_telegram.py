import asyncio

from telegram import Bot

from app.config import get_settings


async def check() -> None:
    token = get_settings().telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    bot = Bot(token)
    identity = await bot.get_me()
    print(f"Telegram bot reachable: @{identity.username}")


if __name__ == "__main__":
    asyncio.run(check())
