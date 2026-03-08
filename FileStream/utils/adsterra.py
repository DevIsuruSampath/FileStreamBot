from __future__ import annotations

from typing import List

from FileStream.config import Telegram


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [x.strip() for x in str(value).split(",") if x and x.strip()]


def get_script_urls() -> List[str]:
    urls = _split_csv(getattr(Telegram, "ADSTERRA_SCRIPT_URLS", ""))
    out: List[str] = []
    for url in urls:
        if url.startswith("http://") or url.startswith("https://") or url.startswith("//"):
            out.append(url)
    return out


def get_direct_link() -> str | None:
    link = str(getattr(Telegram, "ADSTERRA_DIRECT_LINK", "") or "").strip()
    if not link:
        return None
    if link.startswith("http://") or link.startswith("https://") or link.startswith("//"):
        return link
    return None


def is_enabled(ads_status: bool) -> bool:
    if not ads_status:
        return False

    if not bool(getattr(Telegram, "ADSTERRA_ENABLE", False)):
        return False

    return bool(get_direct_link() or get_script_urls())
