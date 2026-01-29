import os
import time
import string
import random
import asyncio
import aiofiles
import datetime
import shutil
import psutil
import logging

# Pyrogram Imports
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode

# Custom Imports
from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram

# Initialize Logger
logger = logging.getLogger(__name__)

# Initialize DB
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

# Create Admin List
ADMIN_IDS = list(set([Telegram.OWNER_ID] + Telegram.AUTH_USERS))

# Global StartTime for Uptime calculation
StartTime = time.time()

# ---------------------[ HELPER FUNCTIONS ]---------------------#
def humanbytes(size):
    """Converts bytes to human readable format."""
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

def get_readable_time(seconds: int) -> str:
    """Converts seconds to a human-readable string (e.g., 2d 5h 30m)."""
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        ping_time += time_list.pop() + ", "
    time_list.reverse()
    ping_time += ":".join(time_list)
    return ping_time

# ---------------------[ COMMANDS ]---------------------#

@FileStream.on_message(filters.command("id"))
async def get_id(c: Client, m: Message):
    await m.reply_text(
        f"Your User ID is: `{m.from_user.id}`\nOwner ID in Config: `{Telegram.OWNER_ID}`", 
        quote=True
    )

@FileStream.on_message(filters.command("ads") & filters.private)
async def ads_toggle(c: Client, m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.reply_text(
            f"⚠️ **Access Denied.**\nYour ID `{m.from_user.id}` is not in `OWNER_ID` or `AUTH_USERS`.", 
            quote=True
        )
        return

    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        status = await db.get_ads_status()
        state = "ON" if status else "OFF"
        await m.reply_text(
            text=f"**Ads are currently:** `{state}`\nUsage: `/ads on` or `/ads off`",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    action = parts[1].strip().lower()
    if action == "on":
        await db.update_ads_status(True)
        await m.reply_text(text="**✅ Ads have been enabled.**", parse_mode=ParseMode.MARKDOWN, quote=True)
    elif action == "off":
        await db.update_ads_status(False)
        await m.reply_text(text="**❌ Ads have been disabled.**", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(
            text="Usage: `/ads on` or `/ads off`",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    await m.reply_text(
        text=f"**Total Users in DB:** `{await db.total_users_count()}`\n"
             f"**Banned Users in DB:** `{await db.total_banned_users_count()}`\n"
             f"**Total Links Generated: ** `{await db.total_files()}`",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )

@FileStream.on_message(filters.command("ban") & filters.private & filters.user(Telegram.OWNER_ID))
async def ban_user(b, m: Message):
    try:
        user_id = int(m.text.split("/ban ")[-1])
    except (IndexError, ValueError):
        await m.reply_text("Usage: `/ban user_id`", quote=True)
        return

    if not await db.is_user_banned(user_id):
        try:
            await db.ban_user(user_id)
            await db.delete_user(user_id)
            await m.reply_text(text=f"`{user_id}`** is Banned** ", parse_mode=ParseMode.MARKDOWN, quote=True)
            if not str(user_id).startswith('-100'):
                try:
                    await b.send_message(
                        chat_id=user_id,
                        text="**You are Banned from using The Bot**",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass
        except Exception as e:
            await m.reply_text(text=f"**something went wrong: {e}** ", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(text=f"`{user_id}`** is Already Banned** ", parse_mode=ParseMode.MARKDOWN, quote=True)

@FileStream.on_message(filters.command("unban") & filters.private & filters.user(Telegram.OWNER_ID))
async def unban_user(b, m: Message):
    try:
        user_id = int(m.text.split("/unban ")[-1])
    except (IndexError, ValueError):
        await m.reply_text("Usage: `/unban user_id`", quote=True)
        return

    if await db.is_user_banned(user_id):
        try:
            await db.unban_user(user_id)
            await m.reply_text(text=f"`{user_id}`** is Unbanned** ", parse_mode=ParseMode.MARKDOWN, quote=True)
            if not str(user_id).startswith('-100'):
                try:
                    await b.send_message(
                        chat_id=user_id,
                        text="**You are Unbanned. You can now use The Bot**",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass
        except Exception as e:
            await m.reply_text(text=f"** something went wrong: {e}**", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(text=f"`{user_id}`** is not Banned** ", parse_mode=ParseMode.MARKDOWN, quote=True)

@FileStream.on_message(filters.command("broadcast") & filters.private & filters.user(Telegram.OWNER_ID) & filters.reply)
async def broadcast_(c, m):
    all_users = await db.get_all_users()
    broadcast_msg = m.reply_to_message
    
    while True:
        broadcast_id = ''.join([random.choice(string.ascii_letters) for i in range(3)])
        if not broadcast_ids.get(broadcast_id):
            break
            
    out = await m.reply_text(
        text=f"Broadcast initiated! You will be notified with log file when all the users are notified."
    )
    
    start_time = time.time()
    total_users = await db.total_users_count()
    done = 0
    failed = 0
    success = 0
    
    broadcast_ids[broadcast_id] = dict(
        total=total_users,
        current=done,
        failed=failed,
        success=success
    )
    
    async with aiofiles.open('broadcast.txt', 'w') as broadcast_log_file:
        async for user in all_users:
            sts, msg = await send_msg(
                user_id=int(user['id']),
                message=broadcast_msg
            )
            if msg is not None:
                await broadcast_log_file.write(msg)
            if sts == 200:
                success += 1
            else:
                failed += 1
            if sts == 400:
                await db.delete_user(user['id'])
            done += 1
            
            if broadcast_ids.get(broadcast_id) is None:
                break
            else:
                broadcast_ids[broadcast_id].update(
                    dict(
                        current=done,
                        failed=failed,
                        success=success
                    )
                )
                try:
                    if done % 20 == 0:
                         await out.edit_text(f"Broadcast Status\n\ncurrent: {done}\nfailed:{failed}\nsuccess: {success}")
                except:
                    pass
                    
    if broadcast_ids.get(broadcast_id):
        broadcast_ids.pop(broadcast_id)
        
    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    await asyncio.sleep(3)
    try:
        await out.delete()
    except:
        pass
        
    if failed == 0:
        await m.reply_text(
            text=f"broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done}, {success} success and {failed} failed.",
            quote=True
        )
    else:
        await m.reply_document(
            document='broadcast.txt',
            caption=f"broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done}, {success} success and {failed} failed.",
            quote=True
        )
    if os.path.exists('broadcast.txt'):
        os.remove('broadcast.txt')

@FileStream.on_message(filters.command("del") & filters.private & filters.user(Telegram.OWNER_ID))
async def del_file(c: Client, m: Message):
    try:
        file_id = m.text.split(" ")[-1]
    except IndexError:
        await m.reply_text("Usage: `/del file_id`", quote=True)
        return

    try:
        file_info = await db.get_file(file_id)
    except FIleNotFound:
        await m.reply_text(
            text=f"**ꜰɪʟᴇ ᴀʟʀᴇᴀᴅʏ ᴅᴇʟᴇᴛᴇᴅ**",
            quote=True
        )
        return
        
    await db.delete_one_file(file_info['_id'])
    await db.count_links(file_info['user_id'], "-")
    await m.reply_text(
        text=f"**Fɪʟᴇ Dᴇʟᴇᴛᴇᴅ Sᴜᴄᴄᴇssғᴜʟʟʏ !** ",
        quote=True
    )

@FileStream.on_message(filters.command("stats") & filters.user(Telegram.OWNER_ID))
async def show_stats(client: Client, message: Message):
    try:
        sys_uptime = await asyncio.to_thread(psutil.boot_time)
        sys_uptime_str = get_readable_time(int(time.time() - sys_uptime))
        bot_uptime_str = get_readable_time(int(time.time() - StartTime))
        
        net_io_counters = await asyncio.to_thread(psutil.net_io_counters)
        cpu_percent = await asyncio.to_thread(psutil.cpu_percent, interval=0.5)
        cpu_cores = await asyncio.to_thread(psutil.cpu_count, logical=False)
        cpu_freq = await asyncio.to_thread(psutil.cpu_freq)
        cpu_freq_ghz = f"{cpu_freq.current / 1000:.2f}" if cpu_freq else "N/A"
        
        ram_info = await asyncio.to_thread(psutil.virtual_memory)
        ram_total = humanbytes(ram_info.total)
        ram_used = humanbytes(ram_info.used)
        ram_free = humanbytes(ram_info.free)

        total_disk, used_disk, free_disk = await asyncio.to_thread(shutil.disk_usage, '.')
        disk_percent = psutil.disk_usage('.').percent

        stats_text_val = (
            f"**System Statistics**\n\n"
            f"**System Uptime:** {sys_uptime_str}\n"
            f"**Bot Uptime:** {bot_uptime_str}\n\n"
            f"**CPU:** {cpu_percent}% ({cpu_cores} Cores, {cpu_freq_ghz} GHz)\n"
            f"**RAM:** {ram_used} / {ram_total} (Free: {ram_free})\n"
            f"**Disk:** {humanbytes(used_disk)} / {humanbytes(total_disk)} ({disk_percent}%)\n\n"
            f"**Upload:** {humanbytes(net_io_counters.bytes_sent)}\n"
            f"**Download:** {humanbytes(net_io_counters.bytes_recv)}"
        )

        await message.reply_text(
            text=stats_text_val,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Close", callback_data="close_panel")]]
            )
        )
    except Exception as e:
        logger.error(f"Error in show_stats: {e}", exc_info=True)
        await message.reply_text(f"Error: {str(e)}")
