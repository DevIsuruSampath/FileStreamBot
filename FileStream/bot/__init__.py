import os
from ..config import Telegram
from pyrogram import Client

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # FileStream/

if Telegram.SECONDARY:
    plugins=None
    no_updates=True
else:    
    plugins={"root": os.path.join(BASE_DIR, "bot", "plugins")}
    no_updates=None

FileStream = Client(
    name="FileStream",
    api_id=Telegram.API_ID,
    api_hash=Telegram.API_HASH,
    workdir=BASE_DIR,
    plugins=plugins,
    bot_token=Telegram.BOT_TOKEN,
    sleep_threshold=Telegram.SLEEP_THRESHOLD,
    workers=Telegram.WORKERS,
    no_updates=no_updates
)

multi_clients = {}
work_loads = {}

