from __future__ import annotations
import asyncio
import logging
import html
import mimetypes
import os
from datetime import datetime
from pyrogram import Client
from typing import Any, Optional

from pyrogram.enums import ParseMode, ChatType
from pyrogram.types import Message
from pyrogram.file_id import FileId
from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.category import detect_category
from FileStream.utils.file_cleanup import delete_file_entry, invalidate_runtime_access
from FileStream.utils.optional_channels import (
    disable_optional_channel,
    is_invalid_optional_channel_error,
    optional_channel_available,
)
from FileStream.config import Telegram, Server
from FileStream.server.exceptions import FileNotFound

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

_FLOG_MISSING_MARKERS = (
    "message_id_invalid",
    "msg_id_invalid",
    "message ids empty",
    "message not found",
    "chat not found",
)


def _flog_enabled() -> bool:
    return optional_channel_available("FLOG_CHANNEL", Telegram.FLOG_CHANNEL)


def _handle_invalid_flog(exc: Exception) -> bool:
    if not is_invalid_optional_channel_error(exc):
        return False
    disable_optional_channel("FLOG_CHANNEL", Telegram.FLOG_CHANNEL, exc)
    return True


async def get_file_ids(client: Client | bool, db_id: str, multi_clients, message=None) -> Optional[FileId]:
    logging.debug("Starting of get_file_ids")
    file_info = await db.get_file(db_id)
    if not file_info or not file_info.get("file_id"):
        raise FileNotFound
    if ("file_ids" not in file_info) or not client:
        if not _flog_enabled():
            if not client:
                return
            file_id_info = file_info.setdefault("file_ids", {})
            file_id_info[str(client.id)] = file_info.get("file_id", "")
            await db.update_file_ids(db_id, file_id_info)
        else:
            try:
                logging.debug("Storing file_id of all clients in DB")
                log_msg = await send_file(FileStream, db_id, file_info['file_id'], message, file_name=file_info.get('file_name'))
                await db.update_file_ids(db_id, await update_file_id(log_msg.id, multi_clients))
                logging.debug("Stored file_id of all clients in DB")
                if not client:
                    return
                file_info = await db.get_file(db_id)
            except Exception as exc:
                if not _handle_invalid_flog(exc):
                    raise
                if not client:
                    return
                file_id_info = file_info.setdefault("file_ids", {})
                file_id_info[str(client.id)] = file_info.get("file_id", "")
                await db.update_file_ids(db_id, file_id_info)

    file_id_info = file_info.setdefault("file_ids", {})
    if str(client.id) not in file_id_info:
        if not _flog_enabled():
            file_id_info[str(client.id)] = file_info.get("file_id", "")
            await db.update_file_ids(db_id, file_id_info)
        else:
            try:
                logging.debug("Storing file_id in DB")
                log_msg = await send_file(FileStream, db_id, file_info['file_id'], message, file_name=file_info.get('file_name'))
                msg = await client.get_messages(Telegram.FLOG_CHANNEL, log_msg.id)
                media = get_media_from_message(msg)
                file_id_info[str(client.id)] = getattr(media, "file_id", "")
                await db.update_file_ids(db_id, file_id_info)
                logging.debug("Stored file_id in DB")
            except Exception as exc:
                if not _handle_invalid_flog(exc):
                    raise
                file_id_info[str(client.id)] = file_info.get("file_id", "")
                await db.update_file_ids(db_id, file_id_info)

    logging.debug("Middle of get_file_ids")
    if not file_id_info.get(str(client.id)):
        # Try to refresh missing/empty file_id for this client
        if _flog_enabled():
            try:
                log_msg = await send_file(FileStream, db_id, file_info['file_id'], message, file_name=file_info.get('file_name'))
                msg = await client.get_messages(Telegram.FLOG_CHANNEL, log_msg.id)
                media = get_media_from_message(msg)
                file_id_info[str(client.id)] = getattr(media, "file_id", "")
                await db.update_file_ids(db_id, file_id_info)
            except Exception as exc:
                if not _handle_invalid_flog(exc):
                    raise
                file_id_info[str(client.id)] = file_info.get("file_id", "")
                await db.update_file_ids(db_id, file_id_info)
        else:
            file_id_info[str(client.id)] = file_info.get("file_id", "")
            await db.update_file_ids(db_id, file_id_info)

    if not file_id_info.get(str(client.id)):
        raise FileNotFound

    file_id = FileId.decode(file_id_info[str(client.id)])
    setattr(file_id, "file_size", file_info['file_size'])
    setattr(file_id, "mime_type", file_info['mime_type'])
    setattr(file_id, "file_name", file_info['file_name'])
    setattr(file_id, "unique_id", file_info['file_unique_id'])
    logging.debug("Ending of get_file_ids")
    return file_id


