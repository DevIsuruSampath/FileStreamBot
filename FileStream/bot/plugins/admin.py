import os
import time
import math
import shutil
import psutil
import string
import random
import asyncio
import aiofiles
import datetime
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FIleNotFound
from FileStream.config import Telegram
from FileStream.utils.human_readable import humanbytes

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

# Record Bot Start Time
BOT_START_TIME = time.time()

# Create Admin List
ADMIN_IDS = list(set([Telegram.OWNER_ID] + Telegram.AUTH_USERS))

# ---------------------[ HELPER FUNCTIONS ]---------------------#
def get_readable_time(seconds: int) -> str:
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

# ---------------------[ CHECK YOUR ID ]---------------------#
@FileStream.on_message(filters.command("id"))
async def get_id(c: Client, m: Message):
    await m.reply_text(f"Your User ID is: `{m.from_user.id}`\nOwner ID in Config: `{Telegram.OWNER_ID}`", quote=True)

# ---------------------[ ADS TOGGLE COMMAND ]---------------------#
@FileStream.on_message(filters.command("ads") & filters.private)
async def ads_toggle(c: Client, m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.reply_text(f"⚠️ **Access Denied.**\nYour ID `{m.from_user.id}` is not in `OWNER_ID` or `AUTH_USERS`.", quote=True)
        return

    if len(m.command) < 2:
        status = await db.get_ads_status()
        state = "ON" if status else "OFF"
        await m.reply_text(
            text=f"**Ads are currently:** `{state}`\nUsage: `/ads on` or `/ads off`",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    action = m.command[1].strip().lower()
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

# ---------------------[ STATUS COMMAND (UPDATED) ]---------------------#
@FileStream.on_message(filters.command("status") & filters.private & filters.user(Telegram.OWNER_ID))
async def sts(c: Client, m: Message):
    # 1. Calculate Uptime
    bot_uptime = get_readable_time(int(time.time() - BOT_START_TIME))
    sys_uptime = get_readable_time(int(time.time() - psutil.boot_time()))

    # 2. CPU Usage
    cpu_usage = psutil.cpu_percent(interval=0.5)
    
    # 3. RAM Usage
    mem = psutil.virtual_memory()
    ram_used = humanbytes(mem.used)
    ram_total = humanbytes(mem.total)
    ram_free = humanbytes(mem.available)
    
    # 4. Disk Usage
    disk = shutil.disk_usage("/")
    disk_used = humanbytes(disk.used)
    disk_total = humanbytes(disk.total)
    disk_percent = f"{int((disk.used / disk.total) * 100)}%"
    
    # 5. Network Usage
    net = psutil.net_io_counters()
    upload = humanbytes(net.bytes_sent)
    download = humanbytes(net.bytes_recv)

    # 6. DB Stats
    total_users = await db.total_users_count()
    banned_users = await db.total_banned_users_count()
    total_files = await db.total_files()

    stats_text = f"""<b>📊 System Statistics</b>

<b>System Uptime:</b> {sys_uptime}
<b>Bot Uptime:</b> {bot_uptime}

<b>CPU:</b> {cpu_usage}%
<b>RAM:</b> {ram_used} / {ram_total} (Free: {ram_free})
<b>Disk:</b> {disk_used} / {disk_total} ({disk_percent})

<b>Upload:</b> {upload}
<b>Download:</b> {download}

<b>-----------------------</b>

<b>Total Users in DB:</b> {total_users}
<b>Banned Users in DB:</b> {banned_users}
<b>Total Links Generated:</b> {total_files}"""

    await m.reply_text(
        text=stats_text,
        parse_mode=ParseMode.HTML,
        quote=True,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]])
    )

# ---------------------[ BAN USER ]---------------------#
@FileStream.on_message(filters.command("ban") & filters.private & filters.user(Telegram.OWNER_ID))
async def ban_user(b: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("**Usage:** `/ban [User_ID]`", quote=True)
        return
    
    try:
        target_id = int(m.command[1])
    except ValueError:
        await m.reply_text("**Error:** User ID must be a number.", quote=True)
        return

    if not await db.is_user_banned(target_id):
        try:
            await db.ban_user(target_id)
            await db.delete_user(target_id)
            await m.reply_text(text=f"`{target_id}`** is Banned** ", parse_mode=ParseMode.MARKDOWN, quote=True)
            if not str(target_id).startswith('-100'):
                try:
                    await b.send_message(
                        chat_id=target_id,
                        text="**You have been Banned from using this Bot**",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                except:
                    pass
        except Exception as e:
            await m.reply_text(text=f"**Something went wrong: {e}** ", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(text=f"`{target_id}`** is Already Banned** ", parse_mode=ParseMode.MARKDOWN, quote=True)

# ---------------------[ UNBAN USER ]---------------------#
@FileStream.on_message(filters.command("unban") & filters.private & filters.user(Telegram.OWNER_ID))
async def unban_user(b: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("**Usage:** `/unban [User_ID]`", quote=True)
        return

    try:
        target_id = int(m.command[1])
    except ValueError:
        await m.reply_text("**Error:** User ID must be a number.", quote=True)
        return

    if await db.is_user_banned(target_id):
        try:
            await db.unban_user(target_id)
            await m.reply_text(text=f"`{target_id}`** is Unbanned** ", parse_mode=ParseMode.MARKDOWN, quote=True)
            if not str(target_id).startswith('-100'):
                try:
                    await b.send_message(
                        chat_id=target_id,
                        text="**You have been Unbanned. You can now use the Bot.**",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                except:
                    pass
        except Exception as e:
            await m.reply_text(text=f"**Something went wrong: {e}**", parse_mode=ParseMode.MARKDOWN, quote=True)
    else:
        await m.reply_text(text=f"`{target_id}`** is not Banned** ", parse_mode=ParseMode.MARKDOWN, quote=True)

# ---------------------[ BROADCAST ]---------------------#
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
                    await out.edit_text(f"Broadcast Status\n\ncurrent: {done}\nfailed:{failed}\nsuccess: {success}")
                except:
                    pass
    if broadcast_ids.get(broadcast_id):
        broadcast_ids.pop(broadcast_id)
    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    await asyncio.sleep(3)
    await out.delete()
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
    os.remove('broadcast.txt')

# ---------------------[ DELETE FILE ]---------------------#
@FileStream.on_message(filters.command("del") & filters.private & filters.user(Telegram.OWNER_ID))
async def del_file(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("**Usage:** `/del [File_ID]`", quote=True)
        return

    file_id = m.command[1]
    try:
        file_info = await db.get_file(file_id)
    except FIleNotFound:
        await m.reply_text(
            text=f"**File already deleted or not found.**",
            quote=True
        )
        return
        
    await db.delete_one_file(file_info['_id'])
    await db.count_links(file_info['user_id'], "-")
    await m.reply_text(
        text=f"**File Deleted Successfully!** ",
        quote=True
    )
