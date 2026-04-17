import time
import math
import logging
import mimetypes
import traceback
import os
import secrets
from datetime import datetime, timedelta
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from FileStream.bot import multi_clients, work_loads, FileStream
from FileStream.config import Telegram, Server
from FileStream.server.exceptions import FileNotFound, InvalidHash
from FileStream import utils, StartTime, __version__
from FileStream.utils.database import Database
from FileStream.utils.file_properties import ensure_flog_media_exists
from FileStream.utils.client_balance import choose_best_client
from FileStream.utils.public_links import build_public_file_url, build_public_folder_url
from FileStream.utils.render_template import render_page, render_folder, render_public_page, render_public_folder
from FileStream.utils.client_identity import get_bot_username

routes = web.RouteTableDef()
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

# One-time download token store
# Format: {token: {"path": str, "expires": datetime, "used": bool}}
_download_tokens = {}

def _generate_token():
    """Generate a secure random token"""
    return secrets.token_urlsafe(32)

def _clean_expired_tokens():
    """Remove expired tokens from store"""
    now = datetime.utcnow()
    expired = [k for k, v in _download_tokens.items() if v["expires"] < now]
    for k in expired:
        del _download_tokens[k]

def _create_download_token(path: str, expires_in_seconds: int = 300) -> str:
    """Create a one-time download token (default 5 min expiry)"""
    _clean_expired_tokens()
    token = _generate_token()
    _download_tokens[token] = {
        "path": path,
        "expires": datetime.utcnow() + timedelta(seconds=expires_in_seconds),
        "used": False
    }
    return token

def _validate_and_consume_token(token: str) -> str | None:
    """Validate token and return path if valid, None otherwise. Marks token as used."""
    _clean_expired_tokens()
    data = _download_tokens.get(token)
    if not data:
        return None
    if data["used"]:
        return None
    if data["expires"] < datetime.utcnow():
        del _download_tokens[token]
        return None
    # Mark as used (one-time)
    data["used"] = True
    path = data["path"]
    # Clean up after use
    del _download_tokens[token]
    return path


def invalidate_file_access(path: str) -> None:
    path = str(path or "")
    if not path:
        return

    expired_tokens = [token for token, data in _download_tokens.items() if data.get("path") == path]
    for token in expired_tokens:
        _download_tokens.pop(token, None)

    for streamer in class_cache.values():
        try:
            streamer.cached_file_ids.pop(path, None)
        except Exception:
            continue

@routes.get("/status", allow_head=True)
async def root_route_handler(_):
    bot_username = get_bot_username(FileStream)
    return web.json_response(
        {
            "server_status": "running",
            "uptime": utils.get_readable_time(time.time() - StartTime),
            "telegram_bot": f"@{bot_username}" if bot_username else None,
            "connected_bots": len(multi_clients),
            "loads": dict(
                ("bot" + str(c + 1), l)
                for c, (_, l) in enumerate(
                    sorted(work_loads.items(), key=lambda x: x[1], reverse=True)
                )
            ),
            "version": __version__,
        }
    )

@routes.get("/watch/{path}", allow_head=True)
async def watch_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        _, public_link = await db.resolve_file_reference(path)
        raise web.HTTPFound(location=build_public_file_url(public_link["public_id"]))
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")

