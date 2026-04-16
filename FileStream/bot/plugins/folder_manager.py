import datetime
import html
from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.enums.parse_mode import ParseMode

from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.bot_utils import verify_user, get_public_folder_context, reply_with_optional_photo
from FileStream.utils.file_properties import ensure_flog_media_exists
from FileStream.config import Telegram, Server
from FileStream.server.exceptions import FileNotFound


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

PAGE_SIZE = 5
rename_pending: dict[int, dict] = {}


async def _edit_message(msg: Message, text: str, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    if getattr(msg, "photo", None) or getattr(msg, "caption", None):
        await msg.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        await msg.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)


def _fmt_title(folder):
    title = (folder.get("title") or "").strip()
    title = " ".join(title.split())
    if not title:
        title = f"Folder {folder.get('_id')}"
    if len(title) > 30:
        title = title[:30] + "…"
    return title


def _fmt_date(ts):
    if not ts:
        return "N/A"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return "N/A"


def _parse_page(value, default: int = 1) -> int:
    try:
        page = int(value)
        return page if page > 0 else default
    except Exception:
        return default


async def _sync_folder_files(folder: dict, bot: Client) -> dict | None:
    folder_id = str(folder.get("_id") or "")
    user_id = int(folder.get("user_id") or 0)
    original_files = [str(fid) for fid in (folder.get("files") or []) if fid]
    active_files = []
    changed = len(original_files) != len(folder.get("files") or [])

    for file_id in original_files:
        try:
            file_info = await db.get_file(file_id)
            await ensure_flog_media_exists(file_info, bot=bot, prune_stale=True, db_instance=db)
        except FileNotFound:
            changed = True
            continue
        active_files.append(str(file_info["_id"]))

    if not active_files:
        try:
            await db.delete_folder(folder_id, user_id)
        except Exception:
            pass
        return None

    if changed or active_files != original_files:
        await db.folders.update_one(
            {"_id": folder_id, "user_id": user_id},
            {"$set": {"files": active_files}},
        )
        folder["files"] = active_files

    return folder


async def _get_visible_folders(user_id: int, bot: Client) -> list[dict]:
    visible_folders = []
    cursor = db.folders.find({"user_id": int(user_id)}).sort("created_at", -1)

    async for folder in cursor:
        synced = await _sync_folder_files(folder, bot)
        if synced:
            visible_folders.append(synced)

    return visible_folders


async def _send_folder_list(bot: Client, message: Message, page: int = 1, edit: bool = False, user_id: int | None = None):
    if user_id is None:
        user_id = message.from_user.id
    if page < 1:
        page = 1

    visible_folders = await _get_visible_folders(user_id, bot)
    total = len(visible_folders)
    max_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    if page > max_pages:
        page = max_pages

    buttons = []
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    for f in visible_folders[start_idx:end_idx]:
        title = _fmt_title(f)
        buttons.append([
            InlineKeyboardButton(title, callback_data=f"fld:open:{f['_id']}:{page}")
        ])

    if total > PAGE_SIZE:
        buttons.append([
            InlineKeyboardButton("◄", callback_data=f"fld:list:{page-1}" if page > 1 else "fld:noop"),
            InlineKeyboardButton(f"{page}/{max_pages}", callback_data="fld:noop"),
            InlineKeyboardButton("►", callback_data=f"fld:list:{page+1}" if page < max_pages else "fld:noop"),
        ])

    if not buttons:
        buttons.append([InlineKeyboardButton("ᴇᴍᴘᴛʏ", callback_data="fld:noop")])

    buttons.append([InlineKeyboardButton("Close", callback_data="fld:close")])

    caption = f"Total folders: {total}"

    if edit:
        try:
            await _edit_message(message, caption, InlineKeyboardMarkup(buttons))
            return
        except Exception:
            pass

    await reply_with_optional_photo(
        message,
        Telegram.FOLDERS_PIC,
        caption,
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True,
    )


