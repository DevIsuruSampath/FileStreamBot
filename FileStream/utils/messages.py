from FileStream.config import Telegram

class LANG(object):

    START_TEXT = """
<b>Hi {} 👋</b>

Send me any file and I’ll turn it into a clean share link in seconds.

<b>What you get 🚀</b>
• ⚡ Fast direct download
• 🔗 Clean public link
• 📁 Folder sharing

<b>How to use me 📌</b>
1️⃣ Send or forward a file
2️⃣ I create the link
3️⃣ Share it anywhere

Need help? Use <code>/help</code>

🤖 @{}
"""

    HELP_TEXT = """
<b>❓ Help</b>

Send or forward a file and I’ll create a public link for it.

<b>Commands 🧭</b>
• <code>/start</code> — Start
• <code>/about</code> — About
• <code>/legal</code> — Privacy and terms
• <code>/files</code> — Your files
• <code>/folders</code> — Your folders
• <code>/folder</code> — Start folder mode
• <code>/done</code> — Finish folder mode
• <code>/cancel</code> — Cancel folder mode
• <code>/donation</code> — Support the bot
• <code>/id</code> — Show your Telegram ID

<b>Tips ✨</b>
• Forward channel files directly to me
• Use the generated page for fast direct download
• Adult/NSFW content is not allowed

💬 <a href='tg://user?id={}'>Contact admin</a>
"""

    ABOUT_TEXT = """
<b>ℹ️ {}</b>

A Telegram bot for turning files into clean public links.

<b>What I offer 🚀</b>
• ⚡ Fast direct download
• 🔗 Clean share links
• 📁 Folder sharing
• 🤖 Open again in Telegram

<b>Version:</b> <code>{}</code>
"""

    STREAM_TEXT = """
<b>✅ Your share link is ready</b>

<b>📄 File:</b> <code>{}</code>
<b>💾 Size:</b> <code>{}</code>
<b>🏷️ Category:</b> <code>{}</code>
<b>🗂 Storage:</b> <code>{}</code>
<b>⏳ Time Left:</b> <code>{}</code>
<b>📅 Expires At:</b> <code>{}</code>
<b>🤖 Bot:</b> <code>@{}</code>

<b>🔗 Public Link:</b>
<code>{}</code>

<i>Open this page to watch, download fast, or open it again in @{}</i>
"""

    STREAM_TEXT_X = """
<b>✅ Your share link is ready</b>

<b>📄 File:</b> <code>{}</code>
<b>💾 Size:</b> <code>{}</code>
<b>🏷️ Category:</b> <code>{}</code>
<b>🗂 Storage:</b> <code>{}</code>
<b>⏳ Time Left:</b> <code>{}</code>
<b>📅 Expires At:</b> <code>{}</code>
<b>🤖 Bot:</b> <code>@{}</code>

<b>🔗 Public Link:</b>
<code>{}</code>

<i>Open this page for fast direct download or open it again in @{}</i>
"""

    BAN_TEXT = "<b>🚫️ Access Restricted</b>\n\n<i>Your account has been restricted from using this bot.</i>\n\n<b>❓ Think this is a mistake?</b>\n<a href='tg://user?id={}'>Contact Admin 💬</a>"
    FORCE_SUB_TEXT = """<b>🔐 Join our update channel to use this bot</b>

<i>Join the channel below, then tap <b>Try Again</b>.</i>

<b>Why this is required:</b>
• Get bot updates and notices 📢
• Keep access active ✅
• Receive important changes quickly ⚡️
"""
    FORCE_SUB_SUCCESS = """<b>✅ Join confirmed</b>

<i>You can use the bot now. Send your file or command again.</i>"""
    FORCE_SUB_STILL_REQUIRED = """<b>⚠️ Join required</b>

<i>Please join the update channel first, then tap <b>Try Again</b>.</i>"""
    FORCE_SUB_ERROR = """<b>😔 Couldn't verify your channel status</b>

<i>Please join the update channel and try again in a moment.</i>"""

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
