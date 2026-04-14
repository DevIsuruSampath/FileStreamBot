import asyncio
import re
import html
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode

from FileStream.bot import FileStream, multi_clients
from FileStream.utils.database import Database
from FileStream.utils.file_properties import get_file_info, get_file_ids
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.bot_utils import verify_user
from FileStream.utils.shortener import shorten
from FileStream.utils.file_cleanup import delete_file_entry
from FileStream.config import Telegram, Server


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

# Manual folder sessions (old /batch)
folderm_sessions: dict[int, dict] = {}
MAX_FOLDERM_ITEMS = 100
PROGRESS_REFRESH_EVERY = 5  # edit N times, then resend to keep it near bottom


def _clean_status_name(text: str, max_len: int = 90) -> str:
    text = str(text or "")
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "file"
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def _escape_html(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def _folderm_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="folder_done"), InlineKeyboardButton("❌ Cancel", callback_data="folder_cancel")]
    ])


def _folder_status_text(total: int, note: str | None = None) -> str:
    text = (
        "📦 <b>Folder mode active</b>\n"
        f"Total: <b>{int(total)}</b>\n"
        "Send only media files.\n"
        "Use /done to finish or /cancel to stop."
    )
    if note:
        text += f"\n\n{_escape_html(note)}"
    return text


def _render_added_list(names: list[str], limit: int = 5) -> str:
    if not names:
        return ""

    shown = names[-limit:]
    lines = "\n".join(f"• {_escape_html(name)}" for name in shown)
    extra = len(names) - len(shown)
    if extra > 0:
        lines += f"\n• +{extra} more..."

    return f"\n\n<b>Added list:</b>\n{lines}"


async def _try_delete_message(message: Message):
    try:
        await message.delete()
    except Exception:
        pass


def _get_session(user_id: int) -> dict | None:
    session = folderm_sessions.get(user_id)
    if not session:
        return None
    if not isinstance(session, dict):
        session = {
            "files": list(session),
            "new_files": [],
            "recent_names": [],
            "status_msg_id": None,
            "chat_id": None,
            "lock": asyncio.Lock(),
            "update_count": 0,
        }
        folderm_sessions[user_id] = session
    session.setdefault("files", [])
    session.setdefault("new_files", [])
    session.setdefault("recent_names", [])
    session.setdefault("update_count", 0)
    if "lock" not in session or session["lock"] is None:
        session["lock"] = asyncio.Lock()
    return session


async def _update_progress(bot: Client, message: Message, session: dict, text: str):
    chat_id = session.get("chat_id") or message.chat.id
    msg_id = session.get("status_msg_id")
    update_count = session.get("update_count", 0)

    # Try edit for a few updates to be "live", then resend to keep it near bottom
    if msg_id and update_count < PROGRESS_REFRESH_EVERY:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=_folderm_buttons(),
            )
            session["update_count"] = update_count + 1
            return
        except Exception:
            pass

    # Resend (and delete old) to keep it near bottom
    if msg_id:
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=msg_id)
        except Exception:
            pass

    msg = await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        quote=True,
        reply_markup=_folderm_buttons()
    )
    session["status_msg_id"] = msg.id
    session["chat_id"] = chat_id
    session["update_count"] = 0


