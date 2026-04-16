from FileStream.utils.messages import LANG
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


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
                    InlineKeyboardButton("⭐ Support", callback_data="support"),
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
                    InlineKeyboardButton("⭐ Support", callback_data="support"),
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
                    InlineKeyboardButton("⭐ Support", callback_data="support"),
                    InlineKeyboardButton("❌ Close", callback_data="close"),
                ],
            ]
        )

    START_BUTTONS = start_buttons()
    HELP_BUTTONS = help_buttons()
    ABOUT_BUTTONS = about_buttons()
