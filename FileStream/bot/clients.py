import asyncio
import logging
import re
from os import environ
from ..config import Telegram
from pyrogram import Client
from . import multi_clients, work_loads, FileStream
from FileStream.utils.client_balance import ensure_client_stat


async def clone_primary_handlers(client: Client):
    dispatcher = getattr(FileStream, "dispatcher", None)
    if not dispatcher:
        return

    groups = getattr(dispatcher, "groups", {}) or {}
    for group, handlers in groups.items():
        for handler in handlers:
            client.add_handler(handler, group)


async def initialize_clients():
    tokens = []
    for k, v in environ.items():
        if k.startswith("MULTI_TOKEN"):
            m = re.search(r"\d+", k)
            idx = int(m.group()) if m else 0
            tokens.append((idx, v))
    tokens.sort(key=lambda x: x[0])

    all_tokens = dict((i + 1, t) for i, (_, t) in enumerate(tokens))
    if not all_tokens:
        multi_clients[0] = FileStream
        work_loads[0] = 0
        ensure_client_stat(0)
        print("No additional clients found, using default client")
        return

    multi_clients[0] = FileStream
    work_loads[0] = 0
    ensure_client_stat(0)
    
    async def start_client(client_id, token):
        try:
            if len(token) >= 100:
                session_string=token
                bot_token=None
                print(f'Starting Client - {client_id} Using Session String')
            else:
                session_string=None
                bot_token=token
                print(f'Starting Client - {client_id} Using Bot Token')
            if client_id == len(all_tokens):
                await asyncio.sleep(2)
                print("This will take some time, please wait...")
            client = Client(
                name=str(client_id),
                api_id=Telegram.API_ID,
                api_hash=Telegram.API_HASH,
                bot_token=bot_token,
                sleep_threshold=Telegram.SLEEP_THRESHOLD,
                no_updates=False,
                session_string=session_string,
                in_memory=True,
            )
            await clone_primary_handlers(client)
            await client.start()
            me = await client.get_me()
            client.id = me.id
            client.username = me.username
            client.fname = me.first_name
            work_loads[client_id] = 0
            ensure_client_stat(client_id)
            return client_id, client
        except Exception:
            logging.error(f"Failed starting Client - {client_id} Error:", exc_info=True)
    
    clients = await asyncio.gather(*[start_client(i, token) for i, token in all_tokens.items()])
    multi_clients.update(dict([c for c in clients if c]))

    if len(multi_clients) == 1:
        print("No additional clients were initialized, using default client")
        return

    Telegram.MULTI_CLIENT = True
    print("Multi-Client Mode Enabled")
