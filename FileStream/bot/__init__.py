import os
from ..config import Telegram
from pyrogram import Client

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # FileStream/
PROJECT_ROOT = os.path.dirname(BASE_DIR)               # project root

if Telegram.SECONDARY:
    plugins=None
    no_updates=True
else:    
    # Use relative plugin path to avoid import issues in pyrogram
    plugins={"root": "FileStream/bot/plugins"}
    no_updates=None

FileStream = Client(
    name="FileStream",
    api_id=Telegram.API_ID,
    api_hash=Telegram.API_HASH,
    workdir=PROJECT_ROOT,
    plugins=plugins,
    bot_token=Telegram.BOT_TOKEN,
    sleep_threshold=Telegram.SLEEP_THRESHOLD,
    workers=Telegram.WORKERS,
    no_updates=no_updates
)

multi_clients = {}
work_loads = {}

