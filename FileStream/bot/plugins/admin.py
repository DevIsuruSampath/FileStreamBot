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

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode

# Logger setup to catch errors
logger = logging.getLogger(__name__)

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

# Admin IDs setup
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
    """Converts seconds to a human-readable string."""
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
    await m.reply_text(f"Your User ID is: `{m.from_user.id}`\nOwner ID in Config: `{Telegram.OWNER_ID}`", quote=True)

@FileStream.on_message(filters.command("ads") & filters.private)
async def ads_toggle(c: Client, m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.reply_text(f"⚠️ **Access Denied.**", quote=True)
        return

    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        status = await db.get_ads_status()
        state = "ON" if status else "OFF"
        await m.reply_text(f"**Ads are currently:** `{state}`\nUsage: `/ads on` or `/ads off`", parse_mode=ParseMode.MARKDOWN, quote=True)
        return

    action = parts[1].strip().lower()
    if action == "on":
        await db.update_ads_status(True)
        await m.reply_text(text="**✅ Ads have been enabled.**", parse_mode=ParseMode.MARKDOWN, quote=True)
    elif action == "off":
        await db.update_ads_status(False)
        await m.reply_text(text="**❌ Ads have been disabled.**", parse_mode=ParseMode.MARKDOWN, quote=True)

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
            await m.reply_text(text=f"`{user_id}`** is Banned**", parse_mode=ParseMode.MARKDOWN, quote=True)
        except Exception as e:
            await m.reply_text(text=f"**Error: {e}**", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(text=f"`{user_id}`** is Already Banned**", parse_mode=ParseMode.MARKDOWN, quote=True)

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
            await m.reply_text(text=f"`{user_id}`** is Unbanned**", parse_mode=ParseMode.MARKDOWN, quote=True)
        except Exception as e:
            await m.reply_text(text=f"**Error: {e}**", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(text=f"`{user_id}`** is not Banned**", parse_mode=ParseMode.MARKDOWN, quote=True)

@FileStream.on_message(filters.command("broadcast") & filters.private & filters.user(Telegram.OWNER_ID) & filters.reply)
async def broadcast_(c, m):
    all_users = await db.get_all_users()
    broadcast_msg = m.reply_to_message
    
    while True:
        broadcast_id = ''.join([random.choice(string.ascii_letters) for i in range(3)])
        if not broadcast_ids.get(broadcast_id):
            break
            
    out = await m.reply_text(text="Broadcast initiated...")
    start_time = time.time()
    total_users = await db.total_users_count()
    done, failed, success = 0, 0, 0
    
    broadcast_ids[broadcast_id] = dict(total=total_users, current=done, failed=failed, success=success)
    
    async with aiofiles.open('broadcast.txt', 'w') as broadcast_log_file:
        async for user in all_users:
            sts, msg = await send_msg(user_id=int(user['id']), message=broadcast_msg)
            if msg: await broadcast_log_file.write(msg)
            
            if sts == 200: success += 1
            else: failed += 1
            if sts == 400: await db.delete_user(user['id'])
            
            done += 1
            if broadcast_ids.get(broadcast_id) is None: break
            
            # Update status every 20 users to avoid FloodWait
            if done % 20 == 0:
                try:
                    await out.edit_text(f"Broadcast Status\n\ncurrent: {done}\nfailed:{failed}\nsuccess: {success}")
                except:
                    pass

    if broadcast_ids.get(broadcast_id): broadcast_ids.pop(broadcast_id)
    
    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    try: await out.delete()
    except: pass
    
    if failed == 0:
        await m.reply_text(f"Broadcast done in `{completed_in}`\nTotal: {total_users}\nSuccess: {success}, Failed: {failed}", quote=True)
    else:
        await m.reply_document(document='broadcast.txt', caption=f"Broadcast done in `{completed_in}`\nTotal: {total_users}\nSuccess: {success}, Failed: {failed}", quote=True)
    
    if os.path.exists('broadcast.txt'): os.remove('broadcast.txt')

@FileStream.on_message(filters.command("del") & filters.private & filters.user(Telegram.OWNER_ID))
async def del_file(c: Client, m: Message):
    try:
        file_id = m.text.split(" ")[-1]
        file_info = await db.get_file(file_id)
        await db.delete_one_file(file_info['_id'])
        await db.count_links(file_info['user_id'], "-")
        await m.reply_text(text=f"**File Deleted Successfully!**", quote=True)
    except FIleNotFound:
        await m.reply_text(text=f"**File already deleted**", quote=True)
    except Exception as e:
        await m.reply_text(f"Error: {e}", quote=True)

@FileStream.on_message(filters.command("stats") & filters.user(Telegram.OWNER_ID))
async def show_stats(client: Client, message: Message):
    try:
        sys_uptime = get_readable_time(int(time.time() - psutil.boot_time()))
        bot_uptime = get_readable_time(int(time.time() - StartTime))
        
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('.')
        
        text = (
            f"**System Stats**\n"
            f"**Uptime:** {sys_uptime} (Bot: {bot_uptime})\n"
            f"**CPU:** {cpu}%\n"
            f"**RAM:** {humanbytes(ram.used)} / {humanbytes(ram.total)}\n"
            f"**Disk:** {humanbytes(disk.used)} / {humanbytes(disk.total)}"
        )
        
        await message.reply_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Close", callback_data="close_panel")]])
        )
    except Exception as e:
        logger.error(f"Stats Error: {e}")
        await message.reply_text("Stats Error")
