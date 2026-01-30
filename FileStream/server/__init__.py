import os
from aiohttp import web
from .stream_routes import routes

def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)

    # -----------------[ STATIC FILES SETUP ]----------------- #
    # This serves files from 'FileStream/static/' at the URL '/static/'
    static_path = 'FileStream/static'
    if os.path.isdir(static_path):
        web_app.router.add_static('/static/', path=static_path, name='static')
    else:
        print(f"[WARNING] Static folder not found at: {static_path}. Local CSS/JS will not work.")
        
    return web_app