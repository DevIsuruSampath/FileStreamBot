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
import html
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums.parse_mode import ParseMode

from FileStream.utils.broadcast_helper import send_msg
from FileStream.utils.database import Database
from FileStream.bot import FileStream
from FileStream.server.exceptions import FileNotFound
from FileStream.config import Telegram
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.speedtest import run_speedtest, format_speedtest, MSG_SPEEDTEST_START, MSG_SPEEDTEST_ERROR
from FileStream.utils.file_cleanup import delete_file_entry
from FileStream.utils.public_links import build_public_file_url, build_public_folder_url
from FileStream.utils.bot_commands import build_admin_help_text

speedtest_lock = asyncio.Lock()
_last_speedtest_at = 0
SPEEDTEST_COOLDOWN = 60

db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)
broadcast_ids = {}

# Record Bot Start Time
BOT_START_TIME = time.time()

def _build_admin_ids():
    seen = set()
    admin_ids = []
    for raw_id in [Telegram.OWNER_ID, *(Telegram.AUTH_USERS or [])]:
        try:
            admin_id = int(raw_id)
        except Exception:
            continue
        if admin_id in seen:
            continue
        seen.add(admin_id)
        admin_ids.append(admin_id)
    return admin_ids


ADMIN_IDS = _build_admin_ids()
OWNER_ID = int(Telegram.OWNER_ID)


def _parse_ref(value: str) -> tuple[str | None, str]:
    raw = str(value or "").strip()
    if ":" in raw:
        kind, target = raw.split(":", 1)
        kind = kind.strip().lower()
        if kind in {"file", "folder", "public"}:
            return kind, target.strip()
    return None, raw


def _public_link_url(link: dict) -> str:
    if link.get("type") == "folder":
        return build_public_folder_url(link.get("public_id"))
    return build_public_file_url(link.get("public_id"))


def _public_link_status(link: dict) -> str:
    if link.get("revoked"):
        return "revoked"
    expires_at = link.get("expires_at")
    if expires_at is not None and float(expires_at) <= time.time():
        return "expired"
    return "active"


async def _resolve_link_reference(raw: str) -> tuple[str, str, dict]:
    kind, value = _parse_ref(raw)
    if not value:
        raise FileNotFound

    if kind == "public":
        link = await db.get_public_link(value)
        return link["type"], str(link["target_id"]), link

    if kind == "file":
        file_info = await db.get_file(value)
        link = await db.ensure_public_link_for_file(file_info)
        return "file", str(file_info["_id"]), link

    if kind == "folder":
        folder = await db.get_folder(value)
        link = await db.ensure_public_link_for_folder(folder)
        return "folder", str(folder["_id"]), link

    try:
        link = await db.get_public_link(value)
        return link["type"], str(link["target_id"]), link
    except FileNotFound:
        pass

    try:
        file_info = await db.get_file(value)
        link = await db.ensure_public_link_for_file(file_info)
        return "file", str(file_info["_id"]), link
    except FileNotFound:
        pass

    folder = await db.get_folder(value)
    link = await db.ensure_public_link_for_folder(folder)
    return "folder", str(folder["_id"]), link

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
@FileStream.on_message(filters.command("id") & filters.private)
async def get_id(c: Client, m: Message):
    await m.reply_text(
        f"Your User ID is: `{m.from_user.id}`\nOwner ID in Config: `{Telegram.OWNER_ID}`",
        parse_mode=ParseMode.MARKDOWN,
        quote=True
    )


