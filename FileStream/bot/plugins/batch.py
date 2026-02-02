import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode

from FileStream.bot import FileStream, multi_clients
from FileStream.utils.database import Database
from FileStream.utils.file_properties import get_file_info, get_file_ids
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.bot_utils import verify_user
from FileStream.config import Telegram, Server


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

# Manual folder sessions (old /batch)
folderm_sessions: dict[int, list[str]] = {}
MAX_FOLDERM_ITEMS = 100


def _folderm_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="folderm_done"), InlineKeyboardButton("❌ Cancel", callback_data="folderm_cancel")]
    ])


@FileStream.on_message(filters.command(["folderm", "folder", "batch"]) & filters.private)
async def start_folderm(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    user_id = message.from_user.id
    if user_id in folderm_sessions and folderm_sessions[user_id]:
        await message.reply_text(
            f"Folderm already active with **{len(folderm_sessions[user_id])}** files.\n"
            "Use the buttons below.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True,
            reply_markup=_folderm_buttons()
        )
        return

    folderm_sessions[user_id] = []
    await message.reply_text(
        "**Folderm mode started.**\n"
        "Forward video/audio/document files one by one.\n"
        "Use the buttons below when finished.",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
        reply_markup=_folderm_buttons()
    )


@FileStream.on_message(
    filters.private
    & filters.forwarded
    & (filters.video | filters.document | filters.audio),
    group=1,
)
async def handle_forwarded(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    user_id = message.from_user.id
    if user_id not in folderm_sessions:
        return

    if len(folderm_sessions[user_id]) >= MAX_FOLDERM_ITEMS:
        await message.reply_text(
            f"Folderm limit reached (**{MAX_FOLDERM_ITEMS}**).",
            parse_mode=ParseMode.MARKDOWN,
            quote=True,
            reply_markup=_folderm_buttons()
        )
        message.stop_propagation()
        return

    info = get_file_info(message)
    if not info:
        message.stop_propagation()
        return

    inserted_id = await db.add_file(info)
    try:
        await get_file_ids(False, inserted_id, multi_clients, message)
    except Exception:
        pass

    item_id = str(inserted_id)
    if item_id in folderm_sessions[user_id]:
        await message.reply_text(
            f"⚠️ Already added **{info.get('file_name', 'file')}**.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True,
            reply_markup=_folderm_buttons()
        )
        message.stop_propagation()
        return

    folderm_sessions[user_id].append(item_id)
    await message.reply_text(
        f"✅ Added **{info.get('file_name', 'file')}** "
        f"({humanbytes(info.get('file_size') or 0)})\n"
        f"Total: **{len(folderm_sessions[user_id])}**",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
        reply_markup=_folderm_buttons()
    )

    message.stop_propagation()


@FileStream.on_callback_query(filters.regex(r"^folderm_(done|cancel)$"))
async def folderm_callback(bot: Client, callback_query):
    action = callback_query.data.split("_", 1)[1]
    user_id = callback_query.from_user.id

    if user_id not in folderm_sessions:
        await callback_query.answer("No active folderm")
        return

    if action == "done":
        await finish_folderm(bot, callback_query.message, user_id=user_id)
    else:
        await cancel_folderm(bot, callback_query.message, user_id=user_id)
    await callback_query.answer()
    try:
        await callback_query.message.delete()
    except Exception:
        pass


@FileStream.on_message(filters.command("done") & filters.private)
async def finish_folderm(bot: Client, message: Message, user_id: int | None = None):
    if user_id is None:
        if not await verify_user(bot, message):
            return
        user_id = message.from_user.id

    file_list = folderm_sessions.get(user_id)
    if not file_list:
        folderm_sessions.pop(user_id, None)
        await message.reply_text(
            "No files in folderm. Use /folderm then forward files.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    folder_id = await db.create_folder(user_id, file_list)
    folderm_sessions.pop(user_id, None)

    link = f"{Server.URL}folderm/{folder_id}"
    await message.reply_text(
        f"✅ Folderm created!\n\n{link}",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        quote=True
    )


@FileStream.on_message(filters.command("cancel") & filters.private)
async def cancel_folderm(bot: Client, message: Message, user_id: int | None = None):
    if user_id is None:
        if not await verify_user(bot, message):
            return
        user_id = message.from_user.id

    if user_id in folderm_sessions:
        folderm_sessions.pop(user_id, None)
        await message.reply_text("Folderm discarded.", parse_mode=ParseMode.MARKDOWN, quote=True)
        return

    # If no active session, stay silent
    return
