import os
import re
import json
import time
import mimetypes
import jinja2
import urllib.parse

from FileStream import __version__
from FileStream.config import Telegram, Server, WebAds
from FileStream.bot import FileStream
from FileStream.utils.database import Database
from FileStream.utils.access_tokens import create_access_token
from FileStream.utils.human_readable import humanbytes
from FileStream.utils.category import detect_category
from FileStream.utils.file_properties import ensure_flog_media_exists
from FileStream.utils.public_links import (
    build_public_bot_open_link,
    build_public_download_token_path,
    build_public_file_url,
    build_public_folder_url,
    build_public_stream_token_path,
)
from FileStream.utils.client_identity import build_add_to_group_link, build_start_link, get_bot_name, get_bot_username
from FileStream.utils.legal import (
    build_policy_page_context,
    build_policy_url,
    build_updates_channel_url,
)
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


def _bot_join_url() -> str | None:
    username = get_bot_username(FileStream)
    if not username:
        return None
    return f"https://t.me/{username}"


def _http_media_url(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if raw.lower().startswith(("http://", "https://")):
        return raw
    return None


async def _template_context(**kwargs):
    web_ads_enabled = await db.get_web_ads_status()
    bot_username = get_bot_username(FileStream)
    return {
        **kwargs,
        "ad_config": WebAds.template_context(enabled_override=web_ads_enabled),
        "bot_username": bot_username,
        "bot_join_url": _bot_join_url(),
        "legal_url": build_policy_url("legal"),
        "privacy_url": build_policy_url("privacy"),
        "updates_channel_url": build_updates_channel_url(),
    }


async def render_page(
    db_id,
    file_data: dict | None = None,
    public_link: dict | None = None,
    *,
    session_id: str | None = None,
):
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

    share_url = build_public_file_url(public_id)
    file_size = humanbytes(file_data.get("file_size") or 0)
    page_token = create_access_token(
        public_id,
        kind="page",
        expires_in_seconds=1800,
        metadata={"session_id": str(session_id or "").strip()},
    )

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

    report_url = None
    if get_bot_username(FileStream):
        report_url = build_start_link(f"report_file_{public_id}", FileStream)

    return template.render(
        **await _template_context(
            file_name=file_name,
            file_id=public_id,
            share_url=share_url,
            telegram_url=build_public_bot_open_link(public_id, FileStream),
            public_id=public_id,
            download_token_path=build_public_download_token_path(public_id),
            stream_token_path=build_public_stream_token_path(public_id),
            page_token=page_token,
            file_size=file_size,
            mime_type=resolved_mime,
            category=category,
            uploader=uploader,
            message_id=message_id,
            is_audio=is_audio,
            report_url=report_url,
        )
    )


async def render_public_page(public_id: str, *, session_id: str | None = None):
    file_data, public_link = await db.resolve_public_file(public_id, increment_click=True)
    return await render_page(
        str(file_data["_id"]),
        file_data=file_data,
        public_link=public_link,
        session_id=session_id,
    )


async def render_folder(
    folder_id: str,
    title: str = "Folder",
    folder_doc: dict | None = None,
    public_link: dict | None = None,
    *,
    session_id: str | None = None,
):
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
                "share_url": build_public_file_url(file_public_id),
                "download_id": file_public_id,
                "stream_token_path": build_public_stream_token_path(file_public_id),
                "download_token_path": build_public_download_token_path(file_public_id),
                "page_token": create_access_token(
                    file_public_id,
                    kind="page",
                    expires_in_seconds=1800,
                    metadata={"session_id": str(session_id or "").strip()},
                ),
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
        **await _template_context(
            folder_id=folder_public_id,
            folder_share_url=build_public_folder_url(folder_public_id),
            folder_json=folder_json,
            files=files,
            count=len(files),
            page_title=title,
            report_url=report_url,
        )
    )


async def render_public_folder(public_id: str, title: str = "Folder", *, session_id: str | None = None):
    folder_doc, public_link = await db.resolve_public_folder(public_id, increment_click=True)
    return await render_folder(
        str(folder_doc["_id"]),
        title=title,
        folder_doc=folder_doc,
        public_link=public_link,
        session_id=session_id,
    )


async def render_policy_page(page: str) -> str:
    template_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template", "legal.html")
    with open(template_file, "r", encoding="utf-8") as f:
        template = env.from_string(f.read())

    context = build_policy_page_context(page, bot_username=get_bot_username(FileStream))
    return template.render(**await _template_context(**context))


