import os
from aiohttp import web
from .stream_routes import routes

def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)

    # -----------------[ STATIC FILES SETUP ]----------------- #
    # Resolve static folder path dynamically (FileStream/static)
    # This ensures it works regardless of CWD (Docker, local, etc.)
    current_dir = os.path.dirname(os.path.abspath(__file__))  # FileStream/server
    package_dir = os.path.dirname(current_dir)                # FileStream
    static_path = os.path.join(package_dir, 'static')
    
    if os.path.isdir(static_path):
        web_app.router.add_static('/static/', path=static_path, name='static')
    else:
        print(f"[WARNING] Static folder not found at: {static_path}. Local CSS/JS will not work.")
        
    return web_app