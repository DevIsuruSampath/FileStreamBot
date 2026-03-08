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
    file_data = await db.get_file(db_id)
    if not file_data:
        raise FileNotFound

    template_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template", "play.html")
    with open(template_file, "r", encoding="utf-8") as f:
        template = env.from_string(f.read())

    raw_name = file_data.get("file_name") or "file"
    file_name = raw_name.replace("_", " ")
    if len(file_name) > 75:
        file_name = file_name[:75] + "…"

    src = urllib.parse.urljoin(Server.URL, f"dl/{db_id}")
    file_size = humanbytes(file_data.get("file_size") or 0)

    mime_type = (file_data.get("mime_type") or "").lower()
    primary = mime_type.split("/")[0].strip() if mime_type else ""
    ext = os.path.splitext(raw_name)[1].lower()
    video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
    audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}

    category = file_data.get("category") or detect_category(file_name=raw_name, mime_type=mime_type, file_ext=ext)
    uploader = (file_data.get("uploader") or "Unknown uploader").replace("
", " ").replace("", " ")
    if len(uploader) > 80:
        uploader = uploader[:80] + "…"

    message_id = file_data.get("message_id")

    is_audio = primary == "audio" or ext in audio_ext
    is_video = primary == "video" or ext in video_ext

    if is_audio:
        resolved_mime = mime_type or "audio/mpeg"
    elif is_video:
        resolved_mime = mime_type or "video/mp4"
    else:
        guessed, _ = __import__("mimetypes").guess_type(raw_name)
        resolved_mime = guessed or mime_type or "application/octet-stream"

    updates_url = None
    if Telegram.UPDATES_CHANNEL:
        channel = str(Telegram.UPDATES_CHANNEL).replace("-100", "").replace("@", "")
        updates_url = f"https://t.me/{channel}"

    report_url = None
    if getattr(FileStream, "username", None):
        report_url = f"https://t.me/{FileStream.username}?start=report_file_{db_id}"

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
    )


async def render_folder(folder_id: str, title: str = "Folder"):
    folder_doc = await db.get_folder(folder_id)
    if not folder_doc:
        raise FileNotFound

    file_ids = folder_doc.get("files") or []
    files = []
    for fid in file_ids:
        file_data = await db.get_file(fid)
        if not file_data:
            continue

        raw_name = file_data.get("file_name") or "file"
        file_name = raw_name.replace("_", " ")
        mime = (file_data.get("mime_type") or "").lower()
        primary = mime.split("/")[0].strip() if mime else ""
        ext = os.path.splitext(raw_name)[1].lower()

        video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
        audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}

        kind = "file"
        if primary == "video" or ext in video_ext:
            kind = "video"
            if not mime:
                mime = "video/mp4"
        elif primary == "audio" or ext in audio_ext:
            kind = "audio"
            if not mime:
                mime = "audio/mpeg"

        playable = kind in ("video", "audio")
        category = file_data.get("category") or detect_category(file_name=raw_name, mime_type=mime, file_ext=ext)
        uploader = (file_data.get("uploader") or "Unknown uploader").replace("
", " ").replace("", " ")
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
    for item in files:
        item.pop("_sort_name", None)

    folder_json = json.dumps(files)

    template_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template", "folder.html")
    with open(template_file, "r", encoding="utf-8") as f:
        template = env.from_string(f.read())

    report_url = None
    if getattr(FileStream, "username", None):
        report_url = f"https://t.me/{FileStream.username}?start=report_folder_{folder_id}"

    return template.render(
        folder_id=str(folder_id),
        folder_json=folder_json,
        files=files,
        count=len(files),
        page_title=title,
        report_url=report_url,
    )
