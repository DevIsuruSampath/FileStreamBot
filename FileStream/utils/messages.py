from FileStream.config import Telegram

class LANG(object):

    START_TEXT = """
<b>👋 Welcome, {}</b>

<b>I am your smart file streaming assistant.</b>
<b>Send any media in private chat or channel and I will return instant links.</b>

<b>🚀 What I generate for you:</b>
• Stream link (watch online)
• Direct download link
• Folder link for multiple files (<code>/folder</code>)

<b>⚡ Quick Start:</b>
1) Send a file
2) Get stream + download buttons
3) Share or save your links

<b>⚠️ Important:</b>
• Links work until the source file is removed
• NSFW/adult content is not allowed
• Use <code>/help</code> for full commands

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
• <code>/folders</code> - Manage your folders
• <code>/del</code> - Delete a file (reply to file)
• <code>/status</code> - Bot status (Admin)

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
<b>✅ Your link generated.</b>

<b>📂 File:</b> <code>{}</code>
<b>💾 Size:</b> <code>{}</code>
<b>🗂️ Category:</b> <code>{}</code>
<b>📥 Download:</b> <code>{}</code>
<b>▶️ Watch:</b> <code>{}</code>

<b>ℹ️ Note:</b> Link works until file is removed.
"""

    STREAM_TEXT_X = """
<b>✅ Your link generated.</b>

<b>📂 File:</b> <code>{}</code>
<b>💾 Size:</b> <code>{}</code>
<b>🗂️ Category:</b> <code>{}</code>
<b>📥 Download:</b> <code>{}</code>

<b>ℹ️ Note:</b> Link works until file is removed.
"""

    BAN_TEXT = "__🚫 You are banned from using this bot.__\n\n**[🆘 Contact Admin](tg://user?id={})**"

    # Folder Mode Messages
    FOLDER_START = "<b>Folder Mode Started</b>\n\nSend me files to add to this folder.\nType <code>/done</code> when finished.\nType <code>/cancel</code> to stop."
    FOLDER_ADDED = "<b>Added to Folder:</b>\n<code>{}</code>"
    FOLDER_DONE = "<b>✅ Folder Created</b>\n\n<b>Title:</b> {}\n<b>Link:</b> {}"
    FOLDER_EMPTY = "Folder is empty."
    FOLDER_CANCEL = "Folder mode cancelled."
    FOLDER_NAME_PROMPT = "Send the name for this folder."

    # Error Messages
    ERROR_GENERIC = "An error occurred."
    ERROR_FILE_NOT_FOUND = "File not found."
    ERROR_INVALID_LINK = "Invalid link."
    ERROR_FLOOD = "FloodWait: Sleeping for {}s."

    # Speedtest Messages
    SPEEDTEST_START = "🚀 Running Speed Test..."
    SPEEDTEST_ERROR = (
        "❌ Speed Test Failed!\n"
        "> Unable to complete the speed test. Please try again later."
    )
    SPEEDTEST_RESULT = (
        "⚡ Speed Test Results\n\n"
        "SPEEDTEST INFO:\n"
        "> Download: {download_mbps} Mbps ({download_bps}/s)\n"
        "> Upload: {upload_mbps} Mbps ({upload_bps}/s)\n"
        "> Ping: {ping} ms\n"
        "> Timestamp: {timestamp}\n"
        "> Data Sent: {bytes_sent}\n"
        "> Data Received: {bytes_received}\n\n"
        "SERVER INFO:\n"
        "> Name: {server_name}\n"
        "> Country: {server_country}\n"
        "> Sponsor: {server_sponsor}\n"
        "> Latency: {server_latency} ms\n"
        "> Coordinates: {server_lat}, {server_lon}\n\n"
        "CLIENT DETAILS:\n"
        "> IP: {client_ip}\n"
        "> Coordinates: {client_lat}, {client_lon}\n"
        "> ISP: {client_isp}\n"
        "> ISP Rating: {client_isprating}\n"
        "> Country: {client_country}"
    )
