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
                InlineKeyboardButton("📘 Help", callback_data="help"),
                InlineKeyboardButton("ℹ️ About", callback_data="about"),
            ],
            [InlineKeyboardButton("📁 My Files", callback_data="userfiles_1")],
            [
                InlineKeyboardButton("📢 Updates", url=_updates_link),
                InlineKeyboardButton("❌ Close", callback_data="close"),
            ],
        ]
    )

    HELP_BUTTONS = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏠 Home", callback_data="home"),
                InlineKeyboardButton("ℹ️ About", callback_data="about"),
            ],
            [InlineKeyboardButton("📁 My Files", callback_data="userfiles_1")],
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
                InlineKeyboardButton("📘 Help", callback_data="help"),
            ],
            [InlineKeyboardButton("📁 My Files", callback_data="userfiles_1")],
            [
                InlineKeyboardButton("📢 Updates", url=_updates_link),
                InlineKeyboardButton("❌ Close", callback_data="close"),
            ],
        ]
    )
