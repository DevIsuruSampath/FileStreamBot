import asyncio

from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums.parse_mode import ParseMode

from FileStream.bot import FileStream
from FileStream.utils.bot_utils import verify_user


CLEAN_SCAN_LIMIT = 8000


def _clean_buttons(user_id: int, source_message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Yes, clean chat", callback_data=f"clean:yes:{user_id}:{source_message_id}")],
            [InlineKeyboardButton("❌ No", callback_data=f"clean:no:{user_id}:{source_message_id}")],
        ]
    )


def _count_deleted(result, fallback_len: int) -> int:
    if isinstance(result, int):
        return result
    if isinstance(result, bool):
        return fallback_len if result else 0
    if isinstance(result, (list, tuple, set)):
        return sum(1 for x in result if x)
    return fallback_len


def _candidate_ids(top_message_id: int, span: int = CLEAN_SCAN_LIMIT) -> list[int]:
    top = max(int(top_message_id), 1)
    bottom = max(1, top - int(span) + 1)
    return list(range(top, bottom - 1, -1))


@FileStream.on_message(filters.command("clean") & filters.private)
async def clean_chat_prompt(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    note = ""
    if len(message.command) > 1:
        note = "\n\nℹ️ Number argument is no longer needed."

    await message.reply_text(
        "🧹 <b>Clean chat now?</b>\n\n"
        "This will try to delete recent messages from both you and bot in this private chat.\n"
        f"Range: last <b>{CLEAN_SCAN_LIMIT}</b> message IDs.\n"
        "<b>/files and /folders data will stay safe</b> (not deleted).\n\n"
        "Continue?"
        f"{note}",
        parse_mode=ParseMode.HTML,
        quote=True,
        reply_markup=_clean_buttons(message.from_user.id, message.id),
    )


@FileStream.on_callback_query(filters.regex(r"^clean:(yes|no):"))
async def clean_chat_confirm(bot: Client, cq: CallbackQuery):
    data = (cq.data or "").split(":")
    if len(data) < 4:
        await cq.answer("Invalid action", show_alert=True)
        return

    action = data[1]
    try:
        owner_id = int(data[2])
        source_message_id = int(data[3])
    except Exception:
        await cq.answer("Invalid action", show_alert=True)
        return

    if not cq.from_user or cq.from_user.id != owner_id:
        await cq.answer("This action is not for you.", show_alert=True)
        return

    if action == "no":
        await cq.answer("Cancelled")
        try:
            await cq.message.edit_text("❌ Clean cancelled.", parse_mode=ParseMode.HTML)
            await asyncio.sleep(2)
            await cq.message.delete()
        except Exception:
            pass
        return

    await cq.answer("Cleaning chat...")

    chat_id = cq.message.chat.id
    top_message_id = max(int(getattr(cq.message, "id", 0) or 0), source_message_id)

    # Remove prompt and original /clean command first (best effort)
    try:
        await cq.message.delete()
    except Exception:
        pass
    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=source_message_id)
    except Exception:
        pass

    ids = _candidate_ids(top_message_id, CLEAN_SCAN_LIMIT)

    deleted = 0
    for i in range(0, len(ids), 100):
        chunk = ids[i : i + 100]
        try:
            result = await bot.delete_messages(chat_id=chat_id, message_ids=chunk)
            deleted += _count_deleted(result, len(chunk))
        except Exception:
            continue

    if deleted > 0:
        status_text = (
            f"🧹 Chat cleaned. Removed around <b>{deleted}</b> messages.\n"
            "📁 /files and /folders data is safe."
        )
    else:
        status_text = (
            "⚠️ Could not remove old messages in this run.\n"
            "Telegram may block very old/protected messages.\n"
            "Try again or clear chat manually."
        )

    try:
        status = await bot.send_message(
            chat_id=chat_id,
            text=status_text,
            parse_mode=ParseMode.HTML,
        )
        await asyncio.sleep(4)
        await status.delete()
    except Exception:
        pass