@FileStream.on_message(filters.command(["folder"]) & filters.private)
async def start_folderm(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    user_id = message.from_user.id
    session = _get_session(user_id)
    if session:
        total = len(session.get("files") or [])
        await _update_progress(
            bot,
            message,
            session,
            _folder_status_text(total, "⚠️ Folder already active."),
        )
        await _try_delete_message(message)
        return

    folderm_sessions[user_id] = {
        "files": [],
        "new_files": [],
        "recent_names": [],
        "status_msg_id": None,
        "chat_id": message.chat.id,
        "lock": asyncio.Lock(),
        "update_count": 0,
    }
    msg = await message.reply_text(
        _folder_status_text(
            0,
            "✅ Send or forward video/audio/document/photo/voice/animation/video_note files now.",
        ),
        parse_mode=ParseMode.HTML,
        quote=True,
        reply_markup=_folderm_buttons()
    )
    folderm_sessions[user_id]["status_msg_id"] = msg.id
    await _try_delete_message(message)


@FileStream.on_message(filters.private & filters.text, group=-1)
async def folderm_guard_text(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    if not message.from_user:
        return

    user_id = message.from_user.id
    session = _get_session(user_id)
    if not session:
        return

    text = (message.text or "").strip()
    if not text:
        return

    cmd = ""
    if text.startswith("/"):
        cmd = text.split(None, 1)[0].split("@", 1)[0].lower()

    # Allow control commands to pass through
    if cmd in {"/done", "/cancel"}:
        return

    total = len(session.get("files") or [])
    await _update_progress(
        bot,
        message,
        session,
        _folder_status_text(total, "⚠️ Send media files only while folder mode is active."),
    )

    # Keep chat clean while folder mode is active
    try:
        await message.delete()
    except Exception:
        pass

    message.stop_propagation()


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
                f"⚠️ Folder limit reached (<b>{MAX_FOLDERM_ITEMS}</b>).",
            )
            await _try_delete_message(message)
            message.stop_propagation()
            return

        info = get_file_info(message)
        if not info:
            await _try_delete_message(message)
            message.stop_propagation()
            return

        file_unique_id = info.get("file_unique_id")
        existing = None
        if file_unique_id:
            try:
                existing = await db.get_file_by_fileuniqueid(user_id, file_unique_id)
            except Exception:
                existing = None

        if existing:
            inserted_id = existing["_id"]
            # Ensure cached ids only if missing
            if not existing.get("file_ids"):
                try:
                    await get_file_ids(False, inserted_id, multi_clients, message)
                except Exception:
                    pass
            is_new = False
        else:
            inserted_id = await db.add_file(info)
            try:
                await get_file_ids(False, inserted_id, multi_clients, message)
            except Exception:
                pass
            is_new = True

        item_id = str(inserted_id)
        status_name = _escape_html(_clean_status_name(info.get("file_name", "file")))

        if item_id in files:
            await _update_progress(
                bot,
                message,
                session,
                f"⚠️ Already added <b>{status_name}</b>.\nTotal: <b>{len(files)}</b>",
            )
            await _try_delete_message(message)
            message.stop_propagation()
            return

        files.append(item_id)
        session["files"] = files

        recent_names = session.get("recent_names") or []
        recent_names.append(_clean_status_name(info.get("file_name", "file"), max_len=70))
        session["recent_names"] = recent_names

        if is_new:
            session["new_files"].append(item_id)

        await _update_progress(
            bot,
            message,
            session,
            f"✅ Added <b>{status_name}</b> "
            f"({humanbytes(info.get('file_size') or 0)})\n"
            f"Total: <b>{len(files)}</b>"
            f"{_render_added_list(recent_names)}",
        )

        await _try_delete_message(message)
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

    total_files = len(file_list)
    folder_id = await db.create_folder(user_id, file_list)
    folderm_sessions.pop(user_id, None)

    link = f"{Server.URL}folder/{folder_id}"
    if await db.get_urlshortener_status():
        link = await shorten(link)
    await message.reply_text(
        f"✅ Folder created!\n"
        f"Total files: **{total_files}**\n\n"
        f"{link}",
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
        session = _get_session(user_id) or {}
        new_files = list(session.get("new_files") or [])
        # delete progress message if exists
        try:
            if session.get("chat_id") and session.get("status_msg_id"):
                await bot.delete_messages(chat_id=session["chat_id"], message_ids=session["status_msg_id"])
        except Exception:
            pass

        for fid in new_files:
            try:
                file_info = await db.get_file(fid)
            except Exception:
                continue
            try:
                await delete_file_entry(db, file_info, bot=bot)
            except Exception:
                pass

        folderm_sessions.pop(user_id, None)
        await message.reply_text("Folder cancelled.", parse_mode=ParseMode.MARKDOWN, quote=True)
        return

    # If no active session, stay silent
    return
