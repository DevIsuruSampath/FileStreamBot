from FileStream.config import Telegram

class LANG(object):

    START_TEXT = """
<b>Hey {}! 👋</b>

<i>I'm here to make sharing files effortless. ⚡️</i>

<b>✨ Just send me any file and I'll give you:</b>
• 🎬 A streaming link — watch instantly
• ⬇️ A download link — save anywhere
• 📁 A folder link — share multiple files at once

<b>💡 Pro tip:</b> Forward messages from channels directly to me!

<b>⚡️ It takes 3 seconds:</b>
1️⃣ Send a file
2️⃣ Tap the buttons I send back
3️⃣ Share your link anywhere

<b>🛡️ A quick note:</b>
Links stay active as long as the original file exists. Adult content isn't allowed here — let's keep it clean. ✨

<b>❓ Need help?</b> Tap the button below or type <code>/help</code>

<i>Made with ❤️ by</i> @{}
"""

    HELP_TEXT = """
<b>📚 How it works</b>

<i>Think of me as your personal file transformer — send anything, get shareable links instantly. ⚡️</i>

<b>🎯 For Users:</b>
• <code>/start</code> — Welcome screen 👋
• <code>/help</code> — You're here! 📖
• <code>/about</code> — About this bot ℹ️
• <code>/files</code> — Browse your uploads 📂
• <code>/folders</code> — Manage your folders 📁
• <code>/del</code> — Delete a file (reply to it) 🗑️
• <code>/status</code> — Bot status (Admin only) ⚡️

<b>🔥 Power Moves:</b>
• <code>/folder</code> — Create a folder link for multiple files
• Forward from channels — instant processing ⚡️

<b>🚫️ What's not allowed:</b>
Adult/NSFW content is strictly prohibited. Let's keep this space safe for everyone. ✨

<b>❓ Questions?</b>
<a href='tg://user?id={}'>Message the admin</a> — happy to help! 💬
"""

    ABOUT_TEXT = """
<b>🤖 Meet {}</b>

<i>Fast, reliable, and built for creators like you. ⚡️</i>

<b>📦 What I do:</b>
Transform Telegram files into streaming + download links — no waiting, no compression, no hassle.

<b>✨ Features:</b>
• Instant streaming (video & audio) 🎬
• Direct downloads ⬇️
• Folder sharing 📁
• Resume playback support ▶️
• NSFW protection & reporting 🛡️

<b>⚙️ Version:</b> <code>{}</code>

<i>Built with ❤️ for the Telegram community</i>
"""

    STREAM_TEXT = """
<b>✨ Your link is ready! 💯⚡️</b>

<b>📄 File:</b> <code>{}</code>
<b>💾 Size:</b> <code>{}</code>
<b>🏷️ Category:</b> <code>{}</code>

<b>🔗 Your Link:</b>
<b>▶️ Stream:</b> <code>{}</code>

<i>💡 Tip: Stream and download from the link above! ⭐️</i>
"""

    STREAM_TEXT_X = """
<b>✨ Your link is ready! 💯⚡️</b>

<b>📄 File:</b> <code>{}</code>
<b>💾 Size:</b> <code>{}</code>
<b>🏷️ Category:</b> <code>{}</code>

<b>⬇️ Download:</b> <code>{}</code>

<i>💡 Tip: Links work as long as the file exists. Save them! ⭐️</i>
"""

    BAN_TEXT = "<b>🚫️ Access Restricted</b>\n\n<i>Your account has been restricted from using this bot.</i>\n\n<b>❓ Think this is a mistake?</b>\n<a href='tg://user?id={}'>Contact Admin 💬</a>"

    # Folder Mode Messages
    FOLDER_START = """<b>📁 Folder Mode Activated ⚡️</b>

<i>I'm ready to collect your files!</i>

<b>How it works:</b>
1️⃣ Send me all the files you want in this folder
2️⃣ Type <code>/done</code> when you're finished ✅
3️⃣ Get a single link to share everything! 🔗

<b>Changed your mind?</b> Type <code>/cancel</code> to exit. ❌
"""
    FOLDER_ADDED = "<b>✅ Added to folder:</b>\n<code>{}</code>\n\n<i>Keep sending files, or type /done when finished! ⚡️</i>"
    FOLDER_DONE = """<b>🎉 Folder Created Successfully! ⭐️💯</b>

<b>📂 Folder:</b> {}
<b>🔗 Link:</b> {}

<i>Share this link and recipients can browse all files! ✨</i>
"""
    FOLDER_EMPTY = "<i>📭 This folder is empty.</i>\n\n<b>Start adding files with /folder! ⚡️</b>"
    FOLDER_CANCEL = "<b>❌ Folder mode cancelled.</b>\n\n<i>No worries — try again anytime with /folder! ✨</i>"
    FOLDER_NAME_PROMPT = "<b>📝 What would you like to name this folder?</b>\n\n<i>Send me the folder name! ⚡️</i>"

    # Error Messages
    ERROR_GENERIC = "<b>😅 Oops! Something went wrong.</b>\n\n<i>Please try again in a moment. ⚡️</i>"
    ERROR_FILE_NOT_FOUND = "<b>🔍 File Not Found</b>\n\n<i>This file may have been deleted or the link is invalid.</i>\n\n<b>Try uploading it again! ⬆️</b>"
    ERROR_INVALID_LINK = "<b>❌ Invalid Link</b>\n\n<i>This link doesn't look right. Double-check and try again. ❓</i>"
    ERROR_FLOOD = "<b>⏳ Please wait...</b>\n\n<i>Taking a short break for {} seconds to keep things smooth. ⚡️</i>"

    # Speedtest Messages
    SPEEDTEST_START = "🏃 <b>Running speed test... ⚡️</b>\n\n<i>This won't take long! 💨</i>"
    SPEEDTEST_ERROR = """<b>❌ Speed Test Failed</b>

<i>Couldn't complete the test right now. 😔</i>

<b>Possible reasons:</b>
• Network instability 📶
• Server is busy 🔧
• Temporary connection issue 🔌

<b>Please try again in a moment! ⚡️</b>
"""
    SPEEDTEST_RESULT = """<b>⚡️ Speed Test Results 💯</b>

<b>📊 YOUR SPEED</b>
├ <b>Download:</b> {download_mbps} Mbps ⬇️
├ <b>Upload:</b> {upload_mbps} Mbps ⬆️
├ <b>Ping:</b> {ping} ms 📶
└ <b>Tested at:</b> {timestamp} 🕐

<b>🌐 SERVER</b>
├ <b>Location:</b> {server_name}, {server_country} 📍
├ <b>Sponsor:</b> {server_sponsor} 🏢
├ <b>Latency:</b> {server_latency} ms ⚡️
└ <b>Coordinates:</b> {server_lat}, {server_lon} 🗺️

<b>📱 YOUR CONNECTION</b>
├ <b>IP:</b> {client_ip} 🔢
├ <b>ISP:</b> {client_isp} 🌐
├ <b>Rating:</b> {client_isprating} ⭐️
├ <b>Location:</b> {client_country} 🌍
└ <b>Coordinates:</b> {client_lat}, {client_lon} 📍

<b>Data transferred:</b> {bytes_sent} ⬆️ / {bytes_received} ⬇️
"""
