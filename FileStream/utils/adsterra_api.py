from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from typing import Any

import aiohttp

from FileStream.config import Telegram


class AdsterraAPIError(Exception):
    pass


_cache_smartlink: dict[str, Any] = {"url": None, "exp": 0.0}
_cache_inventory: dict[str, Any] = {"value": None, "exp": 0.0}
_cache_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


def is_api_ready() -> bool:
    return bool(
        getattr(Telegram, "ADSTERRA_API_ENABLE", False)
        and str(getattr(Telegram, "ADSTERRA_API_KEY", "") or "").strip()
    )


def _base_url() -> str:
    base = str(getattr(Telegram, "ADSTERRA_API_BASE", "") or "").strip()
    if not base:
        base = "https://api3.adsterratools.com/publisher"
    return base.rstrip("/")


def _headers() -> dict[str, str]:
    key = str(getattr(Telegram, "ADSTERRA_API_KEY", "") or "").strip()
    return {
        "X-API-Key": key,
        "Accept": "application/json",
        "User-Agent": "FileStreamBot-Adsterra/1.0",
    }


async def _request_json(path: str, params: dict[str, Any] | None = None) -> Any:
    if not is_api_ready():
        raise AdsterraAPIError("Adsterra API is not configured")

    url = f"{_base_url()}{path}"
    timeout = aiohttp.ClientTimeout(total=12)

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=_headers()) as session:
            async with session.get(url, params=params) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise AdsterraAPIError(f"Adsterra API error {resp.status}: {text[:300]}")
                try:
                    return await resp.json(content_type=None)
                except Exception:
                    raise AdsterraAPIError("Adsterra API returned non-JSON response")
    except asyncio.TimeoutError:
        raise AdsterraAPIError("Adsterra API timeout")
    except aiohttp.ClientError as e:
        raise AdsterraAPIError(f"Adsterra API request failed: {e}")


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]

        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [x for x in data["items"] if isinstance(x, dict)]

        value = payload.get("value")
        if isinstance(value, dict):
            data = value.get("data")
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return [x for x in data["items"] if isinstance(x, dict)]

    return []


