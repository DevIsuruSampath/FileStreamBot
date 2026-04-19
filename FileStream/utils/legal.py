from __future__ import annotations

from FileStream.config import Telegram, Server
from FileStream.utils.client_identity import get_bot_username


POLICY_LAST_UPDATED = "2026-04-19"
_UPDATES_CHANNEL_PLACEHOLDERS = {
    "",
    "telegram",
    "your_updates_channel_username",
    "your updates channel username",
    "updates_channel_username",
}


def build_policy_url(page: str = "legal") -> str:
    slug = "privacy" if str(page or "").strip().lower() == "privacy" else "legal"
    return f"{Server.URL}{slug}"


def build_updates_channel_url() -> str | None:
    channel = str(Telegram.UPDATES_CHANNEL or "").lstrip("@").strip()
    if channel.lower() in _UPDATES_CHANNEL_PLACEHOLDERS:
        return None
    if channel and not channel.lstrip("-").isdigit():
        return f"https://t.me/{channel}"
    return None


def build_bot_legal_text(bot=None) -> str:
    bot_username = get_bot_username(bot)
    owner_id = int(Telegram.OWNER_ID)
    return (
        "<b>⚖️ Legal & Privacy</b>\n\n"
        "<b>Stored data:</b>\n"
        "• Telegram user ID, join date, and link count\n"
        "• File metadata, folders, public IDs, and timestamps\n"
        "• Donation/report records and short-lived web tokens\n\n"
        "<b>File handling:</b>\n"
        "Files stream from Telegram/FLOG storage. The server may keep temporary cache chunks to speed up repeat downloads.\n\n"
        "<b>Web pages:</b>\n"
        "Public pages may set a short-lived session cookie and may load ad scripts when web ads are enabled.\n\n"
        "<b>Rules:</b>\n"
        "Do not upload illegal, infringing, or adult content. Links may be revoked, expired, or removed.\n\n"
        f"<b>Need help?</b> Contact <a href='tg://user?id={owner_id}'>the admin</a>"
        + (f" or use @{bot_username}." if bot_username else ".")
    )


def build_policy_page_context(page: str, *, bot_username: str = "") -> dict:
    selected = "privacy" if str(page or "").strip().lower() == "privacy" else "legal"
    updates_channel_url = build_updates_channel_url()
    updates_channel_name = str(Telegram.UPDATES_CHANNEL or "").lstrip("@").strip() or "our update channel"

    privacy_sections = [
        {
            "id": "privacy-data",
            "title": "What We Store",
            "paragraphs": [
                "This bot stores the minimum data needed to create share links, folders, moderation records, and admin controls.",
            ],
            "bullets": [
                "Telegram user IDs, join dates, and per-user link counters",
                "File metadata such as file name, file size, MIME type, Telegram file identifiers, uploader info, and timestamps",
                "Folder mappings, public share IDs, click counters, report records, and optional donation history",
            ],
        },
        {
            "id": "privacy-storage",
            "title": "How Files Are Stored",
            "paragraphs": [
                "Files are not treated as permanent local origin storage. They are served from Telegram and optional FLOG storage channels.",
                "For performance, the server may keep temporary stream cache chunks on disk. Those cache files are automatically rotated and pruned.",
            ],
            "bullets": [
                "Deleting the backing Telegram/FLOG message can invalidate the share link",
                "Temporary cache is used only to speed up repeated downloads and streams",
            ],
        },
        {
            "id": "privacy-web",
            "title": "Web Sessions, Tokens, and Ads",
            "paragraphs": [
                "Public file pages use short-lived access tokens and a short-lived page session cookie so download and stream actions stay tied to the page that generated them.",
                "When web ads are enabled by the admin, public pages may load third-party advertising scripts. Those providers may collect network and browser data under their own terms.",
            ],
            "bullets": [
                "Short-lived page token and session cookie",
                "Short-lived stream/download tokens",
                "Optional third-party ad scripts on public pages",
            ],
        },
        {
            "id": "privacy-retention",
            "title": "Retention and Contact",
            "paragraphs": [
                "Records can be deleted when a file is revoked, when its Telegram/FLOG backing media disappears, or when an admin removes the content.",
                "If you need help with a privacy or moderation request, contact the bot admin in Telegram.",
            ],
            "bullets": [],
        },
    ]

    legal_sections = [
        {
            "id": "legal-acceptable-use",
            "title": "Acceptable Use",
            "paragraphs": [
                "You are responsible for the content you upload, forward, publish, or share through this bot.",
            ],
            "bullets": [
                "Do not upload illegal, infringing, pirated, or malicious material",
                "Do not upload adult or NSFW content",
                "Do not use the bot to abuse bandwidth, access controls, or third-party services",
            ],
        },
        {
            "id": "legal-links",
            "title": "Links, Availability, and Revocation",
            "paragraphs": [
                "Share links work only while the underlying Telegram/FLOG media and related database records remain valid.",
                "Links may stop working without notice if files are deleted, revoked, expired, reported, or removed by moderation.",
            ],
            "bullets": [
                "Public links are revocable and can expire",
                "Downloads and streams may require page-bound access tokens",
                "Service availability depends on Telegram, the host server, and network conditions",
            ],
        },
        {
            "id": "legal-third-parties",
            "title": "Third-Party Services",
            "paragraphs": [
                "This bot depends on Telegram infrastructure and may optionally use URL shorteners, payment systems, and web advertising providers.",
                "Those services operate under their own terms and privacy policies.",
            ],
            "bullets": [
                "Telegram for bot delivery and media transport",
                "Optional Telegram Stars payments",
                "Optional web ad providers when ads are enabled",
            ],
        },
        {
            "id": "legal-privacy",
            "title": "Privacy Summary",
            "paragraphs": [
                "A dedicated privacy page is available for the exact categories of data used by the bot and its web pages.",
            ],
            "bullets": [
                "User IDs and activity metadata are stored to make the service work",
                "Temporary cache and short-lived tokens are used for performance and protection",
            ],
        },
    ]

    if selected == "privacy":
        sections = privacy_sections
        title = "Privacy Policy"
        subtitle = "What this bot stores, how public pages work, and how temporary cache and ads affect user data."
    else:
        sections = legal_sections + privacy_sections
        title = "Legal & Terms"
        subtitle = "Service rules, link behavior, third-party disclosures, and the matching privacy details for this bot."

    return {
        "selected_page": selected,
        "page_title": title,
        "page_subtitle": subtitle,
        "sections": sections,
        "last_updated": POLICY_LAST_UPDATED,
        "legal_url": build_policy_url("legal"),
        "privacy_url": build_policy_url("privacy"),
        "updates_channel_url": updates_channel_url,
        "updates_channel_name": updates_channel_name,
        "bot_username": str(bot_username or "").lstrip("@"),
    }