@FileStream.on_message(filters.command("admin") & filters.private)
async def admin_help(c: Client, m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.reply_text("⚠️ **Access Denied.**", quote=True)
        return
    await m.reply_text(
        build_admin_help_text(),
        parse_mode=ParseMode.HTML,
        quote=True,
        disable_web_page_preview=True,
    )

# ---------------------[ URL SHORTENER TOGGLE COMMAND ]---------------------#
@FileStream.on_message(filters.command(["urlshortener", "ads"]) & filters.private)
async def urlshortener_toggle(c: Client, m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.reply_text(f"⚠️ **Access Denied.**\nYour ID `{m.from_user.id}` is not in `OWNER_ID` or `AUTH_USERS`.", quote=True)
        return

    # /urlshortener (or legacy /ads) -> status
    if len(m.command) < 2:
        status = await db.get_urlshortener_status()
        state = "ON" if status else "OFF"
        await m.reply_text(
            text=(
                f"**URL Shortener is currently:** `{state}`\n"
                "Usage: `/urlshortener on` or `/urlshortener off`"
            ),
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    action = m.command[1].strip().lower()

    if action in {"status", "state"}:
        status = await db.get_urlshortener_status()
        state = "ON" if status else "OFF"
        await m.reply_text(
            text=f"**URL Shortener:** `{state}`",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
        return

    if action == "on":
        await db.update_urlshortener_status(True)
        await m.reply_text(
            text="**✅ URL Shortener has been enabled.**",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
    elif action == "off":
        await db.update_urlshortener_status(False)
        await m.reply_text(
            text="**❌ URL Shortener has been disabled.**",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )
    else:
        await m.reply_text(
            text="Usage: `/urlshortener on` or `/urlshortener off`",
            parse_mode=ParseMode.MARKDOWN,
            quote=True
        )

# ---------------------[ STATUS COMMAND (FIXED) ]---------------------#
@FileStream.on_message(filters.command("status") & filters.private & filters.user(OWNER_ID))
async def sts(c: Client, m: Message):
    # 1. Calculate Uptime
    bot_uptime = get_readable_time(int(time.time() - BOT_START_TIME))
    sys_uptime = get_readable_time(int(time.time() - psutil.boot_time()))

    # 2. CPU Usage
    cpu_usage = psutil.cpu_percent(interval=0.1)
    
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
    
    # 5. Network Usage (FIXED VARIABLE NAMES)
    net_io_counters = psutil.net_io_counters()
    upload = humanbytes(net_io_counters.bytes_sent)
    download = humanbytes(net_io_counters.bytes_recv)

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
@FileStream.on_message(filters.command("speedtest") & filters.private)
async def speedtest_cmd(c: Client, m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.reply_text("⚠️ **Access Denied.**", quote=True)
        return

    global _last_speedtest_at
    now = time.time()
    if now - _last_speedtest_at < SPEEDTEST_COOLDOWN:
        wait = int(SPEEDTEST_COOLDOWN - (now - _last_speedtest_at))
        await m.reply_text(f"Please wait {wait}s before running another speed test.", quote=True)
        return

    if speedtest_lock.locked():
        await m.reply_text("Speedtest already running. Please wait...", quote=True)
        return

    _last_speedtest_at = now

    async with speedtest_lock:
        msg = await m.reply_text(MSG_SPEEDTEST_START, quote=True)
        try:
            result = await run_speedtest(retries=2, delay=3)
            text = format_speedtest(result)
            share_url = result.get("share") if isinstance(result, dict) else None

            if share_url:
                try:
                    await m.reply_photo(share_url, caption=text, quote=True)
                    await msg.delete()
                    return
                except Exception:
                    pass

            await msg.edit_text(text)
        except Exception:
            await msg.edit_text(MSG_SPEEDTEST_ERROR)


@FileStream.on_message(filters.command("ban") & filters.private & filters.user(OWNER_ID))
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
@FileStream.on_message(filters.command("unban") & filters.private & filters.user(OWNER_ID))
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
@FileStream.on_message(filters.command("broadcast") & filters.private & filters.user(OWNER_ID) & filters.reply)
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
    log_file = f"broadcast_{broadcast_id}.txt"
    async with aiofiles.open(log_file, 'w') as broadcast_log_file:
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
    try:
        await out.delete()
    except Exception:
        pass
    if failed == 0:
        await m.reply_text(
            text=f"broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done}, {success} success and {failed} failed.",
            quote=True
        )
    else:
        await m.reply_document(
            document=log_file,
            caption=f"broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done}, {success} success and {failed} failed.",
            quote=True
        )
    if os.path.exists(log_file):
        os.remove(log_file)

# ---------------------[ DELETE FILE ]---------------------#
@FileStream.on_message(filters.command("del") & filters.private & filters.user(OWNER_ID))
async def del_file(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("**Usage:** `/del [File_ID]`", quote=True)
        return

    file_id = m.command[1]
    try:
        file_info = await db.get_file(file_id)
    except FileNotFound:
        await m.reply_text(
            text=f"**File already deleted or not found.**",
            quote=True
        )
        return
        
    await delete_file_entry(db, file_info, bot=c)
    await m.reply_text(
        text=f"**File Deleted Successfully!** ",
        quote=True
    )


@FileStream.on_message(filters.command("linkinfo") & filters.private & filters.user(OWNER_ID))
async def link_info(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("**Usage:** `/linkinfo [public_id|file:<id>|folder:<id>]`", quote=True)
        return

    try:
        link_type, target_id, link = await _resolve_link_reference(m.command[1])
    except FileNotFound:
        await m.reply_text("**Public link or target not found.**", quote=True)
        return

    status = _public_link_status(link)
    expires_at = link.get("expires_at")
    expires_text = (
        datetime.datetime.utcfromtimestamp(float(expires_at)).strftime("%Y-%m-%d %H:%M:%S UTC")
        if expires_at is not None else "Never"
    )
    title = link.get("file_name") or link.get("folder_name") or "N/A"
    safe_title = html.escape(str(title))
    url = _public_link_url(link)

    await m.reply_text(
        text=(
            f"<b>Type:</b> <code>{link_type}</code>\n"
            f"<b>Target:</b> <code>{target_id}</code>\n"
            f"<b>Public ID:</b> <code>{link.get('public_id')}</code>\n"
            f"<b>Status:</b> <code>{status}</code>\n"
            f"<b>Clicks:</b> <code>{int(link.get('click_count', 0))}</code>\n"
            f"<b>Expires:</b> <code>{expires_text}</code>\n"
            f"<b>Name:</b> <code>{safe_title}</code>\n"
            f"<b>URL:</b> <code>{html.escape(url)}</code>"
        ),
        parse_mode=ParseMode.HTML,
        quote=True,
    )


@FileStream.on_message(filters.command("revoke_link") & filters.private & filters.user(OWNER_ID))
async def revoke_link(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("**Usage:** `/revoke_link [public_id|file:<id>|folder:<id>]`", quote=True)
        return

    try:
        link_type, target_id, link = await _resolve_link_reference(m.command[1])
    except FileNotFound:
        await m.reply_text("**Public link or target not found.**", quote=True)
        return

    revoked = await db.revoke_public_link(public_id=link["public_id"])
    if not revoked:
        await m.reply_text("**No active public link found.**", quote=True)
        return

    await m.reply_text(
        text=f"**Revoked public link:** `{revoked['public_id']}`",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
    )


@FileStream.on_message(filters.command("regen_link") & filters.private & filters.user(OWNER_ID))
async def regenerate_link(c: Client, m: Message):
    if len(m.command) < 2:
        await m.reply_text("**Usage:** `/regen_link [public_id|file:<id>|folder:<id>]`", quote=True)
        return

    try:
        link_type, target_id, link = await _resolve_link_reference(m.command[1])
    except FileNotFound:
        await m.reply_text("**Public link or target not found.**", quote=True)
        return

    if link_type == "file":
        file_info = await db.get_file(target_id)
        new_link = await db.regenerate_public_link(
            "file",
            target_id,
            file_name=file_info.get("file_name") or "file",
            file_type=file_info.get("mime_type") or file_info.get("category") or "",
        )
    else:
        folder = await db.get_folder(target_id)
        title = (folder.get("title") or "").strip() or f"Folder {target_id}"
        new_link = await db.regenerate_public_link(
            "folder",
            target_id,
            folder_name=title,
        )

    await m.reply_text(
        text=(
            f"**New public link:** `{new_link['public_id']}`\n"
            f"`{_public_link_url(new_link)}`"
        ),
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
    )


@FileStream.on_message(filters.command("expire_link") & filters.private & filters.user(OWNER_ID))
async def expire_link(c: Client, m: Message):
    if len(m.command) < 3:
        await m.reply_text("**Usage:** `/expire_link [public_id|file:<id>|folder:<id>] [now|clear|hours]`", quote=True)
        return

    try:
        link_type, target_id, link = await _resolve_link_reference(m.command[1])
    except FileNotFound:
        await m.reply_text("**Public link or target not found.**", quote=True)
        return

    action = m.command[2].strip().lower()
    if action == "clear":
        expires_at = None
    elif action == "now":
        expires_at = time.time() - 1
    else:
        try:
            hours = float(action)
        except ValueError:
            await m.reply_text("**Expiry must be `now`, `clear`, or a number of hours.**", quote=True)
            return
        expires_at = time.time() + max(hours, 0) * 3600

    await db.set_public_link_expiry(link["public_id"], expires_at)

    if expires_at is None:
        result_text = "cleared"
    elif expires_at <= time.time():
        result_text = "expired immediately"
    else:
        result_text = datetime.datetime.utcfromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S UTC")

    await m.reply_text(
        text=f"**Expiry updated for:** `{link['public_id']}`\n`{result_text}`",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
    )
