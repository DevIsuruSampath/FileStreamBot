from __future__ import annotations

import asyncio
import logging
import time
from typing import Iterable

from pyrogram import Client

from FileStream.bot import FileStream
from FileStream.config import Telegram
from FileStream.utils.database import Database
from FileStream.utils.file_cleanup import delete_file_entry
from FileStream.utils.file_properties import get_media_from_message
from FileStream.utils.optional_channels import (
    disable_optional_channel,
    is_invalid_optional_channel_error,
    optional_channel_available,
    warm_optional_channel_peer,
)


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

FLOG_SYNC_BATCH_SIZE = 100
FLOG_SYNC_INTERVAL = 300
FLOG_SYNC_MIN_USER_INTERVAL = 20

_sync_lock = asyncio.Lock()
_sync_task: asyncio.Task | None = None
_last_full_sync_at = 0.0
_last_user_sync_at: dict[int, float] = {}


def _has_flog_storage() -> bool:
    return bool(Telegram.FLOG_CHANNEL) and optional_channel_available("FLOG_CHANNEL", Telegram.FLOG_CHANNEL)


async def _fetch_flog_messages(client: Client, message_ids: Iterable[int]):
    message_ids = [int(mid) for mid in message_ids if mid]
    if not message_ids:
        return {}

    async def _get_messages():
        return await client.get_messages(Telegram.FLOG_CHANNEL, message_ids)

    try:
        result = await _get_messages()
    except Exception as exc:
        if not is_invalid_optional_channel_error(exc):
            raise
        if not await warm_optional_channel_peer(client, "FLOG_CHANNEL", Telegram.FLOG_CHANNEL):
            disable_optional_channel("FLOG_CHANNEL", Telegram.FLOG_CHANNEL, exc)
            return None
        try:
            result = await _get_messages()
        except Exception as retry_exc:
            if is_invalid_optional_channel_error(retry_exc):
                disable_optional_channel("FLOG_CHANNEL", Telegram.FLOG_CHANNEL, retry_exc)
                return None
            raise

    if not isinstance(result, list):
        result = [result] if result else []

    resolved = {}
    for message in result:
        if not message:
            continue
        try:
            resolved[int(message.id)] = message
        except Exception:
            continue
    return resolved


async def _prune_empty_folders(user_id: int | None = None) -> int:
    query = {"files": {"$size": 0}}
    if user_id is not None:
        query["user_id"] = int(user_id)

    deleted = 0
    async for folder in db.folders.find(query, {"_id": 1}):
        try:
            await db.delete_folder_by_id(folder["_id"])
            deleted += 1
        except Exception:
            logging.debug("Failed pruning empty folder %s", folder.get("_id"), exc_info=True)
    return deleted


async def _reconcile_batch(client: Client, batch: list[tuple[dict, int]], stats: dict) -> bool:
    messages = await _fetch_flog_messages(client, [msg_id for _, msg_id in batch])
    if messages is None:
        stats["channel_unavailable"] = True
        return False

    stats["checked_files"] += len(batch)

    for file_info, msg_id in batch:
        message = messages.get(msg_id)
        if message and get_media_from_message(message):
            continue
        try:
            await delete_file_entry(db, file_info, bot=client)
            stats["deleted_files"] += 1
        except Exception:
            logging.debug("Failed deleting stale FLOG-backed file %s", file_info.get("_id"), exc_info=True)

    return True


async def reconcile_flog_storage(
    bot: Client | None = None,
    *,
    user_id: int | None = None,
    force: bool = False,
) -> dict:
    global _last_full_sync_at

    stats = {
        "checked_files": 0,
        "deleted_files": 0,
        "deleted_folders": 0,
        "channel_unavailable": False,
    }

    if not Telegram.FLOG_CHANNEL:
        return stats

    now = time.time()
    scoped_user_id = int(user_id) if user_id is not None else None

    if not force:
        if scoped_user_id is None:
            if now - _last_full_sync_at < FLOG_SYNC_INTERVAL:
                return stats
        else:
            if now - _last_user_sync_at.get(scoped_user_id, 0.0) < FLOG_SYNC_MIN_USER_INTERVAL:
                return stats

    client = bot or FileStream

    async with _sync_lock:
        now = time.time()
        if not force:
            if scoped_user_id is None:
                if now - _last_full_sync_at < FLOG_SYNC_INTERVAL:
                    return stats
            else:
                if now - _last_user_sync_at.get(scoped_user_id, 0.0) < FLOG_SYNC_MIN_USER_INTERVAL:
                    return stats

        if not _has_flog_storage():
            return stats

        if not await warm_optional_channel_peer(client, "FLOG_CHANNEL", Telegram.FLOG_CHANNEL):
            stats["channel_unavailable"] = True
            return stats

        query = {"flog_msg_id": {"$exists": True, "$nin": [None, ""]}}
        if scoped_user_id is not None:
            query["user_id"] = scoped_user_id

        projection = {"_id": 1, "user_id": 1, "flog_msg_id": 1}
        cursor = db.file.find(query, projection).sort("_id", -1)

        batch: list[tuple[dict, int]] = []
        async for file_info in cursor:
            try:
                msg_id = int(file_info.get("flog_msg_id"))
            except Exception:
                continue
            batch.append((file_info, msg_id))
            if len(batch) >= FLOG_SYNC_BATCH_SIZE:
                if not await _reconcile_batch(client, batch, stats):
                    break
                batch = []

        if batch and not stats["channel_unavailable"]:
            await _reconcile_batch(client, batch, stats)

        stats["deleted_folders"] = await _prune_empty_folders(scoped_user_id)

        if scoped_user_id is None:
            _last_full_sync_at = time.time()
        else:
            _last_user_sync_at[scoped_user_id] = time.time()

    if stats["deleted_files"] or stats["deleted_folders"]:
        scope = f"user={scoped_user_id}" if scoped_user_id is not None else "global"
        logging.info(
            "FLOG sync repaired %s: checked=%s deleted_files=%s deleted_folders=%s",
            scope,
            stats["checked_files"],
            stats["deleted_files"],
            stats["deleted_folders"],
        )

    return stats


async def _sync_loop(bot: Client):
    while True:
        try:
            await reconcile_flog_storage(bot, force=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Background FLOG sync failed")
        await asyncio.sleep(FLOG_SYNC_INTERVAL)


def start_flog_sync_task(bot: Client | None = None) -> asyncio.Task | None:
    global _sync_task
    if not Telegram.FLOG_CHANNEL:
        return None
    if _sync_task and not _sync_task.done():
        return _sync_task
    _sync_task = asyncio.create_task(_sync_loop(bot or FileStream))
    return _sync_task


async def stop_flog_sync_task() -> None:
    global _sync_task
    if not _sync_task:
        return
    _sync_task.cancel()
    try:
        await _sync_task
    except asyncio.CancelledError:
        pass
    _sync_task = None
