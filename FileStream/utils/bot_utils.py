
import asyncio
import math
import html
import logging
import os
import time
import datetime
from typing import Union
from pyrogram.errors import UserNotParticipant, FloodWait
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from FileStream.utils.translation import LANG
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.category import detect_category
from FileStream.config import Telegram, Server
from FileStream.bot import FileStream
from FileStream.utils.public_links import build_public_file_url, build_public_folder_url, build_telegram_share_link
from FileStream.utils.flog_sync import reconcile_flog_storage
from FileStream.utils.client_identity import get_bot_username
from FileStream.utils.flog_channels import resolve_file_flog_mode

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
FILE_LIST_PAGE_SIZE = 10
_FORCE_SUB_PROMPTS: dict[int, dict[str, object]] = {}
FORCE_SUB_PROMPT_TTL = 600


def resolve_media_source(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    lowered = raw.lower()
    if lowered.startswith(("http://", "https://")):
        return raw

    candidates = []
    if os.path.isabs(raw):
        candidates.append(raw)
    else:
        candidates.append(os.path.join(PROJECT_ROOT, raw))
        candidates.append(os.path.join(PROJECT_ROOT, "images", raw))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    return raw


async def reply_with_optional_photo(
    message: Message,
    photo: str | None,
    text: str,
    *,
    reply_markup=None,
    parse_mode=None,
    disable_web_page_preview: bool = True,
    quote: bool | None = None,
):
    resolved_photo = resolve_media_source(photo)
    if resolved_photo:
        try:
            return await message.reply_photo(
                photo=resolved_photo,
                caption=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                quote=quote,
            )
        except Exception as exc:
            logging.warning("Failed to send configured photo %r: %s", photo, exc)

    return await message.reply_text(
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
        reply_markup=reply_markup,
        quote=quote,
    )


async def get_public_file_context(file_ref) -> tuple[dict, dict, str]:
    file_info = file_ref if isinstance(file_ref, dict) else await db.get_file(file_ref)
    link_doc = await db.ensure_public_link_for_file(file_info)
    return file_info, link_doc, build_public_file_url(link_doc["public_id"])


async def get_public_folder_context(folder_ref) -> tuple[dict, dict, str]:
    folder = folder_ref if isinstance(folder_ref, dict) else await db.get_folder(folder_ref)
    link_doc = await db.ensure_public_link_for_folder(folder)
    return folder, link_doc, build_public_folder_url(link_doc["public_id"])


def format_expiry_countdown(total_seconds: float | int) -> str:
    try:
        remaining = max(int(total_seconds), 0)
    except Exception:
        return "Unknown"

    if remaining <= 0:
        return "Expired"

    days, remainder = divmod(remaining, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts[:2]) + " left"


def describe_public_link_expiry(file_info: dict, link_doc: dict) -> dict[str, str | bool]:
    storage_mode = resolve_file_flog_mode(file_info)
    ttl_hours = int(Server.PUBLIC_FILE_EXPIRE_HOURS or 0)
    expires_at = link_doc.get("expires_at")

    if storage_mode == "admin" or expires_at is None:
        return {
            "storage_label": "ADMIN (Permanent)",
            "countdown_text": "Never expires",
            "absolute_text": "Permanent",
            "share_text": "♾ Permanent link",
            "is_permanent": True,
        }

    expires_at_value = float(expires_at)
    remaining = expires_at_value - time.time()
    absolute_text = datetime.datetime.utcfromtimestamp(expires_at_value).strftime("%Y-%m-%d %H:%M UTC")
    countdown_text = format_expiry_countdown(remaining)
    main_label = f"MAIN ({ttl_hours}h)" if ttl_hours > 0 else "MAIN"
    if remaining <= 0:
        share_text = "⏳ Link expired"
    else:
        share_text = f"⏳ Available for {format_expiry_countdown(remaining).replace(' left', '')}"

    return {
        "storage_label": main_label,
        "countdown_text": countdown_text,
        "absolute_text": absolute_text,
        "share_text": share_text,
        "is_permanent": False,
    }


def build_forward_share_text(file_name: str, bot_username: str | None, expiry_info: dict[str, str | bool]) -> str:
    normalized_bot = str(bot_username or "").strip().lstrip("@")
    lines = [
        "📥 Fast direct download link",
        f"📄 {file_name or 'file'}",
        str(expiry_info.get("share_text") or "⏳ Limited-time link"),
    ]
    if normalized_bot:
        lines.append(f"🤖 Open again in @{normalized_bot}")
    return "\n".join(lines)

async def get_invite_link(bot, chat_id: Union[str, int]):
    while True:
        try:
            invite_link = await bot.create_chat_invite_link(chat_id=chat_id)
            return invite_link
        except FloodWait as e:
            print(f"Sleep of {e.value}s caused by FloodWait ...")
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            print(f"Failed to create invite link: {e}")
            return None


def _resolve_force_sub_chat() -> Union[str, int, None]:
    if Telegram.FORCE_SUB_ID:
        fsid = str(Telegram.FORCE_SUB_ID).lstrip("@").strip()
        if fsid.startswith("-100") and fsid.lstrip("-").isdigit():
            return int(fsid)
        if fsid.lstrip("-").isdigit():
            return int(fsid)
        if fsid:
            return fsid

    channel = str(Telegram.UPDATES_CHANNEL or "").lstrip("@").strip()
    return channel or None


async def _build_force_sub_join_url(bot, channel_chat_id: Union[str, int, None]) -> str | None:
    if not channel_chat_id:
        return None

    invite_link = await get_invite_link(bot, chat_id=channel_chat_id)
    if invite_link and getattr(invite_link, "invite_link", None):
        return invite_link.invite_link

    if isinstance(channel_chat_id, str) and channel_chat_id and not channel_chat_id.lstrip("-").isdigit():
        return f"https://t.me/{channel_chat_id.lstrip('@')}"

    channel = str(Telegram.UPDATES_CHANNEL or "").lstrip("@").strip()
    if channel and not channel.lstrip("-").isdigit():
        return f"https://t.me/{channel}"

    return None


def _force_sub_markup(join_url: str | None):
    rows = []
    if join_url:
        rows.append([InlineKeyboardButton("🔔 Join Our Channel", url=join_url)])
    rows.append([
        InlineKeyboardButton("✅ Try Again", callback_data="forcesub_retry"),
        InlineKeyboardButton("❌ Close", callback_data="close"),
    ])
    return InlineKeyboardMarkup(rows)


def _get_force_sub_prompt(user_id: int) -> dict[str, object] | None:
    prompt = _FORCE_SUB_PROMPTS.get(int(user_id))
    if not prompt:
        return None
    if float(prompt.get("expires_at", 0)) <= time.time():
        _FORCE_SUB_PROMPTS.pop(int(user_id), None)
        return None
    return prompt


def _store_force_sub_prompt(user_id: int, sent_message: Message) -> None:
    _FORCE_SUB_PROMPTS[int(user_id)] = {
        "chat_id": int(sent_message.chat.id),
        "message_id": int(sent_message.id),
        "kind": "photo" if getattr(sent_message, "photo", None) else "text",
        "expires_at": time.time() + FORCE_SUB_PROMPT_TTL,
    }


def clear_force_sub_prompt(user_id: int) -> None:
    _FORCE_SUB_PROMPTS.pop(int(user_id), None)


async def _edit_force_sub_prompt(bot, prompt: dict[str, object], text: str, reply_markup) -> bool:
    try:
        chat_id = int(prompt["chat_id"])
        message_id = int(prompt["message_id"])
        if prompt.get("kind") == "photo":
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        else:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        prompt["expires_at"] = time.time() + FORCE_SUB_PROMPT_TTL
        return True
    except Exception:
        return False


async def _send_or_refresh_force_sub_prompt(bot, message: Message, text: str, reply_markup):
    user_id = int(message.from_user.id)
    prompt = _get_force_sub_prompt(user_id)
    if prompt and await _edit_force_sub_prompt(bot, prompt, text, reply_markup):
        return

    sent = await reply_with_optional_photo(
        message,
        Telegram.VERIFY_PIC,
        text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
    if sent:
        _store_force_sub_prompt(user_id, sent)


async def _check_force_sub_membership(bot, user_id: int) -> str:
    channel_chat_id = _resolve_force_sub_chat()
    if not channel_chat_id:
        return "joined"
    try:
        user = await bot.get_chat_member(chat_id=channel_chat_id, user_id=user_id)
        if str(getattr(user, "status", "")).upper() == "BANNED":
            return "banned"
        return "joined"
    except UserNotParticipant:
        return "missing"
    except Exception:
        return "error"

async def is_user_joined(bot, message: Message):
    if not getattr(message, "from_user", None):
        return False
    status = await _check_force_sub_membership(bot, message.from_user.id)
    if status == "joined":
        clear_force_sub_prompt(message.from_user.id)
        return True

    if status == "banned":
        await message.reply_text(
            text=LANG.BAN_TEXT.format(Telegram.OWNER_ID),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return False

    channel_chat_id = _resolve_force_sub_chat()
    join_url = await _build_force_sub_join_url(bot, channel_chat_id)
    reply_markup = _force_sub_markup(join_url)

    if status == "missing":
        await _send_or_refresh_force_sub_prompt(
            bot,
            message,
            LANG.FORCE_SUB_TEXT,
            reply_markup,
        )
        return False

    await _send_or_refresh_force_sub_prompt(
        bot,
        message,
        LANG.FORCE_SUB_ERROR,
        reply_markup,
    )
    return False


async def handle_force_sub_retry(bot, query) -> None:
    if not getattr(query, "from_user", None):
        await query.answer("Try again from your account.", show_alert=True)
        return

    status = await _check_force_sub_membership(bot, query.from_user.id)
    if status == "joined":
        clear_force_sub_prompt(query.from_user.id)
        success_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Close", callback_data="close")]]
        )
        try:
            if getattr(query.message, "photo", None) or getattr(query.message, "caption", None):
                await query.message.edit_caption(
                    caption=LANG.FORCE_SUB_SUCCESS,
                    parse_mode=ParseMode.HTML,
                    reply_markup=success_markup,
                )
            else:
                await query.message.edit_text(
                    text=LANG.FORCE_SUB_SUCCESS,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=success_markup,
                )
        except Exception:
            pass
        await query.answer("Join confirmed. Send your file or command again.", show_alert=True)
        return

    channel_chat_id = _resolve_force_sub_chat()
    join_url = await _build_force_sub_join_url(bot, channel_chat_id)
    retry_markup = _force_sub_markup(join_url)
    try:
        if getattr(query.message, "photo", None) or getattr(query.message, "caption", None):
            await query.message.edit_caption(
                caption=LANG.FORCE_SUB_STILL_REQUIRED,
                parse_mode=ParseMode.HTML,
                reply_markup=retry_markup,
            )
        else:
            await query.message.edit_text(
                text=LANG.FORCE_SUB_STILL_REQUIRED,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=retry_markup,
            )
    except Exception:
        pass
    await query.answer("Join the update channel first, then tap Try Again.", show_alert=True)

#---------------------[ PRIVATE GEN LINK + CALLBACK ]---------------------#

async def gen_link(_id, bot=None):
    file_info, link_doc, public_url = await get_public_file_context(_id)
    file_name = file_info.get('file_name') or "file"
    file_size = humanbytes(file_info.get('file_size') or 0)
    mime_type = (file_info.get('mime_type') or "").lower()
    ext = os.path.splitext(file_name)[1].lower()
    video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
    audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}
    is_streamable = ("video" in mime_type or "audio" in mime_type or ext in video_ext or ext in audio_ext)

    category = file_info.get("category") or detect_category(file_name=file_name, mime_type=mime_type, file_ext=ext)

    safe_name = html.escape(file_name)
    safe_category = html.escape(category)
    safe_public_url = html.escape(public_url)
    bot_username = get_bot_username(bot)
    safe_bot_username = html.escape(bot_username or "FileStreamBot")
    expiry_info = describe_public_link_expiry(file_info, link_doc)
    share_link = build_telegram_share_link(
        public_url,
        text=build_forward_share_text(file_name, bot_username, expiry_info),
    )
    if len(safe_name) > 200:
        safe_name = safe_name[:200] + "…"

    if is_streamable:
        stream_text = LANG.STREAM_TEXT.format(
            safe_name,
            file_size,
            safe_category,
            html.escape(str(expiry_info["storage_label"])),
            html.escape(str(expiry_info["countdown_text"])),
            html.escape(str(expiry_info["absolute_text"])),
            safe_bot_username,
            safe_public_url,
            safe_bot_username,
        )
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Open", url=public_url)],
                [InlineKeyboardButton("📤 Share Link", url=share_link), InlineKeyboardButton("Open in Bot", url=public_url)],
                [InlineKeyboardButton("🗑️ Revoke", callback_data=f"msgdelpvt_{_id}")],
                [InlineKeyboardButton("❌ Close", callback_data="close")]
            ]
        )
    else:
        stream_text = LANG.STREAM_TEXT_X.format(
            safe_name,
            file_size,
            safe_category,
            html.escape(str(expiry_info["storage_label"])),
            html.escape(str(expiry_info["countdown_text"])),
            html.escape(str(expiry_info["absolute_text"])),
            safe_bot_username,
            safe_public_url,
            safe_bot_username,
        )
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Open", url=public_url)],
                [InlineKeyboardButton("📤 Share Link", url=share_link), InlineKeyboardButton("Open in Bot", url=public_url)],
                [InlineKeyboardButton("🗑️ Revoke", callback_data=f"msgdelpvt_{_id}")],
                [InlineKeyboardButton("❌ Close", callback_data="close")]
            ]
        )
    return reply_markup, stream_text