@FileStream.on_message(filters.command("folders") & filters.private)
async def folders_cmd(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return
    await _send_folder_list(bot, message, page=1, user_id=message.from_user.id)


@FileStream.on_callback_query(filters.regex(r"^fld:"))
async def folder_callbacks(bot: Client, cq: CallbackQuery):
    if not cq.from_user:
        return

    data = cq.data.split(":")
    if len(data) < 2:
        await cq.answer("Invalid")
        return

    action = data[1]
    user_id = cq.from_user.id

    # Simple auth guard for callbacks
    if Telegram.AUTH_USERS and user_id not in Telegram.AUTH_USERS and user_id != Telegram.OWNER_ID:
        await cq.answer("Unauthorized")
        return
    if await db.is_user_banned(user_id):
        await cq.answer("Banned")
        return

    if action == "noop":
        await cq.answer()
        return

    if action == "close":
        await cq.answer()
        try:
            await cq.message.delete()
        except Exception:
            pass
        return

    if action == "list":
        page = _parse_page(data[2], 1) if len(data) > 2 else 1
        await cq.answer()
        await _send_folder_list(bot, cq.message, page=page, edit=True, user_id=user_id)
        return

    if action == "open":
        if len(data) < 4:
            await cq.answer("Invalid")
            return
        folder_id = data[2]
        page = _parse_page(data[3], 1)
        try:
            folder = await db.get_folder_for_user(folder_id, user_id)
            folder = await _sync_folder_files(folder, bot)
        except Exception:
            await cq.answer("Folder not found")
            return
        if not folder:
            await cq.answer("Folder not found")
            await _send_folder_list(bot, cq.message, page=page, edit=True, user_id=user_id)
            return

        title = _fmt_title(folder)
        count = len(folder.get("files", []))
        created = _fmt_date(folder.get("created_at"))
        _, _, link = await get_public_folder_context(folder)

        safe_title = html.escape(title)

        buttons = [
            [InlineKeyboardButton("Open Folder", url=link)],
            [InlineKeyboardButton("Rename", callback_data=f"fld:ren:{folder_id}:{page}"),
             InlineKeyboardButton("Delete", callback_data=f"fld:del:{folder_id}:{page}")],
            [InlineKeyboardButton("Back", callback_data=f"fld:list:{page}")]
        ]
        await _edit_message(
            cq.message,
            f"<b>{safe_title}</b>\n"
            f"Files: <code>{count}</code>\n"
            f"Created: <code>{created}</code>\n"
            f"Share: <code>{html.escape(link)}</code>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML,
        )
        await cq.answer()
        return

    if action == "del":
        if len(data) < 4:
            await cq.answer("Invalid")
            return
        folder_id = data[2]
        page = _parse_page(data[3], 1)
        buttons = [
            [InlineKeyboardButton("Yes, delete", callback_data=f"fld:delyes:{folder_id}:{page}"),
             InlineKeyboardButton("Cancel", callback_data=f"fld:list:{page}")]
        ]
        await _edit_message(
            cq.message,
            "Confirm delete this folder?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await cq.answer()
        return

    if action == "delyes":
        if len(data) < 4:
            await cq.answer("Invalid")
            return
        folder_id = data[2]
        page = _parse_page(data[3], 1)
        try:
            await db.delete_folder(folder_id, user_id)
        except Exception:
            await cq.answer("Folder not found")
            return
        await cq.answer("Deleted")
        await _send_folder_list(bot, cq.message, page=page, edit=True, user_id=user_id)
        return

    if action == "ren":
        if len(data) < 4:
            await cq.answer("Invalid")
            return
        folder_id = data[2]
        page = _parse_page(data[3], 1)
        rename_pending[user_id] = {
            "folder_id": folder_id,
            "page": page,
            "chat_id": cq.message.chat.id,
            "message_id": cq.message.id,
        }
        await cq.answer()
        await cq.message.reply_text(
            "Send the new folder name (max 50 chars).",
            quote=True
        )
        return


@FileStream.on_message(filters.private & filters.text, group=3)
async def rename_folder_text(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    user_id = message.from_user.id
    if user_id not in rename_pending:
        return

    text = (message.text or "").strip()
    if text.lower().startswith("/cancel"):
        rename_pending.pop(user_id, None)
        await message.reply_text("Rename cancelled.", quote=True)
        return

    if text.startswith("/"):
        # Ignore other commands while waiting for a name
        return

    meta = rename_pending.get(user_id) or {}
    folder_id = meta.get("folder_id")
    page = meta.get("page", 1)
    chat_id = meta.get("chat_id")
    message_id = meta.get("message_id")

    title = text.strip()
    if not title:
        await message.reply_text("Name cannot be empty.", quote=True)
        return
    if len(title) > 50:
        await message.reply_text("Name too long (max 50 chars).", quote=True)
        return

    try:
        await db.update_folder_title(folder_id, user_id, title)
    except Exception:
        rename_pending.pop(user_id, None)
        await message.reply_text("Folder not found.", quote=True)
        return

    rename_pending.pop(user_id, None)
    await message.reply_text("✅ Renamed.", quote=True)

    # Refresh the folder details message if possible
    try:
        folder = await db.get_folder_for_user(folder_id, user_id)
        count = len(folder.get("files", []))
        created = _fmt_date(folder.get("created_at"))
        _, _, link = await get_public_folder_context(folder)
        safe_title = html.escape(_fmt_title(folder))
        buttons = [
            [InlineKeyboardButton("Open Folder", url=link)],
            [InlineKeyboardButton("Rename", callback_data=f"fld:ren:{folder_id}:{page}"),
             InlineKeyboardButton("Delete", callback_data=f"fld:del:{folder_id}:{page}")],
            [InlineKeyboardButton("Back", callback_data=f"fld:list:{page}")]
        ]
        if chat_id and message_id:
            target = await bot.get_messages(chat_id, message_id)
            await _edit_message(
                target,
                f"<b>{safe_title}</b>\n"
                f"Files: <code>{count}</code>\n"
                f"Created: <code>{created}</code>\n"
                f"Share: <code>{html.escape(link)}</code>",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        pass