async def ensure_flog_media_exists(
    file_info: dict,
    bot: Client | None = None,
    prune_stale: bool = False,
    db_instance: Database | None = None,
) -> dict:
    if not file_info:
        raise FileNotFound

    if not _flog_enabled():
        return file_info

    flog_msg_id = file_info.get("flog_msg_id")
    if not flog_msg_id:
        return file_info

    client = bot or FileStream
    log_msg = None

    try:
        log_msg = await client.get_messages(Telegram.FLOG_CHANNEL, int(flog_msg_id))
    except Exception as exc:
        if _handle_invalid_flog(exc):
            return file_info
        error_text = str(exc or "").lower()
        if not any(marker in error_text for marker in _FLOG_MISSING_MARKERS):
            logging.warning("Unable to validate FLOG media for %s: %s", file_info.get("_id"), exc)
            return file_info

    media = get_media_from_message(log_msg)
    if media:
        return file_info

    file_db_id = str(file_info.get("_id") or "")
    invalidate_runtime_access(file_db_id)

    if prune_stale:
        cleanup_db = db_instance or db
        try:
            await delete_file_entry(cleanup_db, file_info, bot=client)
        except Exception:
            logging.debug("Failed to prune stale file %s after missing FLOG media", file_db_id, exc_info=True)

    raise FileNotFound("File no longer available")


def get_media_from_message(message: "Message") -> Any:
    if message is None:
        return None
    media_types = (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    )
    for attr in media_types:
        media = getattr(message, attr, None)
        if media:
            return media
    return None


def get_media_file_size(m):
    media = get_media_from_message(m)
    return getattr(media, "file_size", "None")


def get_name(media_msg: Message | FileId | None) -> str:
    file_name = ""

    if isinstance(media_msg, Message):
        media = get_media_from_message(media_msg)
        file_name = getattr(media, "file_name", "") if media else ""
    elif isinstance(media_msg, FileId):
        file_name = getattr(media_msg, "file_name", "")

    if not file_name:
        if isinstance(media_msg, Message) and getattr(media_msg, "media", None):
            media_type = media_msg.media.value
        elif hasattr(media_msg, "file_type") and media_msg.file_type:
            media_type = media_msg.file_type.name.lower()
        else:
            media_type = "file"

        formats = {
            "photo": "jpg", "audio": "mp3", "voice": "ogg",
            "video": "mp4", "animation": "mp4", "video_note": "mp4",
            "sticker": "webp"
        }

        ext = formats.get(media_type)
        ext = "." + ext if ext else ""

        date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"{media_type}-{date}{ext}"

    return file_name


def _guess_mime(file_name: str, mime_type: str | None = None) -> str:
    if mime_type:
        return mime_type
    if not file_name:
        return ""
    guess, _ = mimetypes.guess_type(file_name)
    return guess or ""


def _extract_uploader(message: Message) -> tuple[str, int | None, str | None]:
    if getattr(message, "from_user", None):
        first_name = (message.from_user.first_name or "").strip()
        last_name = (message.from_user.last_name or "").strip()
        full_name = " ".join(x for x in [first_name, last_name] if x) or "User"
        username = getattr(message.from_user, "username", None)
        return full_name, getattr(message.from_user, "id", None), username

    title = (getattr(message.chat, "title", None) or "Channel").strip()
    return title or "Channel", getattr(message.chat, "id", None), None


