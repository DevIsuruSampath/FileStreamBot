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

        value = payload.get("value")
        if isinstance(value, dict):
            data = value.get("data")
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return [x for x in data["items"] if isinstance(x, dict)]

    return []


async def fetch_smartlinks(status: int = 3) -> list[dict[str, Any]]:
    payload = await _request_json("/smart-links.json", params={"status": status})
    return _extract_items(payload)


async def resolve_smartlink_url() -> str | None:
    """Resolve a smartlink URL from Adsterra API with short TTL cache."""
    if not is_api_ready():
        return None

    now = time.time()
    lock = _get_lock()

    async with lock:
        if _cache_smartlink.get("url") and float(_cache_smartlink.get("exp", 0)) > now:
            return str(_cache_smartlink["url"])

        preferred_id = getattr(Telegram, "ADSTERRA_SMARTLINK_ID", None)
        links = await fetch_smartlinks(status=3)
        chosen: dict[str, Any] | None = None

        if preferred_id is not None:
            for item in links:
                try:
                    if int(item.get("id")) == int(preferred_id):
                        chosen = item
                        break
                except Exception:
                    continue

        if chosen is None and links:
            chosen = links[0]

        url = None
        if chosen:
            raw = str(chosen.get("url") or "").strip()
            if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("//"):
                url = raw

        _cache_smartlink["url"] = url
        _cache_smartlink["exp"] = now + 600  # 10 min cache
        return url


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
        "group_by": "date",
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
