import datetime
import html
import secrets

from pyrogram import Client, filters
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from FileStream.bot import FileStream
from FileStream.config import Telegram
from FileStream.utils.bot_utils import verify_user
from FileStream.utils.client_identity import get_bot_name
from FileStream.utils.database import Database


db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

MIN_DONATION_STARS = 50
MAX_DONATION_STARS = 10000
DONATION_PRESETS = (50, 100, 250)
DONATION_TITLE = "Support Quick Files Stream"
DONATION_DESCRIPTION = "Your donation helps keep the servers running."

pending_custom_amounts: dict[int, dict] = {}


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"{amount} ⭐", callback_data=f"donate:amount:{amount}") for amount in DONATION_PRESETS],
            [InlineKeyboardButton("Custom Amount", callback_data="donate:custom")],
            [
                InlineKeyboardButton("History", callback_data="donate:history"),
                InlineKeyboardButton("Back", callback_data="home"),
            ],
        ]
    )


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="donate:menu")]])


def _donation_text(bot: Client, note: str | None = None) -> str:
    bot_name = html.escape(get_bot_name(bot) or "this bot")
    lines = [
        f"<b>Support {bot_name}</b>",
        "",
        "<i>Your donations help keep the servers running and the bot online.</i>",
        "",
        f"Choose a Telegram Stars amount below or send a custom amount from <code>{MIN_DONATION_STARS}</code> to <code>{MAX_DONATION_STARS}</code> Stars.",
    ]
    if note:
        lines.extend(["", html.escape(note)])
    return "\n".join(lines)


def _custom_amount_text() -> str:
    return (
        "<b>Custom Donation</b>\n\n"
        f"Send a whole number between <code>{MIN_DONATION_STARS}</code> and <code>{MAX_DONATION_STARS}</code> Stars.\n\n"
        "<i>Example:</i> <code>500</code>"
    )


async def _history_text(user_id: int) -> str:
    stats = await db.get_user_donation_stats(user_id)
    donations = await db.get_user_donations(user_id, limit=10)

    lines = [
        "<b>Your Donation History</b>",
        "",
        f"<b>Total Donations:</b> <code>{int(stats.get('count', 0))}</code>",
        f"<b>Total Stars:</b> <code>{int(stats.get('total_stars', 0))} ⭐</code>",
        "",
    ]

    if not donations:
        lines.append("<i>No donations yet.</i>")
        return "\n".join(lines)

    lines.append("<b>Recent Payments</b>")
    for index, item in enumerate(donations, start=1):
        paid_at = item.get("paid_at")
        if isinstance(paid_at, (int, float)):
            paid_on = datetime.datetime.utcfromtimestamp(paid_at).strftime("%Y-%m-%d %H:%M UTC")
        else:
            paid_on = "Unknown time"
        amount = int(item.get("amount", 0) or 0)
        lines.append(f"{index}. <code>{amount} ⭐</code> — {html.escape(paid_on)}")

    return "\n".join(lines)


async def _send_invoice(
    bot: Client,
    *,
    chat_id: int,
    user_id: int,
    amount: int,
    reply_to_message_id: int | None = None,
):
    payload = f"donation:{user_id}:{amount}:{secrets.token_hex(4)}"
    return await bot.send_invoice(
        chat_id=chat_id,
        title=DONATION_TITLE,
        description=DONATION_DESCRIPTION,
        currency="XTR",
        prices=[LabeledPrice(label=f"{amount} Telegram Stars", amount=int(amount))],
        provider="",
        payload=payload,
        reply_to_message_id=reply_to_message_id,
    )


def _parse_payload(payload: str) -> tuple[int, int] | None:
    raw = str(payload or "").strip()
    parts = raw.split(":")
    if len(parts) != 4 or parts[0] != "donation":
        return None
    try:
        user_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        return None
    return user_id, amount


def _is_custom_amount_valid(amount: int) -> bool:
    return MIN_DONATION_STARS <= int(amount) <= MAX_DONATION_STARS


async def _show_menu(message: Message, bot: Client, note: str | None = None):
    await message.reply_text(
        _donation_text(bot, note=note),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=_main_keyboard(),
        quote=True,
    )


