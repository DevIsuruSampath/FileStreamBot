import datetime
from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.enums.parse_mode import ParseMode

from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.bot_utils import verify_user
from FileStream.config import Telegram, Server


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

PAGE_SIZE = 5
rename_pending: dict[int, str] = {}


def _fmt_title(folder):
    title = (folder.get("title") or "").strip()
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


async def _send_folder_list(message: Message, page: int = 1):
    user_id = message.from_user.id
    if page < 1:
        page = 1

    total = await db.total_folders(user_id)
    if total == 0:
        await message.reply_text("No folders yet.", quote=True)
        return

    max_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if page > max_pages:
        page = max_pages

    start = (page - 1) * PAGE_SIZE + 1
    end = page * PAGE_SIZE
    folders, _ = await db.list_folders(user_id, [start, end])

    buttons = []
    async for f in folders:
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

    await message.reply_text(
        f"Your folders ({total}):",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )


@FileStream.on_message(filters.command("folders") & filters.private)
async def folders_cmd(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return
    await _send_folder_list(message, page=1)


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

    if action == "noop":
        await cq.answer()
        return

    if action == "list":
        page = int(data[2]) if len(data) > 2 else 1
        await cq.answer()
        await _send_folder_list(cq.message, page=page)
        return

    if action == "open":
        if len(data) < 4:
            await cq.answer("Invalid")
            return
        folder_id = data[2]
        page = int(data[3])
        try:
            folder = await db.get_folder_for_user(folder_id, user_id)
        except Exception:
            await cq.answer("Folder not found")
            return

        title = _fmt_title(folder)
        count = len(folder.get("files", []))
        created = _fmt_date(folder.get("created_at"))
        link = f"{Server.URL}folder/{folder_id}"

        buttons = [
            [InlineKeyboardButton("Open Folder", url=link)],
            [InlineKeyboardButton("Rename", callback_data=f"fld:ren:{folder_id}:{page}"),
             InlineKeyboardButton("Delete", callback_data=f"fld:del:{folder_id}:{page}")],
            [InlineKeyboardButton("Back", callback_data=f"fld:list:{page}")]
        ]
        await cq.message.edit_text(
            f"**{title}**\n"
            f"Files: `{count}`\n"
            f"Created: `{created}`\n"
            f"ID: `{folder_id}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        await cq.answer()
        return

    if action == "del":
        if len(data) < 4:
            await cq.answer("Invalid")
            return
        folder_id = data[2]
        page = int(data[3])
        buttons = [
            [InlineKeyboardButton("Yes, delete", callback_data=f"fld:delyes:{folder_id}:{page}"),
             InlineKeyboardButton("Cancel", callback_data=f"fld:list:{page}")]
        ]
        await cq.message.edit_text(
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
        page = int(data[3])
        try:
            await db.delete_folder(folder_id, user_id)
        except Exception:
            await cq.answer("Folder not found")
            return
        await cq.answer("Deleted")
        await _send_folder_list(cq.message, page=page)
        return

    if action == "ren":
        if len(data) < 4:
            await cq.answer("Invalid")
            return
        folder_id = data[2]
        rename_pending[user_id] = folder_id
        await cq.answer()
        await cq.message.reply_text(
            "Send the new folder name (max 50 chars).",
            quote=True
        )
        return


@FileStream.on_message(filters.private & filters.text & ~filters.command, group=3)
async def rename_folder_text(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    user_id = message.from_user.id
    if user_id not in rename_pending:
        return

    folder_id = rename_pending.pop(user_id)
    title = (message.text or "").strip()
    if not title:
        await message.reply_text("Name cannot be empty.", quote=True)
        return
    if len(title) > 50:
        title = title[:50]

    try:
        await db.update_folder_title(folder_id, user_id, title)
    except Exception:
        await message.reply_text("Folder not found.", quote=True)
        return

    await message.reply_text("✅ Renamed.", quote=True)
