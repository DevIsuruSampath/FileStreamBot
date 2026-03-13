import asyncio

from pyrogram import filters, Client
from pyrogram.types import Message

from FileStream.bot import FileStream
from FileStream.utils.bot_utils import verify_user


DEFAULT_CLEAN_COUNT = 50
MAX_CLEAN_COUNT = 200


def _parse_clean_count(message: Message) -> int | None:
    if len(message.command) < 2:
        return DEFAULT_CLEAN_COUNT
    try:
        count = int(message.command[1])
    except Exception:
        return None
    if count < 1:
        return None
    return min(count, MAX_CLEAN_COUNT)


@FileStream.on_message(filters.command("clean") & filters.private)
async def clean_chat(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    count = _parse_clean_count(message)
    if count is None:
        await message.reply_text(
            "Usage: <code>/clean [count]</code>\n"
            f"Example: <code>/clean 40</code> (max {MAX_CLEAN_COUNT})",
            parse_mode="html",
            quote=True,
        )
        return

    start_id = max(1, message.id - count + 1)
    ids = list(range(start_id, message.id + 1))

    deleted = 0
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            result = await bot.delete_messages(chat_id=message.chat.id, message_ids=chunk)
            if isinstance(result, int):
                deleted += result
            elif isinstance(result, (list, tuple, set)):
                deleted += len(result)
            else:
                deleted += len(chunk)
        except Exception:
            # Best effort; continue deleting remaining chunks.
            continue

    try:
        status = await bot.send_message(
            chat_id=message.chat.id,
            text=f"🧹 Chat cleaned. Removed around {deleted} messages.",
        )
        await asyncio.sleep(3)
        await status.delete()
    except Exception:
        pass
