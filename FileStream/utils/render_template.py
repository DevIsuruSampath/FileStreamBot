import os
import re
import json
import aiohttp
import jinja2
import urllib.parse
from FileStream.config import Telegram, Server
from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.category import detect_category
from FileStream.utils.adsterra import is_enabled as adsterra_is_enabled, get_direct_link, get_script_urls
from FileStream.utils.adsterra_api import resolve_ad_bundle
from FileStream.server.exceptions import FileNotFound

env = jinja2.Environment(autoescape=True)
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)


_NAT_NUM_RE = re.compile(r"(\d+)")
_SERIES_RE_1 = re.compile(r"[sS](\d{1,2})[\s._-]*[eE](\d{1,3})")
_SERIES_RE_2 = re.compile(r"\b(\d{1,2})x(\d{1,3})\b", re.IGNORECASE)
_EPISODE_ONLY_RE = re.compile(r"\b(?:ep|episode)[\s._-]*(\d{1,3})\b", re.IGNORECASE)


def _natural_key(text: str):
    cleaned = str(text or "").replace("_", " ").strip().lower()
    parts = _NAT_NUM_RE.split(cleaned)
    key = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def _series_episode_key(name: str):
    base = os.path.splitext(str(name or ""))[0]

    m = _SERIES_RE_1.search(base)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = _SERIES_RE_2.search(base)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = _EPISODE_ONLY_RE.search(base)
    if m:
        return 0, int(m.group(1))

    return None


def _folder_sort_key(item: dict):
    raw_name = item.get("_sort_name") or item.get("name") or ""
    category = str(item.get("category") or "").lower()

    if category in {"tv-series", "anime"}:
        series_key = _series_episode_key(raw_name)
        if series_key:
            season, episode = series_key
            return (0, season, episode, _natural_key(raw_name))

    return (1, _natural_key(raw_name))


async def render_page(db_id):
    file_data=await db.get_file(db_id)
    src = urllib.parse.urljoin(Server.URL, f'dl/{file_data["_id"]}')
    file_size = humanbytes(file_data.get('file_size') or 0)
    raw_name = (file_data.get('file_name') or 'file')
    file_name = raw_name.replace("_", " ")
    file_name = file_name.replace("\n", " ").replace("\r", " ")
    if len(file_name) > 150:
        file_name = file_name[:150] + "…"

    base_dir = os.path.dirname(os.path.dirname(__file__))  # FileStream/
    mime_type = (file_data.get('mime_type') or '').lower()
    primary = mime_type.split('/')[0].strip() if mime_type else ""
    ext = os.path.splitext(raw_name)[1].lower()
    video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
    audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}

    category = file_data.get("category") or detect_category(file_name=raw_name, mime_type=mime_type, file_ext=ext)
    uploader = (file_data.get("uploader") or "Unknown uploader").replace("\n", " ").replace("\r", " ")
    if len(uploader) > 80:
        uploader = uploader[:80] + "…"

    message_id = file_data.get("message_id")

    is_audio = primary == "audio" or ext in audio_ext
    if primary in ("video", "audio") or ext in video_ext or ext in audio_ext:
        template_file = os.path.join(base_dir, "template", "play.html")
    else:
        template_file = os.path.join(base_dir, "template", "dl.html")

    # Fallback to Content-Length when size is missing/zero
    if not file_data.get('file_size'):
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.head(src) as u:
                    length = u.headers.get('Content-Length')
                    file_size = humanbytes(int(length)) if length else file_size
        except Exception:
            pass

    with open(template_file, encoding="utf-8") as f:
        template = env.from_string(f.read())

    resolved_mime = mime_type or ("audio/mpeg" if is_audio else "video/mp4")

    updates_channel = (Telegram.UPDATES_CHANNEL or "").lstrip("@").strip()
    updates_url = f"https://t.me/{updates_channel}" if updates_channel else None

    report_url = None
    if getattr(FileStream, "username", None):
        report_url = f"https://t.me/{FileStream.username}?start=report_file_{db_id}"

    web_ads_status = await db.get_web_ads_status()
    adsterra_enabled = adsterra_is_enabled(web_ads_status)
    adsterra_script_urls = get_script_urls() if adsterra_enabled else []

    adsterra_action_urls = []
    adsterra_format_urls = {
        "smartlink": None,
        "popunder": None,
        "social_bar": None,
        "native_banner": None,
        "banner": None,
    }

    if adsterra_enabled:
        direct = get_direct_link()
        if direct:
            adsterra_action_urls.append(direct)
            adsterra_format_urls["smartlink"] = direct

        try:
            bundle = await resolve_ad_bundle(max_urls=8)
            for u in bundle.get("action_urls", []):
                if u and u not in adsterra_action_urls:
                    adsterra_action_urls.append(u)

            fmt = bundle.get("format_urls") or {}
            for k in adsterra_format_urls.keys():
                if fmt.get(k):
                    adsterra_format_urls[k] = fmt.get(k)
        except Exception:
            pass

    adsterra_direct_link = adsterra_action_urls[0] if adsterra_action_urls else None

    return template.render(
        file_name=file_name,
        file_url=src,
        file_size=file_size,
        mime_type=resolved_mime,
        category=category,
        uploader=uploader,
        message_id=message_id,
        is_audio=is_audio,
        updates_url=updates_url,
        report_url=report_url,
        adsterra_enabled=adsterra_enabled,
        adsterra_direct_link=adsterra_direct_link,
        adsterra_action_urls=adsterra_action_urls,
        adsterra_format_urls=adsterra_format_urls,
        adsterra_script_urls=adsterra_script_urls,
    )


