import asyncio
import time
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums.parse_mode import ParseMode

from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.file_properties import get_file_info
from FileStream.utils.human_readable import humanbytes
from FileStream.config import Telegram, Server


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

# In-memory batch sessions: {user_id: [file_db_ids...]}
batch_sessions: dict[int, list[str]] = {}


@FileStream.on_message(filters.command("batch") & filters.private)
async def start_batch(_: Client, message: Message):
    user_id = message.from_user.id
    batch_sessions[user_id] = []
    await message.reply_text(
        "**Batch mode started.**\n"
        "Forward video/document files one by one.\n"
        "Send /done when finished.",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )


@FileStream.on_message(
    filters.private
    & filters.forwarded
    & (filters.video | filters.document),
    group=1,
)
async def collect_batch_file(_: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in batch_sessions:
        return

    info = get_file_info(message)
    if not info:
        return

    inserted_id = await db.add_file(info)
    batch_sessions[user_id].append(str(inserted_id))

    await message.reply_text(
        f"✅ Added **{info.get('file_name', 'file')}** "
        f"({humanbytes(info.get('file_size') or 0)})\n"
        f"Total: **{len(batch_sessions[user_id])}**",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )

    message.stop_propagation()


@FileStream.on_message(filters.command("done") & filters.private)
async def finish_batch(_: Client, message: Message):
    user_id = message.from_user.id
    file_list = batch_sessions.get(user_id)

    if not file_list:
        await message.reply_text(
            "No files in batch. Use /batch then forward files.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    playlist_id = await db.create_playlist(user_id, file_list)
    batch_sessions.pop(user_id, None)

    link = f"{Server.URL}playlist/{playlist_id}"
    await message.reply_text(
        f"✅ Playlist created!\n\n{link}",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        quote=True
    )
