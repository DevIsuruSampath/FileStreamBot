from __future__ import annotations

from FileStream.config import Telegram


def configured_flog_channels() -> dict[str, int]:
    channels: dict[str, int] = {}

    if Telegram.FLOG_CHANNEL:
        channels["main"] = int(Telegram.FLOG_CHANNEL)

    if Telegram.ADMIN_FLOG_CHANNEL:
        admin_channel = int(Telegram.ADMIN_FLOG_CHANNEL)
        if admin_channel != channels.get("main"):
            channels["admin"] = admin_channel

    return channels


def has_configured_flog_channels() -> bool:
    return bool(configured_flog_channels())


def normalize_flog_storage_mode(mode: str | None) -> str:
    return "admin" if str(mode or "").strip().lower() == "admin" else "main"


def optional_channel_name_for_mode(mode: str | None) -> str:
    return "ADMIN_FLOG_CHANNEL" if normalize_flog_storage_mode(mode) == "admin" else "FLOG_CHANNEL"


def resolve_flog_mode_for_channel_id(channel_id: int | None) -> str:
    if not channel_id:
        return "main"

    try:
        normalized = int(channel_id)
    except Exception:
        return "main"

    for mode, configured_id in configured_flog_channels().items():
        if int(configured_id) == normalized:
            return mode

    if Telegram.ADMIN_FLOG_CHANNEL and normalized == int(Telegram.ADMIN_FLOG_CHANNEL):
        return "admin"

    return "main"


def optional_channel_name_for_id(channel_id: int | None) -> str:
    return optional_channel_name_for_mode(resolve_flog_mode_for_channel_id(channel_id))


def resolve_file_flog_channel_id(file_info: dict | None) -> int | None:
    if not file_info:
        return int(Telegram.FLOG_CHANNEL) if Telegram.FLOG_CHANNEL else None

    raw = file_info.get("flog_channel_id")
    try:
        if raw not in (None, ""):
            return int(raw)
    except Exception:
        pass

    return int(Telegram.FLOG_CHANNEL) if Telegram.FLOG_CHANNEL else None


def resolve_file_flog_mode(file_info: dict | None) -> str:
    return resolve_flog_mode_for_channel_id(resolve_file_flog_channel_id(file_info))


async def resolve_active_flog_target(db) -> tuple[str, str, int | None]:
    channels = configured_flog_channels()
    mode = normalize_flog_storage_mode(await db.get_flog_storage_mode())

    if mode == "admin" and channels.get("admin"):
        return "admin", "ADMIN_FLOG_CHANNEL", int(channels["admin"])

    if channels.get("main"):
        return "main", "FLOG_CHANNEL", int(channels["main"])

    if channels.get("admin"):
        return "admin", "ADMIN_FLOG_CHANNEL", int(channels["admin"])

    return mode, optional_channel_name_for_mode(mode), None

