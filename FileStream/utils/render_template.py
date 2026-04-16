import os
import re
import json
import mimetypes
import jinja2
import urllib.parse

from FileStream.config import Telegram, Server, WebAds
from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.category import detect_category
from FileStream.utils.file_properties import ensure_flog_media_exists
from FileStream.utils.public_links import (
    build_public_bot_open_link,
    build_public_download_token_path,
    build_public_file_url,
    build_public_folder_url,
    build_public_stream_url,
)
from FileStream.utils.client_identity import build_start_link, get_bot_username
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


def _safe_text(value, fallback: str) -> str:
    text = str(value or fallback)
    text = text.replace("\n", " ").replace("\r", " ").strip()
    return text or fallback


def _template_context(**kwargs):
    return {
        **kwargs,
        "ad_config": WebAds.template_context(),
    }


async def render_page(db_id, file_data: dict | None = None, public_link: dict | None = None):
    file_data = file_data or await db.get_file(db_id)
    if not file_data:
        raise FileNotFound
    file_data = await ensure_flog_media_exists(file_data, bot=FileStream, prune_stale=True, db_instance=db)
    public_link = public_link or await db.ensure_public_link_for_file(file_data)
    public_id = public_link["public_id"]

    template_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template", "play.html")
    with open(template_file, "r", encoding="utf-8") as f:
        template = env.from_string(f.read())

    raw_name = file_data.get("file_name") or "file"
    file_name = raw_name.replace("_", " ")
    if len(file_name) > 75:
        file_name = file_name[:75] + "…"

    stream_url = build_public_stream_url(public_id)
    share_url = build_public_file_url(public_id)
    file_size = humanbytes(file_data.get("file_size") or 0)

    mime_type = (file_data.get("mime_type") or "").lower()
    primary = mime_type.split("/")[0].strip() if mime_type else ""
    ext = os.path.splitext(raw_name)[1].lower()

    video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
    audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}

    category = file_data.get("category") or detect_category(file_name=raw_name, mime_type=mime_type, file_ext=ext)
    uploader = _safe_text(file_data.get("uploader"), "Unknown uploader")
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
        guessed, _ = mimetypes.guess_type(raw_name)
        resolved_mime = guessed or mime_type or "application/octet-stream"

    updates_url = None
    if Telegram.UPDATES_CHANNEL:
        channel = str(Telegram.UPDATES_CHANNEL).replace("-100", "").replace("@", "")
        updates_url = f"https://t.me/{channel}"

    report_url = None
    if get_bot_username(FileStream):
        report_url = build_start_link(f"report_file_{public_id}", FileStream)

    return template.render(
        **_template_context(
            file_name=file_name,
            file_url=stream_url,
            file_id=public_id,
            share_url=share_url,
            telegram_url=build_public_bot_open_link(public_id, FileStream),
            public_id=public_id,
            download_token_path=build_public_download_token_path(public_id),
            file_size=file_size,
            mime_type=resolved_mime,
            category=category,
            uploader=uploader,
            message_id=message_id,
            is_audio=is_audio,
            updates_url=updates_url,
            report_url=report_url,
        )
    )


async def render_public_page(public_id: str):
    file_data, public_link = await db.resolve_public_file(public_id, increment_click=True)
    return await render_page(str(file_data["_id"]), file_data=file_data, public_link=public_link)


async def render_folder(folder_id: str, title: str = "Folder", folder_doc: dict | None = None, public_link: dict | None = None):
    folder_doc = folder_doc or await db.get_folder(folder_id)
    if not folder_doc:
        raise FileNotFound
    public_link = public_link or await db.ensure_public_link_for_folder(folder_doc)
    folder_public_id = public_link["public_id"]

    file_ids = folder_doc.get("files") or []
    files = []

    for fid in file_ids:
        file_data = await db.get_file(fid)
        if not file_data:
            continue
        file_public = await db.ensure_public_link_for_file(file_data)
        file_public_id = file_public["public_id"]

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
        uploader = _safe_text(file_data.get("uploader"), "Unknown uploader")
        if len(uploader) > 80:
            uploader = uploader[:80] + "…"

        files.append(
            {
                "id": file_public_id,
                "name": file_name,
                "_sort_name": raw_name,
                "size": humanbytes(file_data.get("file_size") or 0),
                "mime": mime,
                "kind": kind,
                "category": category,
                "uploader": uploader,
                "playable": playable,
                "stream_url": build_public_stream_url(file_public_id),
                "share_url": build_public_file_url(file_public_id),
                "download_id": file_public_id,
                "telegram_url": build_public_bot_open_link(file_public_id, FileStream),
            }
        )

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
    if get_bot_username(FileStream):
        report_url = build_start_link(f"report_folder_{folder_public_id}", FileStream)

    return template.render(
        **_template_context(
            folder_id=folder_public_id,
            folder_share_url=build_public_folder_url(folder_public_id),
            folder_json=folder_json,
            files=files,
            count=len(files),
            page_title=title,
            report_url=report_url,
        )
    )


async def render_public_folder(public_id: str, title: str = "Folder"):
    folder_doc, public_link = await db.resolve_public_folder(public_id, increment_click=True)
    return await render_folder(str(folder_doc["_id"]), title=title, folder_doc=folder_doc, public_link=public_link)