#---------------------[ GEN STREAM LINKS FOR CHANNEL ]---------------------#

async def gen_linkx(m:Message , _id, bot=None):
    file_info, link_doc, public_url = await get_public_file_context(_id)
    file_name = file_info.get('file_name') or "file"
    mime_type = (file_info.get('mime_type') or "").lower()
    file_size = humanbytes(file_info.get('file_size') or 0)
    ext = os.path.splitext(file_name)[1].lower()
    video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
    audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}
    is_streamable = ("video" in mime_type or "audio" in mime_type or ext in video_ext or ext in audio_ext)

    category = file_info.get("category") or detect_category(file_name=file_name, mime_type=mime_type, file_ext=ext)

    safe_name = html.escape(file_name)
    safe_category = html.escape(category)
    safe_public_url = html.escape(public_url)
    bot_username = get_bot_username(bot)
    safe_bot_username = html.escape(bot_username or "FileStreamBot")
    expiry_info = describe_public_link_expiry(file_info, link_doc)
    if len(safe_name) > 200:
        safe_name = safe_name[:200] + "…"

    if is_streamable:
        stream_text = LANG.STREAM_TEXT.format(
            safe_name,
            file_size,
            safe_category,
            html.escape(str(expiry_info["storage_label"])),
            html.escape(str(expiry_info["countdown_text"])),
            html.escape(str(expiry_info["absolute_text"])),
            safe_bot_username,
            safe_public_url,
            safe_bot_username,
        )
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Open", url=public_url)]
            ]
        )
    else:
        stream_text = LANG.STREAM_TEXT_X.format(
            safe_name,
            file_size,
            safe_category,
            html.escape(str(expiry_info["storage_label"])),
            html.escape(str(expiry_info["countdown_text"])),
            html.escape(str(expiry_info["absolute_text"])),
            safe_bot_username,
            safe_public_url,
            safe_bot_username,
        )
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Open", url=public_url)]
            ]
        )
    return reply_markup, stream_text