async def _edit_message_text(message: Message, text: str, reply_markup: InlineKeyboardMarkup):
    await message.edit_text(
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


async def open_donation_menu(message: Message, bot: Client, note: str | None = None, *, edit: bool = False):
    if edit:
        await _edit_message_text(message, _donation_text(bot, note=note), _main_keyboard())
        return
    await _show_menu(message, bot, note=note)


@FileStream.on_message(filters.command("donation") & filters.private)
async def donation_command(bot: Client, message: Message):
    if not await verify_user(bot, message):
        return
    pending_custom_amounts.pop(message.from_user.id, None)
    await open_donation_menu(message, bot)


@FileStream.on_callback_query(filters.regex(r"^donate:"))
async def donation_callbacks(bot: Client, query: CallbackQuery):
    if not query.from_user or not query.message:
        return

    user_id = int(query.from_user.id)
    if await db.is_user_banned(user_id):
        await query.answer("Access denied.", show_alert=True)
        return

    if Telegram.AUTH_USERS and user_id != int(Telegram.OWNER_ID) and user_id not in Telegram.AUTH_USERS:
        await query.answer("Unauthorized.", show_alert=True)
        return

    data = str(query.data or "")
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"

    if action == "menu":
        pending_custom_amounts.pop(user_id, None)
        await open_donation_menu(query.message, bot, edit=True)
        await query.answer()
        return

    if action == "custom":
        pending_custom_amounts[user_id] = {
            "chat_id": query.message.chat.id,
            "message_id": query.message.id,
        }
        await _edit_message_text(query.message, _custom_amount_text(), _back_keyboard())
        await query.answer()
        return

    if action == "history":
        pending_custom_amounts.pop(user_id, None)
        await _edit_message_text(query.message, await _history_text(user_id), _back_keyboard())
        await query.answer()
        return

    if action == "amount":
        pending_custom_amounts.pop(user_id, None)
        if len(parts) < 3:
            await query.answer("Invalid amount.", show_alert=True)
            return
        try:
            amount = int(parts[2])
        except ValueError:
            await query.answer("Invalid amount.", show_alert=True)
            return

        if not _is_custom_amount_valid(amount):
            await query.answer("Amount out of range.", show_alert=True)
            return

        try:
            await _send_invoice(
                bot,
                chat_id=query.message.chat.id,
                user_id=user_id,
                amount=amount,
                reply_to_message_id=query.message.id,
            )
        except Exception:
            await query.answer("Failed to create the Stars invoice.", show_alert=True)
            return

        await query.answer("Invoice sent.")
        await _edit_message_text(
            query.message,
            _donation_text(bot, note=f"Invoice created for {amount} Stars."),
            _main_keyboard(),
        )
        return

    await query.answer("Invalid action.", show_alert=True)


@FileStream.on_message(filters.private & filters.text, group=4)
async def donation_custom_amount_input(bot: Client, message: Message):
    if not getattr(message, "from_user", None):
        return

    state = pending_custom_amounts.get(message.from_user.id)
    if not state:
        return

    if not await verify_user(bot, message):
        return

    text = (message.text or "").strip()
    if not text:
        return

    if text.startswith("/"):
        pending_custom_amounts.pop(message.from_user.id, None)
        return

    try:
        amount = int(text)
    except ValueError:
        await message.reply_text(
            f"Send a whole number between {MIN_DONATION_STARS} and {MAX_DONATION_STARS} Stars.",
            quote=True,
            reply_markup=_back_keyboard(),
        )
        return

    if not _is_custom_amount_valid(amount):
        await message.reply_text(
            f"Amount must be between {MIN_DONATION_STARS} and {MAX_DONATION_STARS} Stars.",
            quote=True,
            reply_markup=_back_keyboard(),
        )
        return

    pending_custom_amounts.pop(message.from_user.id, None)

    try:
        await _send_invoice(
            bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            amount=amount,
            reply_to_message_id=message.id,
        )
    except Exception:
        await message.reply_text("Failed to create the Stars invoice. Try again in a moment.", quote=True)
        return

    try:
        await bot.edit_message_text(
            chat_id=state["chat_id"],
            message_id=state["message_id"],
            text=_donation_text(bot, note=f"Invoice created for {amount} Stars."),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_main_keyboard(),
        )
    except Exception:
        pass

    await message.reply_text(f"Stars invoice created for {amount} ⭐", quote=True)


@FileStream.on_pre_checkout_query()
async def donation_pre_checkout(bot: Client, query: PreCheckoutQuery):
    payload_data = _parse_payload(query.payload)
    if payload_data is None:
        await query.answer(success=False, error="Invalid donation request.")
        return

    expected_user_id, expected_amount = payload_data
    if int(query.from_user.id) != expected_user_id:
        await query.answer(success=False, error="This invoice belongs to another user.")
        return

    if query.currency != "XTR":
        await query.answer(success=False, error="Unsupported currency.")
        return

    if int(query.total_amount) != expected_amount or not _is_custom_amount_valid(expected_amount):
        await query.answer(success=False, error="Donation amount is invalid.")
        return

    await query.answer(success=True)


@FileStream.on_message(filters.private & filters.successful_payment)
async def donation_success(bot: Client, message: Message):
    if not getattr(message, "successful_payment", None) or not getattr(message, "from_user", None):
        return

    payment = message.successful_payment
    payload_data = _parse_payload(payment.payload)
    amount = int(payment.total_amount or 0)
    user_id = int(message.from_user.id)

    if payload_data is not None:
        payload_user_id, payload_amount = payload_data
        if payload_user_id == user_id:
            amount = int(payload_amount)

    await db.record_donation(
        user_id=user_id,
        amount=amount,
        currency=payment.currency,
        payload=payment.payload,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        provider_payment_charge_id=payment.provider_payment_charge_id,
        first_name=message.from_user.first_name or "",
        username=message.from_user.username or "",
    )

    stats = await db.get_user_donation_stats(user_id)
    await message.reply_text(
        (
            "<b>Thank you for your donation.</b>\n\n"
            f"Received: <code>{amount} ⭐</code>\n"
            f"Your total support: <code>{int(stats.get('total_stars', 0))} ⭐</code>\n"
            f"Payments made: <code>{int(stats.get('count', 0))}</code>"
        ),
        parse_mode=ParseMode.HTML,
        quote=True,
        disable_web_page_preview=True,
        reply_markup=_main_keyboard(),
    )
