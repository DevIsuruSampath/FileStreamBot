import asyncio
import math
import html
import os
from typing import Union
from pyrogram.errors import UserNotParticipant, FloodWait
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from FileStream.utils.translation import LANG
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.shortener import shorten
from FileStream.utils.category import detect_category
from FileStream.config import Telegram, Server
from FileStream.bot import FileStream

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

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

async def is_user_joined(bot, message: Message):
    if not getattr(message, "from_user", None):
        return False
    if Telegram.FORCE_SUB_ID:
        # Strip @ if provided
        fsid = str(Telegram.FORCE_SUB_ID).lstrip("@").strip()
        if fsid.startswith("-100") and fsid.lstrip("-").isdigit():
            channel_chat_id = int(fsid)
        elif fsid.lstrip('-').isdigit():
            channel_chat_id = int(fsid)
        else:
            channel_chat_id = fsid
    else:
        return 200
    try:
        user = await bot.get_chat_member(chat_id=channel_chat_id, user_id=message.from_user.id)
        if user.status == "BANNED":
            await message.reply_text(
                text=LANG.BAN_TEXT.format(Telegram.OWNER_ID),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return False
    except UserNotParticipant:
        invite_link = await get_invite_link(bot, chat_id=channel_chat_id)
        join_markup = None
        join_url = None
        if invite_link and getattr(invite_link, "invite_link", None):
            join_url = invite_link.invite_link
        else:
            # Fallback to public channel link if available
            if isinstance(channel_chat_id, str) and channel_chat_id and not channel_chat_id.lstrip("-").isdigit():
                join_url = f"https://t.me/{channel_chat_id.lstrip('@')}"
            elif Telegram.UPDATES_CHANNEL:
                join_url = f"https://t.me/{str(Telegram.UPDATES_CHANNEL).lstrip('@')}"
        if join_url:
            join_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("❆ Jᴏɪɴ Oᴜʀ Cʜᴀɴɴᴇʟ ❆", url=join_url)]]
            )

        if Telegram.VERIFY_PIC:
            ver = await message.reply_photo(
                photo=Telegram.VERIFY_PIC,
                caption="<i>Jᴏɪɴ ᴍʏ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜsᴇ ᴍᴇ 🔐</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=join_markup
            )
        else:
            ver = await message.reply_text(
                text = "<i>Jᴏɪɴ ᴍʏ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜsᴇ ᴍᴇ 🔐</i>",
                reply_markup=join_markup,
                parse_mode=ParseMode.HTML
            )
        await asyncio.sleep(30)
        try:
            await ver.delete()
            await message.delete()
        except Exception:
            pass
        return False
    except Exception:
        await message.reply_text(
            text = f"<i>Sᴏᴍᴇᴛʜɪɴɢ ᴡʀᴏɴɢ ᴄᴏɴᴛᴀᴄᴛ ᴍʏ ᴅᴇᴠᴇʟᴏᴘᴇʀ</i> <b><a href='https://t.me/{Telegram.UPDATES_CHANNEL}'>[ ᴄʟɪᴄᴋ ʜᴇʀᴇ ]</a></b>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True)
        return False
    return True

#---------------------[ PRIVATE GEN LINK + CALLBACK ]---------------------#

async def gen_link(_id):
    file_info = await db.get_file(_id)
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
    if len(safe_name) > 200:
        safe_name = safe_name[:200] + "…"

    # 1. Base Links (Normal)
    page_link = f"{Server.URL}watch/{_id}"
    stream_link = f"{Server.URL}dl/{_id}"
    file_link = f"https://t.me/{FileStream.username}?start=file_{_id}"

    # 2. Check Database for ADS Status
    if await db.get_ads_status():
        # Only shorten links that will actually be shown
        if is_streamable:
            page_link = await shorten(page_link)
        stream_link = await shorten(stream_link)

    safe_stream = html.escape(stream_link)
    safe_page = html.escape(page_link)

    if is_streamable:
        stream_text = LANG.STREAM_TEXT.format(safe_name, file_size, safe_category, safe_stream, safe_page)
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("sᴛʀᴇᴀᴍ", url=page_link), InlineKeyboardButton("ᴅᴏᴡɴʟᴏᴀᴅ", url=stream_link)],
                [InlineKeyboardButton("ɢᴇᴛ ғɪʟᴇ", url=file_link), InlineKeyboardButton("ʀᴇᴠᴏᴋᴇ ғɪʟᴇ", callback_data=f"msgdelpvt_{_id}")],
                [InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]
            ]
        )
    else:
        stream_text = LANG.STREAM_TEXT_X.format(safe_name, file_size, safe_category, safe_stream)
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("ᴅᴏᴡɴʟᴏᴀᴅ", url=stream_link)],
                [InlineKeyboardButton("ɢᴇᴛ ғɪʟᴇ", url=file_link), InlineKeyboardButton("ʀᴇᴠᴏᴋᴇ ғɪʟᴇ", callback_data=f"msgdelpvt_{_id}")],
                [InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]
            ]
        )
    return reply_markup, stream_text

