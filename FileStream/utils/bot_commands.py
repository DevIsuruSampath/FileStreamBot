import html
import logging

from pyrogram import Client
from pyrogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from FileStream.config import Telegram


PUBLIC_COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show help"),
    BotCommand("about", "About this bot"),
    BotCommand("files", "Browse your files"),
    BotCommand("folders", "Browse your folders"),
    BotCommand("donation", "Support the bot with Stars"),
    BotCommand("folder", "Create a folder share"),
    BotCommand("done", "Finish folder mode"),
    BotCommand("cancel", "Cancel folder mode"),
    BotCommand("id", "Show your Telegram ID"),
]

ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand("admin", "Show admin commands"),
    BotCommand("flogstorage", "Switch FLOG storage"),
    BotCommand("urlshortener", "Toggle the shortener"),
    BotCommand("webads", "Toggle web ads"),
    BotCommand("speedtest", "Run a speed test"),
    BotCommand("rm_adult", "Remove adult content"),
]

OWNER_COMMANDS = ADMIN_COMMANDS + [
    BotCommand("status", "Show bot status"),
    BotCommand("ban", "Ban a user"),
    BotCommand("unban", "Unban a user"),
    BotCommand("broadcast", "Broadcast a replied message"),
    BotCommand("del", "Delete a file"),
    BotCommand("linkinfo", "Inspect a public link"),
    BotCommand("revoke_link", "Revoke a public link"),
    BotCommand("regen_link", "Regenerate a public link"),
    BotCommand("expire_link", "Set or clear link expiry"),
]


def _unique_admin_ids():
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


async def register_bot_commands(bot: Client):
    try:
        await bot.set_bot_commands(PUBLIC_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    except Exception as exc:
        logging.warning("Failed to register public bot commands: %s", exc)
        return

    owner_id = int(Telegram.OWNER_ID)
    for admin_id in _unique_admin_ids():
        commands = OWNER_COMMANDS if admin_id == owner_id else ADMIN_COMMANDS
        try:
            await bot.set_bot_commands(commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as exc:
            logging.warning("Failed to register bot commands for admin %s: %s", admin_id, exc)


def build_admin_help_text() -> str:
    shared_admin = [
        ("/admin", "Show this admin command list"),
        ("/flogstorage <main|admin|status>", "Switch or inspect FLOG storage"),
        ("/urlshortener <on|off>", "Enable or disable the shortener"),
        ("/webads <on|off>", "Enable or disable web ads"),
        ("/speedtest", "Run a server speed test"),
        ("/rm_adult <file_id|folder_id>", "Remove adult content manually"),
    ]
    owner_only = [
        ("/status", "Show system and database stats"),
        ("/ban <user_id>", "Ban a user"),
        ("/unban <user_id>", "Unban a user"),
        ("/broadcast", "Reply to a message and broadcast it"),
        ("/del <file_id>", "Delete a file"),
        ("/linkinfo <public_id|file:<id>|folder:<id>>", "Inspect a public link"),
        ("/revoke_link <public_id|file:<id>|folder:<id>>", "Revoke a public link"),
        ("/regen_link <public_id|file:<id>|folder:<id>>", "Generate a new public link"),
        ("/expire_link <public_id|file:<id>|folder:<id>> <now|clear|hours>", "Set or clear link expiry"),
    ]

    def render(lines):
        return "\n".join(
            f"• <code>{html.escape(command)}</code> — {html.escape(description)}"
            for command, description in lines
        )

    return (
        "<b>Admin Commands</b>\n\n"
        "<b>Shared Admin</b>\n"
        f"{render(shared_admin)}\n\n"
        "<b>Owner Only</b>\n"
        f"{render(owner_only)}"
    )
