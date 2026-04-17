import sys
import asyncio
import logging
import traceback
import logging.handlers as handlers
from FileStream.config import Telegram, Server
from aiohttp import web
from pyrogram import idle
from pyrogram.errors import FloodWait

from FileStream.bot import FileStream, multi_clients
from FileStream.server import web_server
from FileStream.bot.clients import initialize_clients
from FileStream.utils.bot_commands import register_bot_commands
from FileStream.utils.database import Database
from FileStream.utils.flog_sync import reconcile_flog_storage, start_flog_sync_task, stop_flog_sync_task
from FileStream.utils.optional_channels import warm_optional_channel_peer

logging.basicConfig(
    level=logging.INFO,
    datefmt="%d/%m/%Y %H:%M:%S",
    format='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(stream=sys.stdout),
              handlers.RotatingFileHandler("streambot.log", mode="a", maxBytes=104857600, backupCount=2, encoding="utf-8")],)

logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("aiohttp.web").setLevel(logging.ERROR)

server = web.AppRunner(web_server())
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

loop = asyncio.get_event_loop()

async def _sleep_with_progress(total_seconds: int):
    remaining = max(int(total_seconds), 0)
    while remaining > 0:
        step = 60 if remaining > 60 else remaining
        await asyncio.sleep(step)
        remaining -= step
        if remaining > 0:
            print(f"Startup FloodWait remaining: {remaining}s")


async def start_services():
    print()
    if Telegram.SECONDARY:
        print("------------------ Starting as Secondary Server ------------------")
    else:
        print("------------------- Starting as Primary Server -------------------")

    print()
    print("--------------------- Initializing Web Server ---------------------")
    await db.ensure_indexes()
    await server.setup()
    await web.TCPSite(server, Server.BIND_ADDRESS, Server.PORT).start()
    print("------------------------------ DONE ------------------------------")

    print()
    print("-------------------- Initializing Telegram Bot --------------------")

    while True:
        try:
            await FileStream.start()
            break
        except FloodWait as e:
            wait_for = int(getattr(e, "value", 0)) + 1
            mins = wait_for // 60
            print(f"FloodWait during startup: sleeping {wait_for}s (~{mins}m)")
            await _sleep_with_progress(wait_for)

    bot_info = await FileStream.get_me()
    FileStream.id = bot_info.id
    FileStream.username = bot_info.username
    FileStream.fname = bot_info.first_name
    await warm_optional_channel_peer(FileStream, "FLOG_CHANNEL", Telegram.FLOG_CHANNEL)
    await warm_optional_channel_peer(FileStream, "ULOG_CHANNEL", Telegram.ULOG_CHANNEL)
    await register_bot_commands(FileStream)
    print("------------------------------ DONE ------------------------------")

    print()
    print("---------------------- Initializing Clients ----------------------")
    await initialize_clients()
    for client in multi_clients.values():
        await warm_optional_channel_peer(client, "FLOG_CHANNEL", Telegram.FLOG_CHANNEL)
    await reconcile_flog_storage(FileStream, force=True)
    start_flog_sync_task(FileStream)
    print("------------------------------ DONE ------------------------------")

    print()
    print("------------------------- Service Started -------------------------")
    print("                        bot =>> {}".format(bot_info.first_name))
    if bot_info.dc_id:
        print("                        DC ID =>> {}".format(str(bot_info.dc_id)))
    print(" URL =>> {}".format(Server.URL))
    print("------------------------------------------------------------------")
    await idle()

async def cleanup():
    try:
        await stop_flog_sync_task()
    except Exception:
        pass

    try:
        await server.cleanup()
    except Exception:
        pass

    try:
        if FileStream.is_connected:
            await FileStream.stop()
    except Exception:
        pass

if __name__ == "__main__":
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    except Exception as err:
        logging.error(traceback.format_exc())
    finally:
        try:
            loop.run_until_complete(cleanup())
        except Exception:
            pass
        loop.stop()
        print("------------------------ Stopped Services ------------------------")