#---------------------[ GEN STREAM LINKS FOR CHANNEL ]---------------------#

async def gen_linkx(m:Message , _id, name: list):
    file_info = await db.get_file(_id)
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
    if len(safe_name) > 200:
        safe_name = safe_name[:200] + "…"

    # 1. Base Links (Normal)
    page_link = f"{Server.URL}watch/{_id}"
    stream_link = f"{Server.URL}dl/{_id}"
    
    # 2. Check Database for ADS Status
    if await db.get_ads_status():
        # Only shorten links that will actually be shown
        if is_streamable:
            page_link = await shorten(page_link)
        stream_link = await shorten(stream_link)

    safe_stream = html.escape(stream_link)
    safe_page = html.escape(page_link)

    if is_streamable:
        stream_text= LANG.STREAM_TEXT.format(safe_name, file_size, safe_category, safe_stream, safe_page)
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("sᴛʀᴇᴀᴍ", url=page_link), InlineKeyboardButton("ᴅᴏᴡɴʟᴏᴀᴅ", url=stream_link)]
            ]
        )
    else:
        stream_text= LANG.STREAM_TEXT_X.format(safe_name, file_size, safe_category, safe_stream)
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("ᴅᴏᴡɴʟᴏᴀᴅ", url=stream_link)]
            ]
        )
    return reply_markup, stream_text

#---------------------[ GEN FILE LIST BUTTON ]---------------------#

async def gen_file_list_button(file_list_no: int, user_id: int):
    if file_list_no < 1:
        file_list_no = 1

    total_files = await db.total_files(user_id)
    if total_files > 0:
        max_pages = math.ceil(total_files / 10)
        if file_list_no > max_pages:
            file_list_no = max_pages

    file_range=[file_list_no*10-10+1, file_list_no*10]
    user_files, _ = await db.find_files(user_id, file_range)

    file_list=[]
    async for x in user_files:
        name = x.get("file_name") or "file"
        # Prevent overly long button labels
        if len(name) > 50:
            name = name[:50] + "…"
        file_list.append([InlineKeyboardButton(name, callback_data=f"myfile_{x['_id']}_{file_list_no}")])
    if total_files > 10:
        file_list.append(
                [InlineKeyboardButton("◄", callback_data="{}".format("userfiles_"+str(file_list_no-1) if file_list_no > 1 else 'N/A')),
                 InlineKeyboardButton(f"{file_list_no}/{math.ceil(total_files/10)}", callback_data="N/A"),
                 InlineKeyboardButton("►", callback_data="{}".format("userfiles_"+str(file_list_no+1) if total_files > file_list_no*10 else 'N/A'))]
        )
    if not file_list:
        file_list.append(
                [InlineKeyboardButton("ᴇᴍᴘᴛʏ", callback_data="N/A")])
    file_list.append([InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")])
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
                    InlineKeyboardButton("ᴄʜᴀɴɴᴇʟ ɪs ʙᴀɴɴᴇᴅ", callback_data="N/A")]])
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