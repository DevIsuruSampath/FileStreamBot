import datetime
import math
import os
import html
from FileStream import __version__
from FileStream.bot import FileStream
from FileStream.config import Telegram, Server
from FileStream.utils.translation import LANG, BUTTON
from FileStream.utils.bot_utils import gen_link, gen_file_list_button, get_public_file_context
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.file_cleanup import delete_file_entry
from FileStream.utils.file_properties import ensure_flog_media_exists
from FileStream.server.exceptions import FileNotFound
from FileStream.utils.client_identity import get_bot_name, get_bot_username
from FileStream.bot.plugins.donation import open_donation_menu
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.file_id import FileId, FileType, PHOTO_TYPES
from pyrogram.enums.parse_mode import ParseMode

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

async def edit_message(update: CallbackQuery, text: str, reply_markup=None, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True):
    if getattr(update.message, "photo", None) or getattr(update.message, "caption", None):
        await update.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        await update.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )


def _is_owner(file_info: dict, user_id: int) -> bool:
    try:
        return int(file_info.get("user_id")) == int(user_id)
    except Exception:
        return False

#---------------------[ START CMD ]---------------------#
@FileStream.on_callback_query(
    filters.regex(r"^(home|help|about|support|N/A|close|msgdelete_|msgdelyes_|msgdelpvt_|msgdelpvtyes_|mainstream_|userfiles_|myfile_|sendfile_)")
)
async def cb_data(bot, update: CallbackQuery):
    try:
        data = update.data or ""
    except Exception:
        return

    try:
        usr_cmd = data.split("_")
    except Exception:
        return

    if not usr_cmd or not usr_cmd[0]:
        return

    if usr_cmd[0] == "home":
        await edit_message(
            update,
            text=LANG.START_TEXT.format(update.from_user.mention, get_bot_username(bot)),
            reply_markup=BUTTON.start_buttons(bot),
            parse_mode=ParseMode.HTML
        )
    elif usr_cmd[0] == "help":
        await edit_message(
            update,
            text=LANG.HELP_TEXT.format(Telegram.OWNER_ID),
            reply_markup=BUTTON.help_buttons(bot),
            parse_mode=ParseMode.HTML
        )
    elif usr_cmd[0] == "about":
        await edit_message(
            update,
            text=LANG.ABOUT_TEXT.format(get_bot_name(bot), __version__),
            reply_markup=BUTTON.about_buttons(bot),
            parse_mode=ParseMode.HTML
        )
    elif usr_cmd[0] == "support":
        await open_donation_menu(update.message, bot, edit=True)

    #---------------------[ MY FILES CMD ]---------------------#

    elif usr_cmd[0] == "N/A":
        await update.answer("N/A", True)
    elif usr_cmd[0] == "close":
        try:
            await update.answer()
        except Exception:
            pass
        try:
            await update.message.delete()
        except Exception:
            pass
    elif usr_cmd[0] == "msgdelete":
        if len(usr_cmd) < 3:
            await update.answer("Invalid action")
            return
        await edit_message(
            update,
            "**⚠️ Confirm Delete**\n\nAre you sure you want to delete this file?",
            InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data=f"msgdelyes_{usr_cmd[1]}_{usr_cmd[2]}"), InlineKeyboardButton("❌ No", callback_data=f"myfile_{usr_cmd[1]}_{usr_cmd[2]}")]])
        )
    elif usr_cmd[0] == "msgdelyes":
        if len(usr_cmd) < 3:
            await update.answer("Invalid action")
            return
        await delete_user_file(bot, usr_cmd[1], int(usr_cmd[2]), update)
        return
    elif usr_cmd[0] == "msgdelpvt":
        if len(usr_cmd) < 2:
            await update.answer("Invalid action")
            return
        await edit_message(
            update,
            "**⚠️ Confirm Delete**\n\nAre you sure you want to delete this file?",
            InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data=f"msgdelpvtyes_{usr_cmd[1]}"), InlineKeyboardButton("❌ No", callback_data=f"mainstream_{usr_cmd[1]}")]])
        )
    elif usr_cmd[0] == "msgdelpvtyes":
        if len(usr_cmd) < 2:
            await update.answer("Invalid action")
            return
        await delete_user_filex(bot, usr_cmd[1], update)
        return

    elif usr_cmd[0] == "mainstream":
        if len(usr_cmd) < 2:
            await update.answer("Invalid action")
            return
        _id = usr_cmd[1]
        # gen_link from bot_utils handles Ads/Shortener internally
        reply_markup, stream_text = await gen_link(_id=_id, bot=bot)
        await update.message.edit_text(
            text=stream_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )

    elif usr_cmd[0] == "userfiles":
        if len(usr_cmd) < 2:
            await update.answer("Invalid action")
            return
        try:
            page_no = int(usr_cmd[1])
        except Exception:
            page_no = 1
        file_list, total_files = await gen_file_list_button(page_no, update.from_user.id)
        await edit_message(update, "Total files: {}".format(total_files), InlineKeyboardMarkup(file_list))
    elif usr_cmd[0] == "myfile":
        if len(usr_cmd) < 3:
            await update.answer("Invalid action")
            return
        await gen_file_menu(usr_cmd[1], usr_cmd[2], update)
        return
    elif usr_cmd[0] == "sendfile":
        if len(usr_cmd) < 2:
            await update.answer("Invalid action")
            return
        try:
            myfile = await db.get_file(usr_cmd[1])
            await ensure_flog_media_exists(myfile, bot=bot, prune_stale=True, db_instance=db)
        except FileNotFound:
            await update.answer("File Not Found")
            return
        if not _is_owner(myfile, update.from_user.id):
            await update.answer("Unauthorized", show_alert=True)
            return
        file_name = myfile.get('file_name') or "file"
        await update.answer(f"Sending File {file_name}")
        safe_name = html.escape(file_name)
        if len(safe_name) > 1000:
            safe_name = safe_name[:1000] + "…"
        try:
            await update.message.reply_cached_media(
                myfile['file_id'],
                caption=f"<b>{safe_name}</b>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await update.answer("Failed to send file")
    else:
        return


    #---------------------[ MY FILES FUNC ]---------------------#

async def gen_file_menu(_id, file_list_no, update: CallbackQuery):
    try:
        myfile_info=await db.get_file(_id)
    except FileNotFound:
        await update.answer("File Not Found")
        return

    if not _is_owner(myfile_info, update.from_user.id):
        await update.answer("Unauthorized", show_alert=True)
        return

    try:
        file_id = FileId.decode(myfile_info['file_id'])
    except Exception:
        await update.answer("File Not Found")
        return

    if file_id.file_type in PHOTO_TYPES:
        file_type = "Image"
    elif file_id.file_type == FileType.VOICE:
        file_type = "Voice"
    elif file_id.file_type in (FileType.VIDEO, FileType.ANIMATION, FileType.VIDEO_NOTE):
        file_type = "Video"
    elif file_id.file_type == FileType.DOCUMENT:
        file_type = "Document"
    elif file_id.file_type == FileType.STICKER:
        file_type = "Sticker"
    elif file_id.file_type == FileType.AUDIO:
        file_type = "Audio"
    else:
        file_type = "Unknown"

    file_name = (myfile_info.get("file_name") or "").lower()
    ext = os.path.splitext(file_name)[1]
    video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
    audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}
    is_streamable = file_type in ("Video", "Audio") or ext in video_ext or ext in audio_ext

    _, _, public_url = await get_public_file_context(myfile_info)

    MYFILES_BUTTONS = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Open", url=public_url)],
            [InlineKeyboardButton("Share", url=public_url), InlineKeyboardButton("Open in Bot", url=public_url)],
            [InlineKeyboardButton("📥 Get File", callback_data=f"sendfile_{myfile_info['_id']}"),
             InlineKeyboardButton("🗑️ Revoke", callback_data=f"msgdelete_{myfile_info['_id']}_{file_list_no}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="userfiles_{}".format(file_list_no))]
        ]
    )

    TiMe = myfile_info['time']
    if isinstance(TiMe, (int, float)):
        date = datetime.datetime.fromtimestamp(TiMe)
        readable_time = date.date()
    else:
        readable_time = TiMe

    safe_name = html.escape(myfile_info.get('file_name') or "file")
    safe_type = html.escape(file_type)
    safe_time = html.escape(str(readable_time))
    safe_category = html.escape(myfile_info.get('category') or "Other")

    await edit_message(
        update,
        "<b>File Name :</b> <code>{}</code>\n<b>File Size :</b> <code>{}</code>\n<b>File Type :</b> <code>{}</code>\n<b>Category :</b> <code>{}</code>\n<b>Created On :</b> <code>{}</code>".format(
            safe_name,
            humanbytes(int(myfile_info.get('file_size') or 0)),
            safe_type,
            safe_category,
            safe_time,
        ),
        MYFILES_BUTTONS,
        parse_mode=ParseMode.HTML,
    )


async def delete_user_file(bot, _id, file_list_no: int, update:CallbackQuery):

    try:
        myfile_info=await db.get_file(_id)
    except FileNotFound:
        await update.answer("File Already Deleted")
        return

    if not _is_owner(myfile_info, update.from_user.id):
        await update.answer("Unauthorized", show_alert=True)
        return

    await delete_file_entry(db, myfile_info, bot=bot)
    caption = "**✅ File Deleted Successfully!**"
    if update.message.caption:
        caption += update.message.caption.replace("**⚠️ Confirm Delete**\n\nAre you sure you want to delete this file?", "")
    await edit_message(
        update,
        caption,
        InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"userfiles_1")]])
    )

async def delete_user_filex(bot, _id, update:CallbackQuery):

    try:
        myfile_info=await db.get_file(_id)
    except FileNotFound:
        await update.answer("File Already Deleted")
        return

    if not _is_owner(myfile_info, update.from_user.id):
        await update.answer("Unauthorized", show_alert=True)
        return

    await delete_file_entry(db, myfile_info, bot=bot)
    await edit_message(
        update,
        "**✅ File Deleted Successfully!**\n\n",
        InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data=f"close")]])
    )
