import asyncio
import time
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
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
    if user_id in batch_sessions and batch_sessions[user_id]:
        await message.reply_text(
            f"Batch already active with **{len(batch_sessions[user_id])}** files.\n"
            "Use /done to finish or /cancel to discard.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    batch_sessions[user_id] = []
    await message.reply_text(
        "**Batch mode started.**\n"
        "Forward video/document files one by one.\n"
        "Send /done when finished.\n"
        "Use /cancel to discard.",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done", callback_data="batch_done"), InlineKeyboardButton("❌ Cancel", callback_data="batch_cancel")]
        ])
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
    item_id = str(inserted_id)
    if item_id in batch_sessions[user_id]:
        await message.reply_text(
            f"⚠️ Already added **{info.get('file_name', 'file')}**.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    batch_sessions[user_id].append(item_id)

    await message.reply_text(
        f"✅ Added **{info.get('file_name', 'file')}** "
        f"({humanbytes(info.get('file_size') or 0)})\n"
        f"Total: **{len(batch_sessions[user_id])}**",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )

    message.stop_propagation()


@FileStream.on_callback_query(filters.regex(r"^batch_(done|cancel)$"))
async def batch_callback(_: Client, callback_query):
    action = callback_query.data.split("_", 1)[1]
    user_id = callback_query.from_user.id
    if action == "done":
        await finish_batch(_, callback_query.message, user_id=user_id)
    else:
        await cancel_batch(_, callback_query.message, user_id=user_id)
    await callback_query.answer()
    try:
        await callback_query.message.delete()
    except Exception:
        pass


@FileStream.on_message(filters.command("done") & filters.private)
async def finish_batch(_: Client, message: Message, user_id: int | None = None):
    user_id = user_id or message.from_user.id
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


@FileStream.on_message(filters.command("cancel") & filters.private)
async def cancel_batch(_: Client, message: Message, user_id: int | None = None):
    user_id = user_id or message.from_user.id
    if user_id in batch_sessions:
        batch_sessions.pop(user_id, None)
        await message.reply_text(
            "Batch discarded.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    # If no active batch, stay silent
    return