async def fetch_smartlinks(status: int | None = 3, traffic_type: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if status is not None:
        params["status"] = int(status)
    if traffic_type is not None:
        params["traffic_type"] = int(traffic_type)

    payload = await _request_json("/smart-links.json", params=params or None)
    return _extract_items(payload)


async def fetch_placements() -> list[dict[str, Any]]:
    payload = await _request_json("/placements.json")
    return _extract_items(payload)


def _valid_url(value: Any) -> str | None:
    raw = str(value or "").strip()
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("//"):
        return raw
    return None


def _pick_by_id(items: list[dict[str, Any]], preferred_id: int | None) -> dict[str, Any] | None:
    if preferred_id is None:
        return None
    for item in items:
        try:
            if int(item.get("id")) == int(preferred_id):
                return item
        except Exception:
            continue
    return None


def _is_adult_smartlink(item: dict[str, Any]) -> bool:
    traffic = item.get("traffic_type")

    # Numeric forms from API docs: 1=mainstream, 2=adult
    try:
        if traffic is not None and int(traffic) == 2:
            return True
    except Exception:
        pass

    txt = str(traffic or "").strip().lower()
    return "adult" in txt


def _is_adult_text(text: str) -> bool:
    t = (text or "").lower()
    signals = ["adult", "xxx", "porn", "sex", "erotic", "18+"]
    return any(x in t for x in signals)


def _filter_non_adult_smartlinks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if getattr(Telegram, "ADSTERRA_ALLOW_ADULT", False):
        return items
    return [x for x in items if not _is_adult_smartlink(x)]


def _filter_non_adult_placements(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if getattr(Telegram, "ADSTERRA_ALLOW_ADULT", False):
        return items

    out: list[dict[str, Any]] = []
    for p in items:
        title = str(p.get("title") or "")
        alias = str(p.get("alias") or "")
        if _is_adult_text(title) or _is_adult_text(alias):
            continue
        out.append(p)
    return out


def _placement_format(item: dict[str, Any]) -> str:
    text = f"{item.get('title', '')} {item.get('alias', '')}".lower()

    if any(k in text for k in ("popunder", "pop-under", "pop under")):
        return "popunder"
    if any(k in text for k in ("socialbar", "social bar")):
        return "social_bar"
    if "native" in text:
        return "native_banner"
    if "banner" in text:
        return "banner"

    return "generic"


def _dedupe_keep_order(urls: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _build_inventory(placements: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[str]] = {
        "popunder": [],
        "social_bar": [],
        "native_banner": [],
        "banner": [],
        "generic": [],
    }

    for item in placements:
        url = _valid_url(item.get("direct_url"))
        if not url:
            continue

        kind = _placement_format(item)
        buckets[kind].append(url)
        buckets["generic"].append(url)

    for k in list(buckets.keys()):
        buckets[k] = _dedupe_keep_order(buckets[k])

    return {
        "popunder": buckets["popunder"],
        "social_bar": buckets["social_bar"],
        "native_banner": buckets["native_banner"],
        "banner": buckets["banner"],
        "generic": buckets["generic"],
        "counts": {
            "popunder": len(buckets["popunder"]),
            "social_bar": len(buckets["social_bar"]),
            "native_banner": len(buckets["native_banner"]),
            "banner": len(buckets["banner"]),
            "generic": len(buckets["generic"]),
        },
    }


async def fetch_placement_inventory() -> dict[str, Any] | None:
    if not is_api_ready():
        return None

    now = time.time()
    lock = _get_lock()

    async with lock:
        if _cache_inventory.get("value") is not None and float(_cache_inventory.get("exp", 0)) > now:
            return dict(_cache_inventory["value"])

        placements = await fetch_placements()
        placements = _filter_non_adult_placements(placements)
        inventory = _build_inventory(placements)

        _cache_inventory["value"] = dict(inventory)
        _cache_inventory["exp"] = now + 300  # 5 min cache
        return inventory


async def resolve_smartlink_url() -> str | None:
    """Resolve smartlink URL (mainstream by default)."""
    if not is_api_ready():
        return None

    now = time.time()
    lock = _get_lock()

    async with lock:
        if _cache_smartlink.get("url") and float(_cache_smartlink.get("exp", 0)) > now:
            return str(_cache_smartlink["url"])

        preferred_id = getattr(Telegram, "ADSTERRA_SMARTLINK_ID", None)
        allow_adult = bool(getattr(Telegram, "ADSTERRA_ALLOW_ADULT", False))

        url: str | None = None

        links_active = await fetch_smartlinks(status=3, traffic_type=None if allow_adult else 1)
        links_active = _filter_non_adult_smartlinks(links_active)
        chosen = _pick_by_id(links_active, preferred_id) or (links_active[0] if links_active else None)
        if chosen:
            url = _valid_url(chosen.get("url"))

        if not url:
            links_any = await fetch_smartlinks(status=None, traffic_type=None if allow_adult else 1)
            links_any = _filter_non_adult_smartlinks(links_any)
            chosen_any = _pick_by_id(links_any, preferred_id) or (links_any[0] if links_any else None)
            if chosen_any:
                url = _valid_url(chosen_any.get("url"))

        _cache_smartlink["url"] = url
        _cache_smartlink["exp"] = now + 600  # 10 min cache
        return url


async def resolve_action_ad_urls(max_urls: int = 8) -> list[str]:
    """Return prioritized ad URLs for click actions.

    Priority:
    1) SmartLink
    2) Popunder placements
    3) Social bar placements
    4) Native banner placements
    5) Banner placements
    6) Generic placements
    """
    if not is_api_ready():
        return []

    urls: list[str] = []

    smart = await resolve_smartlink_url()
    if smart:
        urls.append(smart)

    inv = await fetch_placement_inventory()
    if inv:
        urls.extend(inv.get("popunder", []))
        urls.extend(inv.get("social_bar", []))
        urls.extend(inv.get("native_banner", []))
        urls.extend(inv.get("banner", []))
        urls.extend(inv.get("generic", []))

    urls = _dedupe_keep_order([u for u in urls if _valid_url(u)])
    return urls[: max(1, int(max_urls or 8))]


async def fetch_stats_summary(days: int | None = None) -> dict[str, Any] | None:
    if not is_api_ready():
        return None

    d = days or getattr(Telegram, "ADSTERRA_STATS_DAYS", 7) or 7
    try:
        d = max(1, min(int(d), 31))
    except Exception:
        d = 7

    end = date.today()
    start = end - timedelta(days=d - 1)

    params = {
        "start_date": start.isoformat(),
        "finish_date": end.isoformat(),
        "group_by": ["date"],
    }

    payload = await _request_json("/stats.json", params=params)
    items = _extract_items(payload)

    impressions = 0
    clicks = 0
    revenue = 0.0

    for row in items:
        try:
            impressions += int(row.get("impression") or 0)
        except Exception:
            pass
        try:
            clicks += int(row.get("clicks") or 0)
        except Exception:
            pass
        try:
            revenue += float(row.get("revenue") or 0)
        except Exception:
            pass

    return {
        "start_date": start.isoformat(),
        "finish_date": end.isoformat(),
        "days": d,
        "impressions": impressions,
        "clicks": clicks,
        "revenue": round(revenue, 4),
        "rows": len(items),
    }
