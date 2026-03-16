from FileStream.utils.messages import LANG
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from FileStream.config import Telegram
from FileStream.utils.client_identity import build_add_to_group_link


_updates_username = str(Telegram.UPDATES_CHANNEL or "").lstrip("@").strip()
_updates_link = f"https://t.me/{_updates_username}" if _updates_username else "https://t.me"


class LANG(LANG):
    pass


class BUTTON(object):
    @staticmethod
    def start_buttons(bot=None):
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("ℹ️ About", callback_data="about"),
                    InlineKeyboardButton("❓ Help", callback_data="help"),
                ],
                [
                    InlineKeyboardButton("📢 Updates", url=_updates_link),
                ],
            ]
        )

    @staticmethod
    def help_buttons(bot=None):
        return InlineKeyboardMarkup(
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

    @staticmethod
    def about_buttons(bot=None):
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🏠 Home", callback_data="home"),
                    InlineKeyboardButton("❓ Help", callback_data="help"),
                ],
                [
                    InlineKeyboardButton("📢 Updates", url=_updates_link),
                    InlineKeyboardButton("❌ Close", callback_data="close"),
                ],
            ]
        )

    START_BUTTONS = start_buttons()
    HELP_BUTTONS = help_buttons()
    ABOUT_BUTTONS = about_buttons()
