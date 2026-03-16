from pyrogram import Client

from FileStream.bot import FileStream
from FileStream.config import Telegram


def get_bot_username(bot: Client | None = None) -> str:
    client = bot or FileStream
    username = getattr(client, "username", None) or getattr(FileStream, "username", None)
    return str(username or "").lstrip("@")


def get_bot_name(bot: Client | None = None) -> str:
    client = bot or FileStream
    return getattr(client, "fname", None) or getattr(FileStream, "fname", None) or "Bot"


def build_start_link(payload: str, bot: Client | None = None) -> str:
    username = get_bot_username(bot)
    return f"https://t.me/{username}?start={payload}" if username else "https://t.me"


def build_add_to_group_link(bot: Client | None = None) -> str:
    username = get_bot_username(bot)
    if username:
        return f"https://t.me/{username}?startgroup=true"

    token = str(getattr(Telegram, "BOT_TOKEN", "") or "")
    bot_id = token.split(":", 1)[0].strip()
    return f"https://t.me/{bot_id}?startgroup=true" if bot_id else "https://t.me"