async def render_landing_page() -> str:
    template_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template", "landing.html")
    with open(template_file, "r", encoding="utf-8") as f:
        template = env.from_string(f.read())

    bot_username = get_bot_username(FileStream)
    bot_name = get_bot_name(FileStream)
    brand_name = bot_username or bot_name.replace(" ", "") or "QuickFileToLinkBot"
    canonical_url = Server.URL
    legal_url = build_policy_url("legal")
    privacy_url = build_policy_url("privacy")
    updates_channel_url = build_updates_channel_url()
    bot_join_url = _bot_join_url()
    add_to_group_url = build_add_to_group_link(FileStream)
    preview_image_url = _http_media_url(Telegram.START_PIC)
    lastmod = time.strftime("%Y-%m-%d")

    title = f"{brand_name} | FileToLink Telegram File Streaming Bot"
    description = (
        f"{brand_name} turns Telegram files into instant watch and download links. "
        "Use QuickFileToLinkBot for FileToLink sharing, folder pages, and secure TG-FileStreamBot style delivery."
    )
    keywords = [
        brand_name,
        "QuickFileToLinkBot",
        "FileToLink",
        "TG-FileStreamBot",
        "FilestreamBot",
        "Telegram file to link",
        "Telegram file streaming bot",
        "Telegram direct download link",
        "Telegram folder share bot",
    ]

    faq_items = [
        {
            "question": "What is QuickFileToLinkBot?",
            "answer": (
                f"{brand_name} is a Telegram bot that turns uploaded files into public watch, download, and folder links."
            ),
        },
        {
            "question": "How does FileToLink work?",
            "answer": (
                "Send a file to the bot, let it create a public share page, then open the generated link to watch, download, or reopen the file in Telegram."
            ),
        },
        {
            "question": "Is this a TG-FileStreamBot or FilestreamBot style service?",
            "answer": (
                "Yes. The bot focuses on fast Telegram-powered streaming, secure public share pages, and folder-based sharing for multiple files."
            ),
        },
        {
            "question": "Can I share one clean link?",
            "answer": (
                "Yes. The bot is built around generated public share routes so users can share one clean page instead of raw internal stream URLs."
            ),
        },
    ]

    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": title,
                "url": canonical_url,
                "description": description,
            },
            {
                "@type": "SoftwareApplication",
                "name": brand_name,
                "alternateName": ["QuickFileToLinkBot", "FileToLink", "TG-FileStreamBot", "FilestreamBot"],
                "applicationCategory": "ProductivityApplication",
                "operatingSystem": "Telegram Web, Android, iOS, Desktop",
                "description": description,
                "url": canonical_url,
                "softwareVersion": __version__,
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                    }
                    for item in faq_items
                ],
            },
        ],
    }

    features = [
        {
            "title": "One Clean Share Link",
            "text": "Generate a single public page for each file instead of exposing raw stream endpoints.",
        },
        {
            "title": "Watch, Download, Reopen",
            "text": "Users can watch media in the browser, start downloads, or reopen the file inside Telegram.",
        },
        {
            "title": "Folder Sharing",
            "text": "Bundle multiple files into one folder page and share the whole set with one URL.",
        },
        {
            "title": "Telegram-Powered Delivery",
            "text": "The platform uses Telegram and optional FLOG storage, with secure page-bound access tokens on the web side.",
        },
    ]

    steps = [
        "Send or forward a file to the bot.",
        "Receive a generated public share page instantly.",
        "Share the link anywhere or open it again in Telegram.",
    ]

    return template.render(
        **await _template_context(
            page_title=title,
            meta_description=description,
            meta_keywords=", ".join(dict.fromkeys(keywords)),
            canonical_url=canonical_url,
            preview_image_url=preview_image_url,
            schema_json=json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
            brand_name=brand_name,
            bot_name=bot_name,
            bot_username=bot_username,
            bot_join_url=bot_join_url,
            add_to_group_url=add_to_group_url,
            updates_channel_url=updates_channel_url,
            legal_url=legal_url,
            privacy_url=privacy_url,
            features=features,
            steps=steps,
            faq_items=faq_items,
            search_aliases=["QuickFileToLinkBot", "FileToLink", "TG-FileStreamBot", "FilestreamBot"],
            lastmod=lastmod,
        )
    )


def render_robots_txt() -> str:
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /dl/",
        "Disallow: /file/",
        "Disallow: /stream/",
        "Disallow: /get-download-token/",
        "Disallow: /get-stream-token/",
        "Disallow: /gen/",
        "Disallow: /gfolder/",
        "Disallow: /status",
        f"Sitemap: {Server.URL}sitemap.xml",
    ]
    return "\n".join(lines) + "\n"


def render_sitemap_xml() -> str:
    today = time.strftime("%Y-%m-%d")
    urls = (
        Server.URL,
        build_policy_url("legal"),
        build_policy_url("privacy"),
    )
    items = "\n".join(
        f"  <url><loc>{url}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>{priority}</priority></url>"
        for url, priority in zip(urls, ("1.0", "0.5", "0.5"))
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>\n"
    )


