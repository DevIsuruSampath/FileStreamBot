import os
import aiohttp
import jinja2
import urllib.parse
from FileStream.config import Telegram, Server
from FileStream.utils.database import Database
from FileStream.utils.human_readable import humanbytes
db = Database(Telegram.DATABASE_URL, Telegram.SESSION_NAME)

async def render_page(db_id):
    file_data=await db.get_file(db_id)
    src = urllib.parse.urljoin(Server.URL, f'dl/{file_data["_id"]}')
    file_size = humanbytes(file_data.get('file_size') or 0)
    file_name = file_data['file_name'].replace("_", " ")

    base_dir = os.path.dirname(os.path.dirname(__file__))  # FileStream/
    mime_type = (file_data.get('mime_type') or '').split('/')[0].strip()
    if str(mime_type) == 'video':
        template_file = os.path.join(base_dir, "template", "play.html")
    else:
        template_file = os.path.join(base_dir, "template", "dl.html")

    # Fallback to Content-Length when size is missing/zero
    if not file_data.get('file_size'):
        async with aiohttp.ClientSession() as s:
            async with s.get(src) as u:
                length = u.headers.get('Content-Length')
                file_size = humanbytes(int(length)) if length else file_size

    with open(template_file) as f:
        env = jinja2.Environment(autoescape=True)
        template = env.from_string(f.read())

    return template.render(
        file_name=file_name,
        file_url=src,
        file_size=file_size
    )
