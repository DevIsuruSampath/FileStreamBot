from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from FileStream.config import Telegram


_updates_username = str(Telegram.UPDATES_CHANNEL or "").lstrip("@").strip()
_updates_link = f"https://t.me/{_updates_username}" if _updates_username else "https://t.me"


class LANG(object):

    START_TEXT = """
<b>👋 Hey, {}</b>

<b>I am a Telegram file streaming + direct link bot.</b>
<b>Send me any media file in private chat or channel.</b>

<b>⚡ I can generate:</b>
• Stream link
• Direct download link
• Folder link (batch mode)

<b>Bot:</b> @{}
"""

    HELP_TEXT = """
<b>How to use:</b>
1) Send me any media (video/audio/document/photo)
2) I store it and return stream + download links
3) Use <code>/folder</code> for batch folder links

<b>User Commands:</b>
• <code>/start</code> - Start bot
• <code>/help</code> - Show help
• <code>/about</code> - Bot info
• <code>/files</code> - Your uploaded files
• <code>/folder</code> - Start folder mode
• <code>/done</code> - Finish folder and get link
• <code>/cancel</code> - Cancel folder mode
• <code>/folders</code> - Manage your folders

<b>Safety:</b>
🔞 Adult content is strictly prohibited.

<b>Need support?</b>
<a href='tg://user?id={}'>Contact Admin</a>
"""

    ABOUT_TEXT = """
<b>🤖 Bot:</b> {}
<b>⚙️ Version:</b> {}
<b>📦 Purpose:</b> Stream + direct download links for Telegram files
<b>🛡️ Moderation:</b> NSFW reporting enabled
"""

    STREAM_TEXT = """
<b>📂 File:</b> <code>{}</code>
<b>💾 Size:</b> <code>{}</code>
<b>📥 Download:</b> <code>{}</code>
<b>▶️ Watch:</b> <code>{}</code>

<b>ℹ️ Note:</b> Link works until file is removed.
"""

    STREAM_TEXT_X = """
<b>📂 File:</b> <code>{}</code>
<b>💾 Size:</b> <code>{}</code>
<b>📥 Download:</b> <code>{}</code>

<b>ℹ️ Note:</b> Link works until file is removed.
"""

    BAN_TEXT = "__🚫 You are banned from using this bot.__\n\n**[🆘 Contact Admin](tg://user?id={})**"


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