async def render_public_error_page(title: str, message: str) -> str:
    template = env.from_string(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root {
      --bg: #09090b;
      --surface: #18181b;
      --surface-soft: #202024;
      --text: #fafafa;
      --muted: #a1a1aa;
      --border: #27272a;
      --primary: #dc2626;
      --primary-2: #991b1b;
      --radius: 18px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      font-family: Inter, system-ui, -apple-system, sans-serif;
      background:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(220, 38, 38, 0.22), transparent),
        var(--bg);
      color: var(--text);
    }
    .container { width: min(960px, 94%); margin: 0 auto; padding: 24px 0 32px; display: grid; gap: 18px; }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 22px;
    }
    .hero h1 { font-size: 2rem; margin-bottom: 10px; letter-spacing: -0.03em; }
    .hero p { color: var(--muted); line-height: 1.65; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
    .btn {
      min-height: 44px;
      padding: 0 16px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      border: 1px solid var(--border);
      text-decoration: none;
      color: var(--text);
      background: var(--surface-soft);
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--primary), var(--primary-2));
      border-color: transparent;
    }
    .ad-card { padding: 14px; }
    .ad-label { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }
    .ad-slot-grid { display: grid; gap: 10px; justify-items: center; }
    .ad-slot { width: 100%; display: none; justify-content: center; align-items: center; min-height: 50px; }
    .ad-slot.loaded { display: flex; }
    .ad-slot-inner { display: flex; align-items: center; justify-content: center; overflow: hidden; }
    .desktop-only { display: block; }
    .mobile-only { display: none !important; }
    .subcopy { color: var(--muted); font-size: 0.9rem; margin-top: 12px; }
    @media (max-width: 767px) {
      .desktop-only { display: none !important; }
      .mobile-only { display: block !important; }
    }
  </style>
</head>
<body>
  <main class="container">
    {% if ad_config.desktop.top_banner.enabled %}
    <section class="card ad-card desktop-only">
      <p class="ad-label">Sponsored</p>
      <div class="ad-slot-grid">
        <div class="ad-slot" data-device="{{ ad_config.desktop.top_banner.device }}" data-key="{{ ad_config.desktop.top_banner.key }}" data-width="{{ ad_config.desktop.top_banner.width }}" data-height="{{ ad_config.desktop.top_banner.height }}" data-invoke-url="{{ ad_config.desktop.top_banner.invoke_url }}"></div>
      </div>
    </section>
    {% endif %}
    {% if ad_config.mobile.top_banner.enabled %}
    <section class="card ad-card mobile-only">
      <p class="ad-label">Sponsored</p>
      <div class="ad-slot-grid">
        <div class="ad-slot" data-device="{{ ad_config.mobile.top_banner.device }}" data-key="{{ ad_config.mobile.top_banner.key }}" data-width="{{ ad_config.mobile.top_banner.width }}" data-height="{{ ad_config.mobile.top_banner.height }}" data-invoke-url="{{ ad_config.mobile.top_banner.invoke_url }}"></div>
      </div>
    </section>
    {% endif %}
    <section class="card hero">
      <h1>{{ title }}</h1>
      <p>{{ message }}</p>
      <div class="actions">
        {% if bot_join_url %}
        <a class="btn btn-primary" href="{{ bot_join_url }}">Join @{{ bot_username }}</a>
        {% endif %}
        {% if bot_join_url %}
        <a class="btn" href="{{ bot_join_url }}">Open Bot</a>
        {% endif %}
      </div>
      {% if bot_username %}
      <p class="subcopy">Need help or a fresh file? Visit our Telegram bot @{{ bot_username }}.</p>
      {% endif %}
    </section>
  </main>
  <script>
    (function () {
      const slots = Array.from(document.querySelectorAll('.ad-slot'));
      let index = 0;
      function loadNext() {
        if (index >= slots.length) return;
        const slot = slots[index++];
        const key = slot.getAttribute('data-key');
        const invokeUrl = slot.getAttribute('data-invoke-url');
        const width = parseInt(slot.getAttribute('data-width') || '0', 10);
        const height = parseInt(slot.getAttribute('data-height') || '0', 10);
        if (!key || !invokeUrl || !width || !height) {
          loadNext();
          return;
        }
        const inner = document.createElement('div');
        inner.className = 'ad-slot-inner';
        inner.style.width = `${width}px`;
        inner.style.height = `${height}px`;
        const s1 = document.createElement('script');
        s1.type = 'text/javascript';
        s1.text = `atOptions = {'key':'${key}','format':'iframe','height':${height},'width':${width},'params':{}};`;
        const s2 = document.createElement('script');
        s2.type = 'text/javascript';
        s2.src = invokeUrl;
        s2.onload = () => { slot.classList.add('loaded'); loadNext(); };
        s2.onerror = () => loadNext();
        inner.appendChild(s1);
        inner.appendChild(s2);
        slot.appendChild(inner);
      }
      loadNext();
    })();
  </script>
</body>
</html>"""
    )
    return template.render(
        **await _template_context(
            title=title,
            message=message,
        )
    )
