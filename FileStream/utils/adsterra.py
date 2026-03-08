from __future__ import annotations

from typing import List

from FileStream.config import Telegram


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [x.strip() for x in str(value).split(",") if x and x.strip()]


def _valid_url(url: str | None) -> str | None:
    raw = str(url or "").strip()
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("//"):
        return raw
    return None


def get_script_urls() -> List[str]:
    urls: List[str] = []

    # Generic list (existing)
    urls.extend(_split_csv(getattr(Telegram, "ADSTERRA_SCRIPT_URLS", "")))

    # Specific ad formats
    urls.extend(_split_csv(getattr(Telegram, "ADSTERRA_BANNER_SCRIPT_URLS", "")))

    single_slots = [
        getattr(Telegram, "ADSTERRA_POPUNDER_SCRIPT_URL", ""),
        getattr(Telegram, "ADSTERRA_SOCIAL_BAR_SCRIPT_URL", ""),
        getattr(Telegram, "ADSTERRA_NATIVE_BANNER_SCRIPT_URL", ""),
    ]
    urls.extend(str(x or "").strip() for x in single_slots if str(x or "").strip())

    out: List[str] = []
    seen = set()
    for url in urls:
        good = _valid_url(url)
        if not good:
            continue
        if good in seen:
            continue
        seen.add(good)
        out.append(good)
    return out


def get_direct_link() -> str | None:
    link = str(getattr(Telegram, "ADSTERRA_DIRECT_LINK", "") or "").strip()
    if not link:
        return None
    if link.startswith("http://") or link.startswith("https://") or link.startswith("//"):
        return link
    return None


def has_api_fallback() -> bool:
    return bool(
        getattr(Telegram, "ADSTERRA_API_ENABLE", False)
        and str(getattr(Telegram, "ADSTERRA_API_KEY", "") or "").strip()
    )


def is_enabled(web_ads_status: bool) -> bool:
    if not web_ads_status:
        return False

    if not bool(getattr(Telegram, "ADSTERRA_ENABLE", False)):
        return False

    return bool(get_direct_link() or get_script_urls() or has_api_fallback())