def get_file_info(message):
    if message is None or not getattr(message, "chat", None):
        return None

    if message.chat.type == ChatType.PRIVATE and not getattr(message, "from_user", None):
        return None

    media = get_media_from_message(message)
    if message.chat.type == ChatType.PRIVATE:
        user_idx = message.from_user.id
    else:
        user_idx = message.chat.id

    if not getattr(media, "file_id", None):
        # No valid media found
        return None

    file_name = get_name(message)
    file_ext = os.path.splitext(file_name)[1].lower() if file_name else ""
    mime_type = _guess_mime(file_name, getattr(media, "mime_type", ""))
    category = detect_category(file_name=file_name, mime_type=mime_type, file_ext=file_ext)

    uploader_name, uploader_id, uploader_username = _extract_uploader(message)

    msg_id = getattr(message, "id", None)
    try:
        msg_id = int(msg_id) if msg_id is not None else None
    except Exception:
        msg_id = None

    return {
        "user_id": user_idx,
        "file_id": getattr(media, "file_id", ""),
        "file_unique_id": getattr(media, "file_unique_id", ""),
        "file_name": file_name,
        "file_size": getattr(media, "file_size", 0),
        "mime_type": mime_type,
        "file_ext": file_ext,
        "category": category,
        "uploader": uploader_name,
        "uploader_id": uploader_id,
        "uploader_username": uploader_username,
        "message_id": msg_id,
        "chat_id": getattr(message.chat, "id", None),
    }


async def update_file_id(msg_id, multi_clients):
    file_ids = {}
    if not _flog_enabled():
        return file_ids
    
    async def get_id(client):
        try:
            log_msg = await client.get_messages(Telegram.FLOG_CHANNEL, msg_id)
            media = get_media_from_message(log_msg)
            return str(client.id), getattr(media, "file_id", "")
        except Exception as exc:
            if _handle_invalid_flog(exc):
                return str(client.id), ""
            return str(client.id), ""

    # Run concurrently for speed
    tasks = [get_id(client) for client in multi_clients.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            continue
        client_id, file_id = result
        file_ids[client_id] = file_id

    return file_ids


async def send_file(client: Client, db_id, file_id: str, message=None, file_name: str | None = None):
    if not _flog_enabled():
        raise FileNotFound

    if message:
        file_caption = getattr(message, 'caption', None) or get_name(message)
    else:
        file_caption = file_name or "file"

    if not isinstance(file_caption, str):
        file_caption = str(file_caption)
    file_caption = file_caption.replace("\n", " ").replace("\r", " ")
    if len(file_caption) > 1000:
        file_caption = file_caption[:1000] + "…"

    safe_caption = html.escape(file_caption)

    try:
        log_msg = await client.send_cached_media(
            chat_id=Telegram.FLOG_CHANNEL,
            file_id=file_id,
            caption=f"<b>{safe_caption}</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        if _handle_invalid_flog(exc):
            raise FileNotFound from exc
        raise
    try:
        await db.update_file_flog_msg(db_id, log_msg.id)
    except Exception:
        pass

    if message and message.chat:
        if message.chat.type == ChatType.PRIVATE and message.from_user:
            name = html.escape(message.from_user.first_name or "User")
            await log_msg.reply_text(
                text=(
                    f"<b>RᴇQᴜᴇꜱᴛᴇᴅ ʙʏ :</b> <a href='tg://user?id={message.from_user.id}'>{name}</a>\n"
                    f"<b>Uꜱᴇʀ ɪᴅ :</b> <code>{message.from_user.id}</code>\n"
                    f"<b>Fɪʟᴇ ɪᴅ :</b> <code>{db_id}</code>"
                ),
                disable_web_page_preview=True, parse_mode=ParseMode.HTML, quote=True)
        else:
            title = html.escape(message.chat.title or "Channel")
            await log_msg.reply_text(
                text=(
                    f"<b>RᴇQᴜᴇꜱᴛᴇᴅ ʙʏ :</b> {title}\n"
                    f"<b>Cʜᴀɴɴᴇʟ ɪᴅ :</b> <code>{message.chat.id}</code>\n"
                    f"<b>Fɪʟᴇ ɪᴅ :</b> <code>{db_id}</code>"
                ),
                disable_web_page_preview=True, parse_mode=ParseMode.HTML, quote=True)

    return log_msg
    # return await client.send_cached_media(Telegram.BIN_CHANNEL, file_id)
