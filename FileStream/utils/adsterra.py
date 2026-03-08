from __future__ import annotations

from typing import Any, List

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


def _slot(key: str | None, invoke_url: str | None, width: int, height: int) -> dict[str, Any] | None:
    k = str(key or "").strip()
    u = _valid_url(invoke_url)
    if not k or not u:
        return None

    return {
        "key": k,
        "invoke_url": u,
        "width": int(width),
        "height": int(height),
        "format": "iframe",
    }


def get_responsive_banner_slots() -> dict[str, list[dict[str, Any]]]:
    """Desktop: 728x90 + 300x250; Mobile: 320x50 + 300x250."""
    slot_300 = _slot(
        getattr(Telegram, "ADSTERRA_BANNER_300X250_KEY", ""),
        getattr(Telegram, "ADSTERRA_BANNER_300X250_INVOKE_URL", ""),
        300,
        250,
    )
    slot_728 = _slot(
        getattr(Telegram, "ADSTERRA_BANNER_728X90_KEY", ""),
        getattr(Telegram, "ADSTERRA_BANNER_728X90_INVOKE_URL", ""),
        728,
        90,
    )
    slot_320 = _slot(
        getattr(Telegram, "ADSTERRA_BANNER_320X50_KEY", ""),
        getattr(Telegram, "ADSTERRA_BANNER_320X50_INVOKE_URL", ""),
        320,
        50,
    )

    desktop: list[dict[str, Any]] = []
    mobile: list[dict[str, Any]] = []

    if slot_728:
        desktop.append(slot_728)
    if slot_300:
        desktop.append(slot_300)

    if slot_320:
        mobile.append(slot_320)
    if slot_300:
        mobile.append(slot_300)

    return {
        "desktop": desktop,
        "mobile": mobile,
    }


def has_api_fallback() -> bool:
    return bool(
        getattr(Telegram, "ADSTERRA_API_ENABLE", False)
        and str(getattr(Telegram, "ADSTERRA_API_KEY", "") or "").strip()
    )


def has_responsive_banners() -> bool:
    slots = get_responsive_banner_slots()
    return bool(slots.get("desktop") or slots.get("mobile"))


def is_enabled(web_ads_status: bool) -> bool:
    if not web_ads_status:
        return False

    if not bool(getattr(Telegram, "ADSTERRA_ENABLE", False)):
        return False

    return bool(get_direct_link() or get_script_urls() or has_responsive_banners() or has_api_fallback())