def _public_link_error_page(title: str, message: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; background: #0f172a; color: #e5e7eb; margin: 0; }}
    main {{ min-height: 100vh; display: grid; place-items: center; padding: 24px; }}
    .card {{ max-width: 560px; width: 100%; background: #111827; border: 1px solid #334155; border-radius: 20px; padding: 28px; }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
    p {{ margin: 0; line-height: 1.6; color: #cbd5e1; }}
  </style>
</head>
<body>
  <main>
    <section class="card">
      <h1>{title}</h1>
      <p>{message}</p>
    </section>
  </main>
</body>
</html>"""


@routes.get("/gen/{public_id}", allow_head=True)
async def gen_handler(request: web.Request):
    public_id = request.match_info["public_id"]
    try:
        return web.Response(text=await render_public_page(public_id), content_type="text/html")
    except FileNotFound as e:
        return web.Response(
            text=_public_link_error_page("Link unavailable", e.message or "This file link is not available anymore."),
            content_type="text/html",
            status=404,
        )
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")

@routes.get("/folder/{folder_id}", allow_head=True)
async def folder_handler(request: web.Request):
    try:
        folder_id = request.match_info["folder_id"]
        _, public_link = await db.resolve_folder_reference(folder_id)
        raise web.HTTPFound(location=build_public_folder_url(public_link["public_id"]))
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")

# legacy /folderm route (kept for old links)
@routes.get("/folderm/{folder_id}", allow_head=True)
async def folderm_handler(request: web.Request):
    try:
        folder_id = request.match_info["folder_id"]
        _, public_link = await db.resolve_folder_reference(folder_id)
        raise web.HTTPFound(location=build_public_folder_url(public_link["public_id"]))
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")


@routes.get("/gfolder/{public_id}", allow_head=True)
async def gfolder_handler(request: web.Request):
    public_id = request.match_info["public_id"]
    try:
        return web.Response(text=await render_public_folder(public_id, title="Folder"), content_type="text/html")
    except FileNotFound as e:
        return web.Response(
            text=_public_link_error_page("Folder unavailable", e.message or "This folder link is not available anymore."),
            content_type="text/html",
            status=404,
        )
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")

@routes.get("/dl/{path}", allow_head=True)
async def dl_handler(request: web.Request):
    # Serve files for streaming (video/audio playback)
    try:
        path = request.match_info["path"]
        return await media_streamer(request, path)
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")
    except Exception as e:
        traceback.print_exc()
        logging.critical(e.with_traceback(None))
        logging.debug(traceback.format_exc())
        raise web.HTTPInternalServerError(text=str(e))

@routes.get("/get-download-token/{path}", allow_head=False)
async def get_download_token_handler(request: web.Request):
    """Generate a one-time download token for the file"""
    try:
        path = request.match_info["path"]
        file_info, public_link = await db.resolve_file_reference(path)
        await ensure_flog_media_exists(file_info, bot=FileStream, prune_stale=True, db_instance=db)
        # Create a token that expires in 5 minutes
        token_path = public_link["public_id"] if public_link else str(file_info["_id"])
        token = _create_download_token(token_path, expires_in_seconds=300)
        download_url = f"{Server.URL}file/{token}"
        return web.json_response({
            "success": True,
            "download_url": download_url,
            "expires_in": 300
        })
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except Exception as e:
        logging.error(f"Error generating download token: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

@routes.get("/file/{token}", allow_head=True)
async def file_handler(request: web.Request):
    """Serve file using one-time token"""
    try:
        token = request.match_info["token"]
        path = _validate_and_consume_token(token)
        
        if not path:
            # Token invalid, expired, or already used
            raise web.HTTPForbidden(text="Download link expired or already used. Please go back and click Download again.")
        
        # Serve the file
        return await media_streamer(request, path, force_download=True)
    except web.HTTPForbidden:
        raise
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except Exception as e:
        traceback.print_exc()
        logging.critical(e.with_traceback(None))
        logging.debug(traceback.format_exc())
        raise web.HTTPInternalServerError(text=str(e))

class_cache = {}

def _sanitize_filename(name: str) -> str:
    if not isinstance(name, str):
        name = str(name or "")
    # Remove control chars and path separators
    name = name.replace("\x00", " ").replace("\n", " ").replace("\r", " ")
    name = name.replace("/", " ").replace("\\", " ").replace('"', "")
    name = "".join(ch for ch in name if ch.isprintable())
    name = " ".join(name.split()).strip()
    if not name:
        return "file"
    if len(name) > 150:
        name = name[:150]
    return name


def _parse_range(range_header: str, file_size: int):
    if not range_header:
        return None
    header = range_header.strip().lower()
    if not header.startswith("bytes="):
        return False
    # Only support a single range; ignore extras
    range_spec = header.split("=", 1)[1].split(",", 1)[0].strip()
    if "-" not in range_spec:
        return False
    start_str, end_str = range_spec.split("-", 1)
    if start_str == "" and end_str == "":
        return False
    try:
        if start_str == "":
            # suffix range: last N bytes
            length = int(end_str)
            if length <= 0:
                return False
            start = max(file_size - length, 0)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
    except ValueError:
        return False
    return start, end


async def media_streamer(request: web.Request, db_id: str, *, force_download: bool = False):
    range_header = request.headers.get("Range")

    # MongoDB remains the source of truth for whether a file is still active.
    # This prevents stale in-memory file_id cache entries from keeping deleted
    # files accessible until cache expiry.
    file_info, _ = await db.resolve_file_reference(db_id)
    await ensure_flog_media_exists(file_info, bot=FileStream, prune_stale=True, db_instance=db)
    internal_db_id = str(file_info["_id"])

    if not work_loads:
        raise web.HTTPServiceUnavailable(text="No available clients")

    index = choose_best_client(multi_clients.keys())
    faster_client = multi_clients[index]
    
    if Telegram.MULTI_CLIENT:
        logging.info(f"Client {index} is now serving {request.headers.get('X-FORWARDED-FOR',request.remote)}")

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
        logging.debug(f"Using cached ByteStreamer object for client {index}")
    else:
        logging.debug(f"Creating new ByteStreamer object for client {index}")
        tg_connect = utils.ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect
    
    logging.debug("before calling get_file_properties")
    file_id = await tg_connect.get_file_properties(internal_db_id, multi_clients)
    logging.debug("after calling get_file_properties")
    
    file_size = file_id.file_size
    if not file_size or file_size <= 0:
        raise web.HTTPNotFound(text="File not found")

    if range_header:
        parsed = _parse_range(range_header, file_size)
        if parsed is False:
            return web.Response(
                status=416,
                body="416: Range not satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        if parsed is None:
            from_bytes = 0
            until_bytes = file_size - 1
            range_header = None
        else:
            from_bytes, until_bytes = parsed
    else:
        from_bytes = 0
        until_bytes = file_size - 1

    if (until_bytes > file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = 1024 * 1024
    until_bytes = min(until_bytes, file_size - 1)

    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1

    req_length = until_bytes - from_bytes + 1
    part_count = math.ceil((until_bytes + 1) / chunk_size) - math.floor(offset / chunk_size)
    body = None
    if request.method != "HEAD":
        body = tg_connect.yield_file(
            file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
        )

    mime_type = (file_id.mime_type or "").strip()
    file_name = _sanitize_filename(utils.get_name(file_id))

    # RFC 5987 filename* fallback for non-ASCII names
    from urllib.parse import quote
    encoded_name = quote(file_name)

    if not mime_type:
        mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"

    mime_type = (mime_type or "application/octet-stream").lower()

    # Keep media inline for the player, but force attachment for tokenized
    # download links so browsers/download managers preserve the real filename
    # instead of deriving one from /file/{token}.
    ext = os.path.splitext(file_name)[1].lower()
    video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
    audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}
    explicit_download = force_download or request.query.get("download", "").lower() in {"1", "true", "yes"}
    fetch_dest = request.headers.get("Sec-Fetch-Dest", "").lower()
    embedded_media_request = fetch_dest in {"video", "audio", "image"}
    direct_dl_download = request.path.startswith("/dl/") and not embedded_media_request
    if explicit_download or direct_dl_download:
        disposition = "attachment"
    elif "video" in mime_type or "audio" in mime_type or "image" in mime_type or ext in video_ext or ext in audio_ext:
        disposition = "inline"
    else:
        disposition = "attachment"

    headers = {
        "Content-Type": f"{mime_type}",
        "Content-Length": str(req_length),
        "Content-Disposition": f"{disposition}; filename=\"{file_name}\"; filename*=UTF-8''{encoded_name}",
        "Accept-Ranges": "bytes",
    }
    
    if range_header:
        headers["Content-Range"] = f"bytes {from_bytes}-{until_bytes}/{file_size}"
        
    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers=headers,
    )
