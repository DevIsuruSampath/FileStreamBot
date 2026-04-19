from FileStream.utils.messages import LANG
from FileStream.utils.legal import build_policy_url
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
                    InlineKeyboardButton("⚖️ Legal", callback_data="legal"),
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
                    InlineKeyboardButton("⚖️ Legal", callback_data="legal"),
                ],
                [
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
                    InlineKeyboardButton("⚖️ Legal", callback_data="legal"),
                ],
                [
                    InlineKeyboardButton("❌ Close", callback_data="close"),
                ],
            ]
        )

    @staticmethod
    def legal_buttons(bot=None):
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔒 Privacy Policy", url=build_policy_url("privacy")),
                    InlineKeyboardButton("⚖️ Full Legal", url=build_policy_url("legal")),
                ],
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
    LEGAL_BUTTONS = legal_buttons()
