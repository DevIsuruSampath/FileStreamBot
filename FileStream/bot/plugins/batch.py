import asyncio
import re
import time
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
# Range folder sessions
folder_sessions: dict[int, dict] = {}

MAX_FOLDERM_ITEMS = 100
MAX_FOLDER_RANGE = 200


def parse_tg_link(link: str):
    # Accept: https://t.me/c/<id>/<msg_id>  OR https://t.me/<username>/<msg_id>
    m = re.match(r"(?:https?://)?t\.me/(c/)?([^/]+)/(?P<msg>\d+)", link)
    if not m:
        return None
    is_private = bool(m.group(1))
    chat = m.group(2)
    msg_id = int(m.group("msg"))

    if is_private:
        # t.me/c/<id>/<msg_id> where <id> is channel_id without -100
        chat_id = int("-100" + chat)
    else:
        chat_id = chat  # username

    return chat_id, msg_id


async def resolve_chat_id(bot: Client, chat_id):
    if isinstance(chat_id, int):
        return chat_id
    try:
        chat = await bot.get_chat(chat_id)
        return chat.id
    except Exception:
        return None


async def build_folder_from_range(bot: Client, message: Message, user_id: int, chat_id, start_id: int, end_id: int, mode: str = "folder"):
    start_id, end_id = (start_id, end_id) if start_id <= end_id else (end_id, start_id)
    total = end_id - start_id + 1

    if total > MAX_FOLDER_RANGE:
        await message.reply_text(
            f"Range too large (**{total}**). Max allowed: **{MAX_FOLDER_RANGE}**",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    status = await message.reply_text(
        f"Building folder from **{total}** messages...",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )

    files = []
    for chunk_start in range(start_id, end_id + 1, 50):
        ids = list(range(chunk_start, min(chunk_start + 50, end_id + 1)))
        msgs = await bot.get_messages(chat_id, ids)
        if not isinstance(msgs, list):
            msgs = [msgs]
        for msg in msgs:
            if not msg:
                continue
            info = get_file_info(msg)
            if not info:
                continue
            inserted_id = await db.add_file(info)
            try:
                await get_file_ids(False, inserted_id, multi_clients, msg)
            except Exception:
                pass
            files.append(str(inserted_id))

    if not files:
        await status.edit_text("No valid media found in that range.")
        return

    playlist_id = await db.create_playlist(user_id, files)
    link = f"{Server.URL}{mode}/{playlist_id}"
    await status.edit_text(f"✅ Folder created!\n\n{link}")


@FileStream.on_message(filters.command("folder") & filters.private)
async def start_folder(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    parts = message.text.split()
    user_id = message.from_user.id

    if len(parts) >= 3:
        start = parse_tg_link(parts[1])
        end = parse_tg_link(parts[2])
        if not start or not end:
            await message.reply_text("Invalid links. Use: /folder <start_link> <end_link>")
            return
        start_chat = await resolve_chat_id(bot, start[0])
        end_chat = await resolve_chat_id(bot, end[0])
        if not start_chat or not end_chat:
            await message.reply_text("Unable to resolve channel from link.")
            return
        if start_chat != end_chat:
            await message.reply_text("Start and end links must be from the same channel.")
            return

        await build_folder_from_range(bot, message, user_id, start_chat, start[1], end[1], mode="folder")
        return

    if len(parts) == 2:
        start = parse_tg_link(parts[1])
        if not start:
            await message.reply_text("Invalid link. Use: /folder <start_link> <end_link>")
            return
        start_chat = await resolve_chat_id(bot, start[0])
        if not start_chat:
            await message.reply_text("Unable to resolve channel from link.")
            return

        if user_id in folder_sessions and folder_sessions[user_id].get("start"):
            prev_chat, prev_id = folder_sessions[user_id]["start"]
            if prev_chat != start_chat:
                await message.reply_text("Start and end links must be from the same channel.")
                return
            folder_sessions.pop(user_id, None)
            await build_folder_from_range(bot, message, user_id, start_chat, prev_id, start[1], mode="folder")
            return

        folder_sessions[user_id] = {"start": (start_chat, start[1])}
        await message.reply_text(
            "Start saved. Now forward the END file or send /folder <end_link>.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    if user_id in folder_sessions and folder_sessions[user_id].get("start"):
        await message.reply_text(
            "Start already set. Now forward the END file or send /folder <end_link>.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    folder_sessions[user_id] = {"start": None}
    await message.reply_text(
        "**Folder mode started.**\n"
        "Forward the **START** file or send /folder <start_link>.\n"
        "Then forward the **END** file or send /folder <end_link>.\n"
        "Use /cancel to discard.",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )


@FileStream.on_message(filters.command(["folderm", "batch"]) & filters.private)
async def start_folderm(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    user_id = message.from_user.id
    if user_id in folderm_sessions and folderm_sessions[user_id]:
        await message.reply_text(
            f"Folderm already active with **{len(folderm_sessions[user_id])}** files.\n"
            "Use /done to finish or /cancel to discard.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    folderm_sessions[user_id] = []
    await message.reply_text(
        "**Folderm mode started.**\n"
        "Forward video/audio/document files one by one.\n"
        "Send /done when finished.\n"
        "Use /cancel to discard.",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done", callback_data="folderm_done"), InlineKeyboardButton("❌ Cancel", callback_data="folderm_cancel")]
        ])
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

    # Range folder flow
    if user_id in folder_sessions:
        start = folder_sessions[user_id].get("start")
        fchat = getattr(message, "forward_from_chat", None)
        fmsg_id = getattr(message, "forward_from_message_id", None)
        if not fchat or not fmsg_id:
            await message.reply_text("Please forward a message from a channel.")
            return

        if not start:
            folder_sessions[user_id]["start"] = (fchat.id, fmsg_id)
            await message.reply_text("Start saved. Now forward the END file or send /folder <end_link>.")
            return

        start_chat, start_id = start
        if start_chat != fchat.id:
            await message.reply_text("Start and end must be from the same channel.")
            return

        folder_sessions.pop(user_id, None)
        await build_folder_from_range(bot, message, user_id, fchat.id, start_id, fmsg_id, mode="folder")
        message.stop_propagation()
        return

    # Manual folderm flow
    if user_id not in folderm_sessions:
        return

    if len(folderm_sessions[user_id]) >= MAX_FOLDERM_ITEMS:
        await message.reply_text(
            f"Folderm limit reached (**{MAX_FOLDERM_ITEMS}**). Send /done to finish.",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    info = get_file_info(message)
    if not info:
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
            quote=True
        )
        return

    folderm_sessions[user_id].append(item_id)
    await message.reply_text(
        f"✅ Added **{info.get('file_name', 'file')}** "
        f"({humanbytes(info.get('file_size') or 0)})\n"
        f"Total: **{len(folderm_sessions[user_id])}**",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )

    message.stop_propagation()


@FileStream.on_callback_query(filters.regex(r"^folderm_(done|cancel)$"))
async def folderm_callback(_: Client, callback_query):
    action = callback_query.data.split("_", 1)[1]
    user_id = callback_query.from_user.id
    if action == "done":
        await finish_folderm(callback_query.message, user_id=user_id)
    else:
        await cancel_any(callback_query.message, user_id=user_id)
    await callback_query.answer()
    try:
        await callback_query.message.delete()
    except Exception:
        pass


@FileStream.on_message(filters.command("done") & filters.private)
async def finish_folderm(message: Message, user_id: int | None = None):
    if user_id is None:
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

    playlist_id = await db.create_playlist(user_id, file_list)
    folderm_sessions.pop(user_id, None)

    link = f"{Server.URL}folderm/{playlist_id}"
    await message.reply_text(
        f"✅ Folderm created!\n\n{link}",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        quote=True
    )


@FileStream.on_message(filters.command("cancel") & filters.private)
async def cancel_any(message: Message, user_id: int | None = None):
    if user_id is None:
        user_id = message.from_user.id

    if user_id in folderm_sessions:
        folderm_sessions.pop(user_id, None)
        await message.reply_text("Folderm discarded.", parse_mode=ParseMode.MARKDOWN, quote=True)
        return

    if user_id in folder_sessions:
        folder_sessions.pop(user_id, None)
        await message.reply_text("Folder range discarded.", parse_mode=ParseMode.MARKDOWN, quote=True)
        return

    # If no active session, stay silent
    return
