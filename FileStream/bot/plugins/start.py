import logging
import math
import html
from FileStream import __version__
from FileStream.bot import FileStream
from FileStream.server.exceptions import FileNotFound
from FileStream.utils.bot_utils import gen_linkx, verify_user, gen_file_list_button
from FileStream.config import Telegram
from FileStream.utils.database import Database
from FileStream.utils.translation import LANG, BUTTON
from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.enums.parse_mode import ParseMode
import asyncio

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

async def delete_later(filex, message, delay=3600):
    await asyncio.sleep(delay)
    try:
        await filex.delete()
        await message.delete()
    except Exception:
        pass

@FileStream.on_message(filters.command('start') & filters.private)
async def start(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return


    payload = ""
    if " " in message.text:
        payload = message.text.split(" ", 1)[1].strip()

    if not payload:
        if Telegram.START_PIC:
            await message.reply_photo(
                photo=Telegram.START_PIC,
                caption=LANG.START_TEXT.format(message.from_user.mention, FileStream.username),
                parse_mode=ParseMode.HTML,
                reply_markup=BUTTON.START_BUTTONS
            )
        else:
            await message.reply_text(
                text=LANG.START_TEXT.format(message.from_user.mention, FileStream.username),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=BUTTON.START_BUTTONS
            )
    else:
        if payload.startswith("stream_"):
            file_id = payload.split("stream_", 1)[1]
            try:
                file_check = await db.get_file(file_id)
                file_id = str(file_check['_id'])
                reply_markup, stream_text = await gen_linkx(m=message, _id=file_id,
                                                            name=[FileStream.username, FileStream.fname])
                await message.reply_text(
                    text=stream_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                    quote=True
                )

            except FileNotFound as e:
                await message.reply_text("File Not Found")
            except Exception as e:
                await message.reply_text("Something Went Wrong")
                logging.error(e)

        elif payload.startswith("file_"):
            file_id = payload.split("file_", 1)[1]
            try:
                file_check = await db.get_file(file_id)
                file_id = file_check['file_id']
                file_name = file_check.get('file_name') or "file"
                safe_name = html.escape(file_name)
                if len(safe_name) > 1000:
                    safe_name = safe_name[:1000] + "…"
                filex = await message.reply_cached_media(
                    file_id=file_id,
                    caption=f"<b>{safe_name}</b>",
                    parse_mode=ParseMode.HTML,
                )
                asyncio.create_task(delete_later(filex, message))

            except FileNotFound as e:
                await message.reply_text("**File Not Found**", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply_text("Something Went Wrong")
                logging.error(e)

        elif payload.startswith("report_file_") or payload.startswith("report_folder_"):
            from FileStream.bot.plugins.nsfw_report import process_report
            target_type = "file" if payload.startswith("report_file_") else "folder"
            target_id = payload.split("_", 2)[2]
            await process_report(bot, message, target_type, target_id)
        else:
            await message.reply_text("**Invalid Command**", parse_mode=ParseMode.MARKDOWN)

@FileStream.on_message(filters.private & filters.command(["about"]))
async def about(bot, message):
    if not await verify_user(bot, message):
        return
    if Telegram.START_PIC:
        await message.reply_photo(
            photo=Telegram.START_PIC,
            caption=LANG.ABOUT_TEXT.format(FileStream.fname, __version__),
            parse_mode=ParseMode.HTML,
            reply_markup=BUTTON.ABOUT_BUTTONS
        )
    else:
        await message.reply_text(
            text=LANG.ABOUT_TEXT.format(FileStream.fname, __version__),
            disable_web_page_preview=True,
            reply_markup=BUTTON.ABOUT_BUTTONS
        )

@FileStream.on_message((filters.command('help')) & filters.private)
async def help_handler(bot, message):
    if not await verify_user(bot, message):
        return
    if Telegram.START_PIC:
        await message.reply_photo(
            photo=Telegram.START_PIC,
            caption=LANG.HELP_TEXT.format(Telegram.OWNER_ID),
            parse_mode=ParseMode.HTML,
            reply_markup=BUTTON.HELP_BUTTONS
        )
    else:
        await message.reply_text(
            text=LANG.HELP_TEXT.format(Telegram.OWNER_ID),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=BUTTON.HELP_BUTTONS
        )

# ---------------------------------------------------------------------------------------------------

@FileStream.on_message(filters.command('files') & filters.private)
async def my_files(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return
    
    file_list, total_files = await gen_file_list_button(1, message.from_user.id)

    if Telegram.FILE_PIC:
        await message.reply_photo(photo=Telegram.FILE_PIC,
                                  caption="Total files: {}".format(total_files),
                                  reply_markup=InlineKeyboardMarkup(file_list))
    else:
        await message.reply_text(text="Total files: {}".format(total_files),
                                 reply_markup=InlineKeyboardMarkup(file_list))