async def render_folder(folder_id: str, title: str = "Folder"):
    folder = await db.get_folder(folder_id)
    files = []
    seen = set()
    for fid in folder.get("files", []):
        if fid in seen:
            continue
        seen.add(fid)
        try:
            file_data = await db.get_file(fid)
        except Exception:
            continue
        raw_name = (file_data.get("file_name") or "file")
        file_name = raw_name.replace("_", " ")
        file_name = file_name.replace("\n", " ").replace("\r", " ")
        if len(file_name) > 150:
            file_name = file_name[:150] + "…"
        mime = (file_data.get("mime_type") or "").lower()
        kind = "video" if mime.startswith("video/") else "audio" if mime.startswith("audio/") else "other"
        ext = os.path.splitext(raw_name)[1].lower()
        video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
        audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}
        if kind == "other":
            if ext in video_ext:
                kind = "video"
            elif ext in audio_ext:
                kind = "audio"
        playable = kind in ("video", "audio")
        category = file_data.get("category") or detect_category(file_name=raw_name, mime_type=mime, file_ext=ext)
        uploader = (file_data.get("uploader") or "Unknown uploader").replace("\n", " ").replace("\r", " ")
        if len(uploader) > 80:
            uploader = uploader[:80] + "…"

        files.append({
            "id": str(file_data.get("_id")),
            "name": file_name,
            "_sort_name": raw_name,
            "size": humanbytes(file_data.get("file_size") or 0),
            "mime": mime,
            "kind": kind,
            "category": category,
            "uploader": uploader,
            "message_id": file_data.get("message_id"),
            "playable": playable,
            "url": urllib.parse.urljoin(Server.URL, f"dl/{file_data['_id']}")
        })

    if not files:
        raise FileNotFound

    files.sort(key=_folder_sort_key)

    # Internal sort helper key should not leak to templates/json
    for item in files:
        item.pop("_sort_name", None)

    base_dir = os.path.dirname(os.path.dirname(__file__))  # FileStream/
    template_file = os.path.join(base_dir, "template", "folder.html")

    with open(template_file, encoding="utf-8") as f:
        template = env.from_string(f.read())

    folder_json = json.dumps(files, ensure_ascii=False)
    folder_json = folder_json.replace("</", "<\\/")

    report_url = None
    if getattr(FileStream, "username", None):
        report_url = f"https://t.me/{FileStream.username}?start=report_folder_{folder_id}"

    web_ads_status = await db.get_web_ads_status()
    adsterra_enabled = adsterra_is_enabled(web_ads_status)
    adsterra_script_urls = get_script_urls() if adsterra_enabled else []

    adsterra_action_urls = []
    adsterra_format_urls = {
        "smartlink": None,
        "popunder": None,
        "social_bar": None,
        "native_banner": None,
        "banner": None,
    }

    if adsterra_enabled:
        direct = get_direct_link()
        if direct:
            adsterra_action_urls.append(direct)
            adsterra_format_urls["smartlink"] = direct

        try:
            bundle = await resolve_ad_bundle(max_urls=8)
            for u in bundle.get("action_urls", []):
                if u and u not in adsterra_action_urls:
                    adsterra_action_urls.append(u)

            fmt = bundle.get("format_urls") or {}
            for k in adsterra_format_urls.keys():
                if fmt.get(k):
                    adsterra_format_urls[k] = fmt.get(k)
        except Exception:
            pass

    adsterra_direct_link = adsterra_action_urls[0] if adsterra_action_urls else None

    return template.render(
        folder_id=str(folder_id),
        folder_json=folder_json,
        files=files,
        count=len(files),
        page_title=title,
        report_url=report_url,
        adsterra_enabled=adsterra_enabled,
        adsterra_direct_link=adsterra_direct_link,
        adsterra_action_urls=adsterra_action_urls,
        adsterra_format_urls=adsterra_format_urls,
        adsterra_script_urls=adsterra_script_urls,
    )


# alias removed
