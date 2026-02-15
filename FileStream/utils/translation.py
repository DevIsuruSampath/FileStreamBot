from FileStream.utils.messages import LANG
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from FileStream.config import Telegram


_updates_username = str(Telegram.UPDATES_CHANNEL or "").lstrip("@").strip()
_updates_link = f"https://t.me/{_updates_username}" if _updates_username else "https://t.me"


class LANG(LANG):
    pass


class BUTTON(object):
    START_BUTTONS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add to Channel", url=f"https://t.me/{Telegram.BOT_TOKEN.split(':')[0]}?startgroup=true"),
            ],
            [
                InlineKeyboardButton("ℹ️ About", callback_data="about"),
                InlineKeyboardButton("🆘 Help", callback_data="help"),
            ],
            [
                InlineKeyboardButton("📢 Updates", url=_updates_link),
            ],
        ]
    )

    HELP_BUTTONS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏠 Home", callback_data="home"),
                InlineKeyboardButton("ℹ️ About", callback_data="about"),
            ],
            [
                InlineKeyboardButton("📢 Updates", url=_updates_link),
                InlineKeyboardButton("❌ Close", callback_data="close"),
            ],
        ]
    )

    ABOUT_BUTTONS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏠 Home", callback_data="home"),
                InlineKeyboardButton("🆘 Help", callback_data="help"),
            ],
            [
                InlineKeyboardButton("📢 Updates", url=_updates_link),
                InlineKeyboardButton("❌ Close", callback_data="close"),
            ],
        ]
    )
