from os import environ as env
from urllib.parse import urlparse
from dotenv import load_dotenv


def _float_env(key: str, default: float) -> float:
    try:
        return float(env.get(key, default))
    except Exception:
        return float(default)


load_dotenv()

class Telegram:
    API_ID = int(env.get("API_ID", 0))
    API_HASH = str(env.get("API_HASH"))
    BOT_TOKEN = str(env.get("BOT_TOKEN"))
    OWNER_ID = int(env.get('OWNER_ID', '7978482443'))
    WORKERS = int(env.get("WORKERS", env.get("BOT_WORKERS", "6")))
    DATABASE_URL = str(env.get('DATABASE_URL'))
    UPDATES_CHANNEL = str(env.get('UPDATES_CHANNEL', "Telegram"))
    SESSION_NAME = str(env.get('SESSION_NAME', 'FileStream'))
    FORCE_SUB_ID = env.get('FORCE_SUB_ID', None)
    FORCE_SUB = env.get('FORCE_SUB', False)
    FORCE_SUB = True if str(FORCE_SUB).lower() == "true" else False
    SLEEP_THRESHOLD = int(env.get("SLEEP_THRESHOLD", "60"))
    FILE_PIC = env.get('FILE_PIC', "https://graph.org/file/5bb9935be0229adf98b73.jpg")
    START_PIC = env.get('START_PIC', "https://graph.org/file/290af25276fa34fa8f0aa.jpg")
    VERIFY_PIC = env.get('VERIFY_PIC', "https://graph.org/file/736e21cc0efa4d8c2a0e4.jpg")
    MULTI_CLIENT = False
    
    # Safely handle optional integer env vars
    _flog = env.get("FLOG_CHANNEL", None)
    FLOG_CHANNEL = int(_flog) if _flog else None

    _ulog = env.get("ULOG_CHANNEL", None)
    ULOG_CHANNEL = int(_ulog) if _ulog else None

    MODE = env.get("MODE", "primary")
    SECONDARY = True if MODE.lower() == "secondary" else False
    _auth_raw = str(env.get("AUTH_USERS", "")).split()
    AUTH_USERS = []
    for x in _auth_raw:
        try:
            AUTH_USERS.append(int(x))
        except Exception:
            pass
    AUTH_USERS = list(set(AUTH_USERS))

    # --- [ NEW: URL SHORTENER CONFIG ] ---
    URL_SHORTENER_API_KEY = env.get('URL_SHORTENER_API_KEY', None)
    URL_SHORTENER_SITE = env.get('URL_SHORTENER_SITE', None)

class Server:
    PORT = int(env.get("PORT", 8080))
    BIND_ADDRESS = str(env.get("BIND_ADDRESS", "0.0.0.0"))
    PING_INTERVAL = int(env.get("PING_INTERVAL", "1200"))
    HAS_SSL = str(env.get("HAS_SSL", "0")).lower() in ("1", "true", "t", "yes", "y")
    NO_PORT = str(env.get("NO_PORT", "0")).lower() in ("1", "true", "t", "yes", "y")
    _raw_fqdn = str(env.get("FQDN", BIND_ADDRESS))
    parsed = urlparse(_raw_fqdn if "://" in _raw_fqdn else f"//{_raw_fqdn}")
    FQDN = parsed.netloc or parsed.path
    has_port = parsed.port is not None
    URL = "http{}://{}{}/".format(
        "s" if HAS_SSL else "", FQDN, "" if (NO_PORT or has_port) else ":" + str(PORT)
    )

class NSFW:
    ENABLE = str(env.get("NUDENET_ENABLE", "true")).lower() in ("1", "true", "t", "yes", "y")
    BLOCK_ON_ERROR = str(env.get("NUDENET_BLOCK_ON_ERROR", "false")).lower() in (
        "1",
        "true",
        "t",
        "yes",
        "y",
    )
    THRESHOLD = _float_env("NUDENET_THRESHOLD", 0.6)
    SCAN_IMAGES = str(env.get("NUDENET_SCAN_IMAGES", "true")).lower() in (
        "1",
        "true",
        "t",
        "yes",
        "y",
    )
    SCAN_VIDEOS = str(env.get("NUDENET_SCAN_VIDEOS", "true")).lower() in (
        "1",
        "true",
        "t",
        "yes",
        "y",
    )
    MAX_VIDEO_FRAMES = int(env.get("NUDENET_MAX_VIDEO_FRAMES", "12"))
    FRAME_INTERVAL = int(env.get("NUDENET_FRAME_INTERVAL", "5"))
    TEMP_DIR = str(env.get("NUDENET_TEMP_DIR", "/tmp/filestream_nsfw"))