#---------------------[ GEN FILE LIST BUTTON ]---------------------#

async def gen_file_list_button(file_list_no: int, user_id: int, bot=None):
    if file_list_no < 1:
        file_list_no = 1

    await reconcile_flog_storage(bot or FileStream, user_id=int(user_id))
    start_idx = (file_list_no - 1) * FILE_LIST_PAGE_SIZE + 1
    end_idx = start_idx + FILE_LIST_PAGE_SIZE - 1
    cursor, total_files = await db.find_files(int(user_id), (start_idx, end_idx))

    if total_files > 0:
        max_pages = math.ceil(total_files / FILE_LIST_PAGE_SIZE)
        if file_list_no > max_pages:
            file_list_no = max_pages
            start_idx = (file_list_no - 1) * FILE_LIST_PAGE_SIZE + 1
            end_idx = start_idx + FILE_LIST_PAGE_SIZE - 1
            cursor, total_files = await db.find_files(int(user_id), (start_idx, end_idx))
    else:
        max_pages = 1

    file_list = []
    async for x in cursor:
        name = x.get("file_name") or "file"
        # Prevent overly long button labels
        if len(name) > 50:
            name = name[:50] + "…"
        file_list.append([InlineKeyboardButton(name, callback_data=f"myfile_{x['_id']}_{file_list_no}")])
    if total_files > FILE_LIST_PAGE_SIZE:
        file_list.append(
                [InlineKeyboardButton("◄", callback_data="{}".format("userfiles_"+str(file_list_no-1) if file_list_no > 1 else 'N/A')),
                 InlineKeyboardButton(f"{file_list_no}/{max_pages}", callback_data="N/A"),
                 InlineKeyboardButton("►", callback_data="{}".format("userfiles_"+str(file_list_no+1) if total_files > file_list_no*FILE_LIST_PAGE_SIZE else 'N/A'))]
        )
    if not file_list:
        file_list.append(
                [InlineKeyboardButton("📭 Empty", callback_data="N/A")])
    file_list.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    return file_list, total_files

