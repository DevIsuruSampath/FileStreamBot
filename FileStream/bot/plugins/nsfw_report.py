import asyncio
import secrets
import html
from datetime import datetime

from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums.parse_mode import ParseMode

from FileStream.bot import FileStream
from FileStream.config import Telegram, NSFW
from FileStream.utils.database import Database
from FileStream.utils.nsfw import scan_message
from FileStream.server.exceptions import FileNotFound
from FileStream.utils.bot_utils import verify_user
from FileStream.utils.file_cleanup import delete_file_entry


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)


def _report_id() -> str:
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "")


def _is_object_id(value: str) -> bool:
    return bool(value) and len(value) == 24 and all(c in "0123456789abcdef" for c in value.lower())


async def _delete_file(bot: Client, file_info: dict):
    await delete_file_entry(db, file_info, bot=bot)


async def _delete_folder(bot: Client, folder: dict):
    file_ids = list(folder.get("files", []))
    for fid in file_ids:
        try:
            file_info = await db.get_file(fid)
        except Exception:
            continue
        await _delete_file(bot, file_info)

    try:
        await db.delete_folder_by_id(folder.get("_id"))
    except Exception:
        pass


async def _scan_file_by_id(bot: Client, file_id: str) -> tuple[bool, str]:
    try:
        file_info = await db.get_file(file_id)
    except Exception:
        raise FileNotFound

    if not Telegram.FLOG_CHANNEL or not file_info.get("flog_msg_id"):
        return False, "no_flog"

    try:
        log_msg = await bot.get_messages(Telegram.FLOG_CHANNEL, int(file_info["flog_msg_id"]))
        blocked, reason = await scan_message(log_msg)
        return blocked, reason
    except Exception:
        return False, "scan_error"


async def _scan_folder_by_id(bot: Client, folder_id: str) -> tuple[bool, str]:
    folder = await db.get_folder(folder_id)
    for fid in folder.get("files", []):
        try:
            blocked, reason = await _scan_file_by_id(bot, fid)
        except Exception:
            continue
        if blocked:
            return True, reason
    return False, "clean"


async def process_report(bot: Client, message: Message, target_type: str, target_id: str):
    if not Telegram.NUDENET_CHANNEL:
        await message.reply_text("NUDENET_CHANNEL not set.", quote=True)
        return

    report_id = _report_id()
    reporter = message.from_user
    report_by = reporter.id if reporter else 0

    if target_type == "file":
        try:
            try:
                file_info = await db.get_file(target_id)
            except Exception:
                file_info, _ = await db.resolve_public_file(target_id)
        except Exception:
            await message.reply_text("File not found.", quote=True)
            return
        uploader_id = file_info.get("user_id")
        uploader_ref = f"<code>{uploader_id}</code>"
        target_label = f"File Ref: <code>{target_id}</code>"
        target_name = html.escape(file_info.get("file_name") or "file")
    else:
        try:
            try:
                folder = await db.get_folder(target_id)
            except Exception:
                folder, _ = await db.resolve_public_folder(target_id)
        except Exception:
            await message.reply_text("Folder not found.", quote=True)
            return
        uploader_id = folder.get("user_id")
        uploader_ref = f"<code>{uploader_id}</code>"
        target_label = f"Folder Ref: <code>{target_id}</code>"
        target_name = html.escape(folder.get("title") or "Folder")

    doc = {
        "_id": report_id,
        "type": target_type,
        "target_id": str(target_id),
        "report_by": report_by,
        "uploader_id": uploader_id,
        "status": "scanning",
        "created_at": datetime.utcnow().timestamp(),
    }
    await db.add_nsfw_report(doc)

    report_text = (
        "<b>🚨 NSFW Report</b>\n\n"
        f"<b>Report ID:</b> <code>{report_id}</code>\n"
        f"<b>Report By:</b> <a href='tg://user?id={report_by}'>User</a>\n"
        f"<b>Report User ID:</b> <code>{report_by}</code>\n"
        f"<b>Uploader ID:</b> {uploader_ref}\n"
        f"<b>Target:</b> {target_label}\n"
        f"<b>Name:</b> <code>{target_name}</code>\n\n"
        "<b>Status:</b> <code>Scanning NudeNet...</code>"
    )

    report_msg = await bot.send_message(
        chat_id=Telegram.NUDENET_CHANNEL,
        text=report_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

    await db.update_nsfw_report(report_id, {"report_msg_id": report_msg.id})

    await message.reply_text("✅ Report received. Scanning now...", quote=True)

    async def _finalize():
        try:
            if target_type == "file":
                blocked, reason = await _scan_file_by_id(bot, target_id)
            else:
                blocked, reason = await _scan_folder_by_id(bot, target_id)

            if blocked:
                if target_type == "file":
                    await _delete_file(bot, await db.get_file(target_id))
                else:
                    await _delete_folder(bot, await db.get_folder(target_id))

                # warn uploader
                if uploader_id:
                    try:
                        await bot.send_message(
                            chat_id=uploader_id,
                            text=(
                                "⚠️ Your content was removed due to adult content report.\n"
                                f"Target: {target_label}"
                            ),
                        )
                    except Exception:
                        pass

                result_text = report_text.replace(
                    "<code>Scanning NudeNet...</code>",
                    "<code>Removed (NSFW)</code>",
                )

                await bot.send_message(
                    chat_id=report_by,
                    text="✅ Thank you for the report. Adult content removed.",
                )
            else:
                result_text = report_text.replace(
                    "<code>Scanning NudeNet...</code>",
                    "<code>Not adult (kept)</code>",
                )
                await bot.send_message(
                    chat_id=report_by,
                    text="✅ Thank you. NudeNet did not detect adult content.",
                )

            try:
                await report_msg.edit_text(result_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception:
                pass

            await db.update_nsfw_report(report_id, {"status": "removed" if blocked else "kept", "reason": reason})
        except Exception as exc:
            try:
                await report_msg.edit_text(
                    report_text.replace(
                        "<code>Scanning NudeNet...</code>",
                        f"<code>Error: {html.escape(str(exc))[:200]}</code>",
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

    asyncio.create_task(_finalize())


@FileStream.on_message(filters.command("rm_adult") & filters.private)
async def rm_adult_cmd(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: /rm_adult <file_id|folder_id>", quote=True)
        return

    target = message.command[1].strip()
    target_type = "file" if _is_object_id(target) else "folder"

    await process_report(bot, message, target_type, target)
