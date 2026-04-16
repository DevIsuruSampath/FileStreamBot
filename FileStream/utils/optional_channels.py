from __future__ import annotations

import logging

from pyrogram.errors import ChannelInvalid, ChannelPrivate, ChatIdInvalid, PeerIdInvalid


_DISABLED_OPTIONAL_CHANNELS: set[tuple[str, int]] = set()

_INVALID_CHANNEL_MARKERS = (
    "channel_invalid",
    "channel invalid",
    "channel_private",
    "channel private",
    "channel parameter is invalid",
    "chat_id_invalid",
    "chat id invalid",
    "chat not found",
    "peer id invalid",
)


def is_invalid_optional_channel_error(exc: Exception) -> bool:
    if isinstance(exc, (ChannelInvalid, ChannelPrivate, ChatIdInvalid, PeerIdInvalid)):
        return True

    error_text = str(exc or "").lower()
    return any(marker in error_text for marker in _INVALID_CHANNEL_MARKERS)


def optional_channel_available(name: str, channel_id: int | None) -> bool:
    if not channel_id:
        return False
    try:
        key = (str(name), int(channel_id))
    except Exception:
        return False
    return key not in _DISABLED_OPTIONAL_CHANNELS


def disable_optional_channel(name: str, channel_id: int | None, exc: Exception) -> None:
    if not channel_id:
        return

    try:
        key = (str(name), int(channel_id))
    except Exception:
        return

    if key in _DISABLED_OPTIONAL_CHANNELS:
        return

    _DISABLED_OPTIONAL_CHANNELS.add(key)
    logging.warning(
        "Optional channel %s=%s disabled for this runtime: %s",
        name,
        channel_id,
        exc,
    )


async def safe_send_optional_message(bot, name: str, channel_id: int | None, **kwargs):
    if not optional_channel_available(name, channel_id):
        return None

    try:
        return await bot.send_message(chat_id=channel_id, **kwargs)
    except Exception as exc:
        if is_invalid_optional_channel_error(exc):
            disable_optional_channel(name, channel_id, exc)
            return None
        raise