#---------------------[ USER BANNED ]---------------------#

async def is_user_banned(message):
    if not getattr(message, "from_user", None):
        return True
    if await db.is_user_banned(message.from_user.id):
        await message.reply_text(
            text=LANG.BAN_TEXT.format(Telegram.OWNER_ID),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return True
    return False

#---------------------[ CHANNEL BANNED ]---------------------#

async def is_channel_banned(bot, message):
    if await db.is_user_banned(message.chat.id):
        try:
            await bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=message.id,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🚫️ Channel Banned", callback_data="N/A")]])
            )
        except Exception:
            pass
        return True
    return False

#---------------------[ USER AUTH ]---------------------#

async def is_user_authorized(message):
    if not getattr(message, "from_user", None):
        return False

    if hasattr(Telegram, 'AUTH_USERS') and Telegram.AUTH_USERS:
        user_id = message.from_user.id

        if user_id == Telegram.OWNER_ID:
            return True

        if not (user_id in Telegram.AUTH_USERS):
            await message.reply_text(
                text="Yᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ ᴛᴏ ᴜsᴇ ᴛʜɪs ʙᴏᴛ.",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return False

    return True

#---------------------[ USER EXIST (FIXED) ]---------------------#

async def is_user_exist(bot, message):
    # Only Log if db.add_user returns TRUE (meaning it was a new insertion)
    if await db.add_user(message.from_user.id):
        if Telegram.ULOG_CHANNEL:
            try:
                await bot.send_message(
                    Telegram.ULOG_CHANNEL,
                    f"**#NᴇᴡUsᴇʀ**\n**⬩ ᴜsᴇʀ ɴᴀᴍᴇ :** [{message.from_user.first_name}](tg://user?id={message.from_user.id})\n**⬩ ᴜsᴇʀ ɪᴅ :** `{message.from_user.id}`"
                )
            except Exception:
                pass

async def is_channel_exist(bot, message):
    # Using the same logic for channels
    if await db.add_user(message.chat.id):
        if Telegram.ULOG_CHANNEL:
            members = "N/A"
            try:
                members = await bot.get_chat_members_count(message.chat.id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                pass
            try:
                await bot.send_message(
                    Telegram.ULOG_CHANNEL,
                    f"**#NᴇᴡCʜᴀɴɴᴇʟ** \n**⬩ ᴄʜᴀᴛ ɴᴀᴍᴇ :** `{message.chat.title}`\n**⬩ ᴄʜᴀᴛ ɪᴅ :** `{message.chat.id}`\n**⬩ ᴛᴏᴛᴀʟ ᴍᴇᴍʙᴇʀs :** `{members}`"
                )
            except Exception:
                pass

async def verify_user(bot, message):
    if not getattr(message, "from_user", None):
        return False

    if not await is_user_authorized(message):
        return False

    if await is_user_banned(message):
        return False

    await is_user_exist(bot, message)

    # Allow authorized users (and Owner) to bypass Force Sub
    user_id = message.from_user.id
    is_auth = (user_id == Telegram.OWNER_ID) or (user_id in Telegram.AUTH_USERS)

    if Telegram.FORCE_SUB and not is_auth:
        if not await is_user_joined(bot, message):
            return False

    return True
