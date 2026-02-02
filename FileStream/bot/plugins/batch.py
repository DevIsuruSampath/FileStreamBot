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
folderm_sessions: dict[int, dict] = {}
MAX_FOLDERM_ITEMS = 100


def _folderm_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="folder_done"), InlineKeyboardButton("❌ Cancel", callback_data="folder_cancel")]
    ])


def _get_session(user_id: int) -> dict | None:
    session = folderm_sessions.get(user_id)
    if not session:
        return None
    if not isinstance(session, dict):
        session = {"files": list(session), "status_msg_id": None, "chat_id": None, "lock": asyncio.Lock()}
        folderm_sessions[user_id] = session
    session.setdefault("files", [])
    if "lock" not in session or session["lock"] is None:
        session["lock"] = asyncio.Lock()
    return session


async def _update_progress(bot: Client, message: Message, session: dict, text: str):
    chat_id = session.get("chat_id") or message.chat.id
    msg_id = session.get("status_msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_folderm_buttons(),
            )
            return
        except Exception:
            pass
    # fallback: send a new message and track it
    msg = await message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
        reply_markup=_folderm_buttons()
    )
    session["status_msg_id"] = msg.id
    session["chat_id"] = chat_id


@FileStream.on_message(filters.command(["folder"]) & filters.private)
async def start_folderm(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    user_id = message.from_user.id
    session = _get_session(user_id)
    if session:
        total = len(session.get("files") or [])
        msg = await message.reply_text(
            f"Folder already active with **{total}** files.\n"
            "Use the buttons below.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True,
            reply_markup=_folderm_buttons()
        )
        session["status_msg_id"] = msg.id
        session["chat_id"] = message.chat.id
        return

    folderm_sessions[user_id] = {"files": [], "status_msg_id": None, "chat_id": message.chat.id, "lock": asyncio.Lock()}
    msg = await message.reply_text(
        "**Folder mode started.**\n"
        "Send or forward video/audio/document/photo/voice/animation/video_note files one by one.\n"
        "Use the buttons below when finished.",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
        reply_markup=_folderm_buttons()
    )
    folderm_sessions[user_id]["status_msg_id"] = msg.id


@FileStream.on_message(
    filters.private
    & (filters.video | filters.document | filters.audio | filters.photo | filters.animation | filters.voice | filters.video_note),
    group=1,
)
async def handle_forwarded(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    user_id = message.from_user.id
    session = _get_session(user_id)
    if not session:
        return

    async with session["lock"]:
        files = session.get("files") or []

        if len(files) >= MAX_FOLDERM_ITEMS:
            await _update_progress(
                bot,
                message,
                session,
                f"Folder limit reached (**{MAX_FOLDERM_ITEMS}**).",
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
        if item_id in files:
            await _update_progress(
                bot,
                message,
                session,
                f"⚠️ Already added **{info.get('file_name', 'file')}**.\nTotal: **{len(files)}**",
            )
            message.stop_propagation()
            return

        files.append(item_id)
        session["files"] = files
        await _update_progress(
            bot,
            message,
            session,
            f"✅ Added **{info.get('file_name', 'file')}** "
            f"({humanbytes(info.get('file_size') or 0)})\n"
            f"Total: **{len(files)}**",
        )

        message.stop_propagation()


@FileStream.on_callback_query(filters.regex(r"^folder(m)?_(done|cancel)$"))
async def folderm_callback(bot: Client, callback_query):
    action = callback_query.data.split("_", 1)[1]
    user_id = callback_query.from_user.id

    if user_id not in folderm_sessions:
        await callback_query.answer("No active folder")
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

    session = _get_session(user_id)
    file_list = (session or {}).get("files")
    if not file_list:
        folderm_sessions.pop(user_id, None)
        await message.reply_text(
            "No files in folder. Use /folder then forward files.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    folder_id = await db.create_folder(user_id, file_list)
    folderm_sessions.pop(user_id, None)

    link = f"{Server.URL}folder/{folder_id}"
    await message.reply_text(
        f"✅ Folder created!\n\n{link}",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        quote=True,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Folder", url=link)]])
    )


@FileStream.on_message(filters.command("cancel") & filters.private)
async def cancel_folderm(bot: Client, message: Message, user_id: int | None = None):
    if user_id is None:
        if not await verify_user(bot, message):
            return
        user_id = message.from_user.id

    if user_id in folderm_sessions:
        folderm_sessions.pop(user_id, None)
        await message.reply_text("Folder cancelled.", parse_mode=ParseMode.MARKDOWN, quote=True)
        return

    # If no active session, stay silent
    return
