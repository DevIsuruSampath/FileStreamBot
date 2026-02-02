import os
import json
import aiohttp
import jinja2
import urllib.parse
from FileStream.config import Telegram, Server
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
from FileStream.server.exceptions import FileNotFound

env = jinja2.Environment(autoescape=True)
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

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

    return template.render(
        file_name=file_name,
        file_url=src,
        file_size=file_size,
        mime_type=resolved_mime,
        is_audio=is_audio,
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
        files.append({
            "id": str(file_data.get("_id")),
            "name": file_name,
            "size": humanbytes(file_data.get("file_size") or 0),
            "mime": mime,
            "kind": kind,
            "playable": playable,
            "url": urllib.parse.urljoin(Server.URL, f"dl/{file_data['_id']}")
        })

    if not files:
        raise FileNotFound

    base_dir = os.path.dirname(os.path.dirname(__file__))  # FileStream/
    template_file = os.path.join(base_dir, "template", "folder.html")

    with open(template_file, encoding="utf-8") as f:
        template = env.from_string(f.read())

    folder_json = json.dumps(files, ensure_ascii=False)
    folder_json = folder_json.replace("</", "<\\/")

    return template.render(
        folder_id=str(folder_id),
        folder_json=folder_json,
        files=files,
        count=len(files),
        page_title=title,
    )


# Backward-compatible alias
async def render_playlist(playlist_id: str, title: str = "Folder"):
    return await render_folder(playlist_id, title=title)
