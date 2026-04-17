from __future__ import annotations

import logging

from pyrogram import Client

from FileStream.config import Telegram
from FileStream.utils.runtime_cache import invalidate_file_runtime


def invalidate_runtime_access(file_id: str) -> None:
    file_id = str(file_id or "")
    if not file_id:
        return

    invalidate_file_runtime(file_id)

    try:
        from FileStream.server.stream_routes import invalidate_file_access

        invalidate_file_access(file_id)
    except Exception:
        logging.debug("Runtime cache invalidation failed for %s", file_id, exc_info=True)


async def delete_file_entry(db, file_info: dict, bot: Client | None = None) -> None:
    file_id = str(file_info.get("_id") or "")
    invalidate_runtime_access(file_id)

    if bot and Telegram.FLOG_CHANNEL and file_info.get("flog_msg_id"):
        try:
            await bot.delete_messages(Telegram.FLOG_CHANNEL, int(file_info["flog_msg_id"]))
        except Exception:
            logging.debug("FLOG delete failed for %s", file_id, exc_info=True)

    try:
        await db.delete_one_file(file_info["_id"])
    finally:
        try:
            await db.remove_file_from_folders(file_id)
        except Exception:
            logging.debug("Folder cleanup failed for %s", file_id, exc_info=True)

        try:
            if file_info.get("user_id") is not None:
                await db.count_links(file_info.get("user_id"), "-")
        except Exception:
            logging.debug("Link count cleanup failed for %s", file_id, exc_info=True)

        invalidate_runtime_access(file_id)
