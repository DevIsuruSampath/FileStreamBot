from __future__ import annotations

import urllib.parse

from pyrogram import Client

from FileStream.config import Server
from FileStream.utils.client_identity import build_start_link


def build_public_file_url(public_id: str) -> str:
    return f"{Server.URL}gen/{str(public_id or '').strip()}"


def build_public_folder_url(public_id: str) -> str:
    return f"{Server.URL}gfolder/{str(public_id or '').strip()}"


def build_public_stream_url(public_id: str) -> str:
    return f"{Server.URL}dl/{str(public_id or '').strip()}"


def build_public_download_token_path(public_id: str) -> str:
    return f"/get-download-token/{str(public_id or '').strip()}"


def build_public_stream_token_path(public_id: str) -> str:
    return f"/get-stream-token/{str(public_id or '').strip()}"


def build_public_bot_open_link(public_id: str, bot: Client | None = None) -> str:
    return build_start_link(f"open_{str(public_id or '').strip()}", bot)


def build_telegram_share_link(url: str, text: str = "") -> str:
    params = {"url": str(url or "").strip()}
    if str(text or "").strip():
        params["text"] = str(text or "").strip()
    return "https://t.me/share/url?" + urllib.parse.urlencode(params)
