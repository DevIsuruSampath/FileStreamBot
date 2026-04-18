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
from FileStream.utils.flog_channels import (
    configured_flog_channels,
    optional_channel_name_for_id,
    resolve_file_flog_channel_id,
)
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
    for channel_id in configured_flog_channels().values():
        if optional_channel_available(optional_channel_name_for_id(channel_id), channel_id):
            return True
    return False


def _build_flog_query(user_id: int | None = None, channel_id: int | None = None) -> dict:
    base_query = {"flog_msg_id": {"$exists": True, "$nin": [None, ""]}}
    if user_id is not None:
        base_query["user_id"] = int(user_id)

    if channel_id is None:
        return base_query

    query = dict(base_query)
    main_channel_id = configured_flog_channels().get("main")
    if main_channel_id and int(channel_id) == int(main_channel_id):
        query["$or"] = [
            {"flog_channel_id": int(channel_id)},
            {"flog_channel_id": {"$exists": False}},
            {"flog_channel_id": None},
            {"flog_channel_id": ""},
        ]
        return query

    query["flog_channel_id"] = int(channel_id)
    return query


async def _fetch_flog_messages(client: Client, channel_id: int, message_ids: Iterable[int]):
    message_ids = [int(mid) for mid in message_ids if mid]
    if not message_ids:
        return {}
    channel_name = optional_channel_name_for_id(channel_id)

    async def _get_messages():
        return await client.get_messages(channel_id, message_ids)

    try:
        result = await _get_messages()
    except Exception as exc:
        if not is_invalid_optional_channel_error(exc):
            raise
        if not await warm_optional_channel_peer(client, channel_name, channel_id):
            disable_optional_channel(channel_name, channel_id, exc)
            return None
        try:
            result = await _get_messages()
        except Exception as retry_exc:
            if is_invalid_optional_channel_error(retry_exc):
                disable_optional_channel(channel_name, channel_id, retry_exc)
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


async def _reconcile_batch(client: Client, channel_id: int, batch: list[tuple[dict, int]], stats: dict) -> bool:
    messages = await _fetch_flog_messages(client, channel_id, [msg_id for _, msg_id in batch])
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


async def _purge_flog_records(client: Client, query: dict, stats: dict) -> None:
    projection = {"_id": 1, "user_id": 1, "flog_msg_id": 1, "flog_channel_id": 1}
    async for file_info in db.file.find(query, projection).sort("_id", -1):
        stats["checked_files"] += 1
        try:
            await delete_file_entry(db, file_info, bot=client)
            stats["deleted_files"] += 1
        except Exception:
            logging.debug("Failed deleting FLOG-backed file %s during storage purge", file_info.get("_id"), exc_info=True)


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

    if not configured_flog_channels():
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

        channel_ids: list[int] = []
        seen_channel_ids: set[int] = set()
        for channel_id in configured_flog_channels().values():
            normalized = int(channel_id)
            if normalized in seen_channel_ids:
                continue
            seen_channel_ids.add(normalized)
            channel_ids.append(normalized)

        try:
            distinct_channel_ids = await db.file.distinct("flog_channel_id", _build_flog_query(scoped_user_id))
        except Exception:
            distinct_channel_ids = []

        for raw_channel_id in distinct_channel_ids:
            try:
                normalized = int(raw_channel_id)
            except Exception:
                continue
            if normalized in seen_channel_ids:
                continue
            seen_channel_ids.add(normalized)
            channel_ids.append(normalized)

        for channel_id in channel_ids:
            channel_name = optional_channel_name_for_id(channel_id)
            channel_query = _build_flog_query(scoped_user_id, channel_id)

            if not optional_channel_available(channel_name, channel_id):
                stats["channel_unavailable"] = True
                await _purge_flog_records(client, channel_query, stats)
                logging.warning(
                    "FLOG storage %s=%s unavailable; purged records for %s",
                    channel_name,
                    channel_id,
                    f"user={scoped_user_id}" if scoped_user_id is not None else "global sync",
                )
                continue

            if not await warm_optional_channel_peer(client, channel_name, channel_id):
                stats["channel_unavailable"] = True
                disable_optional_channel(channel_name, channel_id, Exception("unable to warm optional channel peer"))
                await _purge_flog_records(client, channel_query, stats)
                logging.warning(
                    "FLOG storage %s=%s could not be warmed; purged records for %s",
                    channel_name,
                    channel_id,
                    f"user={scoped_user_id}" if scoped_user_id is not None else "global sync",
                )
                continue

            projection = {"_id": 1, "user_id": 1, "flog_msg_id": 1, "flog_channel_id": 1}
            cursor = db.file.find(channel_query, projection).sort("_id", -1)
            batch: list[tuple[dict, int]] = []

            async for file_info in cursor:
                try:
                    msg_id = int(file_info.get("flog_msg_id"))
                except Exception:
                    continue

                resolved_channel_id = resolve_file_flog_channel_id(file_info)
                if resolved_channel_id and int(resolved_channel_id) != int(channel_id):
                    continue

                batch.append((file_info, msg_id))
                if len(batch) >= FLOG_SYNC_BATCH_SIZE:
                    if not await _reconcile_batch(client, channel_id, batch, stats):
                        await _purge_flog_records(client, channel_query, stats)
                        break
                    batch = []

            if batch:
                if not await _reconcile_batch(client, channel_id, batch, stats):
                    await _purge_flog_records(client, channel_query, stats)

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
    if not configured_flog_channels():
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
