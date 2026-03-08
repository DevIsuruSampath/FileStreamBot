import time
import math
import logging
import mimetypes
import traceback
import os
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from FileStream.bot import multi_clients, work_loads, FileStream
from FileStream.config import Telegram, Server
from FileStream.server.exceptions import FileNotFound, InvalidHash
from FileStream import utils, StartTime, __version__
from FileStream.utils.render_template import render_page, render_folder

routes = web.RouteTableDef()

@routes.get("/status", allow_head=True)
async def root_route_handler(_):
    return web.json_response(
        {
            "server_status": "running",
            "uptime": utils.get_readable_time(time.time() - StartTime),
            "telegram_bot": "@" + FileStream.username if getattr(FileStream, "username", None) else None,
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
        return web.Response(text=await render_page(path), content_type='text/html')
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")

# legacy route removed

@routes.get("/folder/{folder_id}", allow_head=True)
async def folder_handler(request: web.Request):
    try:
        folder_id = request.match_info["folder_id"]
        return web.Response(text=await render_folder(folder_id, title="Folder"), content_type='text/html')
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")

# legacy /folderm route (kept for old links)
@routes.get("/folderm/{folder_id}", allow_head=True)
async def folderm_handler(request: web.Request):
    try:
        folder_id = request.match_info["folder_id"]
        return web.Response(text=await render_folder(folder_id, title="Folder"), content_type='text/html')
    except FileNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        raise web.HTTPServiceUnavailable(text="Service Unavailable")

@routes.get("/dl/{path}", allow_head=True)
async def dl_handler(request: web.Request):
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


async def media_streamer(request: web.Request, db_id: str):
    range_header = request.headers.get("Range")

    if not work_loads:
        raise web.HTTPServiceUnavailable(text="No available clients")

    index = min(work_loads, key=work_loads.get)
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
    file_id = await tg_connect.get_file_properties(db_id, multi_clients)
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

    # Use "inline" for media to allow in-browser playback
    # Use "attachment" for everything else to force download
    ext = os.path.splitext(file_name)[1].lower()
    video_ext = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpeg", ".mpg"}
    audio_ext = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".oga"}
    if "video" in mime_type or "audio" in mime_type or "image" in mime_type or ext in video_ext or ext in audio_ext:
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
