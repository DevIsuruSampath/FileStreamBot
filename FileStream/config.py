from os import environ as env
from urllib.parse import urlparse
from dotenv import load_dotenv


def _float_env(key: str, default: float) -> float:
    try:
        return float(env.get(key, default))
    except Exception:
        return float(default)


def _int_or_none(key: str):
    raw = env.get(key, None)
    try:
        return int(raw) if raw not in (None, "") else None
    except Exception:
        return None


def _int_env(key: str, default: int) -> int:
    try:
        return int(env.get(key, default))
    except Exception:
        return int(default)


def _bool_env(key: str, default: bool = False) -> bool:
    return str(env.get(key, str(default))).lower() in ("1", "true", "t", "yes", "y")


def _str_env(key: str, default: str = "") -> str:
    value = env.get(key, default)
    return str(value).strip() if value is not None else ""


load_dotenv()


class Telegram:
    API_ID = int(env.get("API_ID", 0))
    API_HASH = str(env.get("API_HASH"))
    BOT_TOKEN = str(env.get("BOT_TOKEN"))

    OWNER_ID = int(env.get("OWNER_ID", "7978482443"))
    WORKERS = int(env.get("WORKERS", env.get("BOT_WORKERS", "6")))

    DATABASE_URL = str(env.get("DATABASE_URL"))
    SESSION_NAME = str(env.get("SESSION_NAME", "FileStream"))

    UPDATES_CHANNEL = str(env.get("UPDATES_CHANNEL", "Telegram"))

    FORCE_SUB_ID = env.get("FORCE_SUB_ID", None)
    # Support both FORCE_SUB (current) and FORCE_UPDATES_CHANNEL (legacy)
    _force_sub_raw = env.get("FORCE_SUB", env.get("FORCE_UPDATES_CHANNEL", False))
    FORCE_SUB = str(_force_sub_raw).lower() in ("1", "true", "t", "yes", "y")

    SLEEP_THRESHOLD = int(env.get("SLEEP_THRESHOLD", "60"))

    FILE_PIC = env.get("FILE_PIC", "https://graph.org/file/5bb9935be0229adf98b73.jpg")
    START_PIC = env.get("START_PIC", "images/start.jpg")
    VERIFY_PIC = env.get("VERIFY_PIC", "https://graph.org/file/736e21cc0efa4d8c2a0e4.jpg")
    FOLDERS_PIC = env.get("FOLDERS_PIC", "https://graph.org/file/5bb9935be0229adf98b73.jpg")

    # Runtime flag toggled when multiple clients are initialized
    MULTI_CLIENT = False

    # Optional channels
    BIN_CHANNEL = _int_or_none("BIN_CHANNEL")
    FLOG_CHANNEL = _int_or_none("FLOG_CHANNEL")
    ULOG_CHANNEL = _int_or_none("ULOG_CHANNEL")
    NUDENET_CHANNEL = _int_or_none("NUDENET_CHANNEL")

    MODE = env.get("MODE", "primary")
    SECONDARY = MODE.lower() == "secondary"

    _auth_raw = str(env.get("AUTH_USERS", "")).split()
    AUTH_USERS = []
    for x in _auth_raw:
        try:
            AUTH_USERS.append(int(x))
        except Exception:
            pass
    AUTH_USERS = list(set(AUTH_USERS))

    # --- [ URL SHORTENER CONFIG ] ---
    URL_SHORTENER_API_KEY = env.get("URL_SHORTENER_API_KEY", None)
    URL_SHORTENER_SITE = env.get("URL_SHORTENER_SITE", None)


class Server:
    PORT = _int_env("PORT", 8080)
    BIND_ADDRESS = str(env.get("BIND_ADDRESS", "0.0.0.0"))
    PING_INTERVAL = _int_env("PING_INTERVAL", 1200)
    HAS_SSL = str(env.get("HAS_SSL", "0")).lower() in ("1", "true", "t", "yes", "y")
    NO_PORT = str(env.get("NO_PORT", "0")).lower() in ("1", "true", "t", "yes", "y")
    STREAM_CHUNK_SIZE_MB = max(1, _int_env("STREAM_CHUNK_SIZE_MB", 1))
    STREAM_PREFETCH_CHUNKS = max(1, min(_int_env("STREAM_PREFETCH_CHUNKS", 4), 8))
    STREAM_LOCAL_CACHE_ENABLED = _bool_env("STREAM_LOCAL_CACHE_ENABLED", True)
    STREAM_CACHE_DIR = _str_env("STREAM_CACHE_DIR", "/tmp/filestream_stream_cache")
    STREAM_CACHE_MAX_GB = max(_float_env("STREAM_CACHE_MAX_GB", 10.0), 0.0)
    STREAM_CACHE_TTL_HOURS = max(_float_env("STREAM_CACHE_TTL_HOURS", 24.0), 0.0)
    _raw_fqdn = str(env.get("FQDN", BIND_ADDRESS))
    parsed = urlparse(_raw_fqdn if "://" in _raw_fqdn else f"//{_raw_fqdn}")
    FQDN = parsed.netloc or parsed.path
    has_port = parsed.port is not None
    URL = "http{}://{}{}/".format(
        "s" if HAS_SSL else "", FQDN, "" if (NO_PORT or has_port) else ":" + str(PORT)
    )


class WebAds:
    ENABLED = _bool_env("WEB_ADS_ENABLED", True)

    DESKTOP_TOP_BANNER_KEY = _str_env("WEB_ADS_DESKTOP_TOP_BANNER_KEY", "9626363529c248162c9238de39d16745")
    DESKTOP_TOP_BANNER_WIDTH = int(env.get("WEB_ADS_DESKTOP_TOP_BANNER_WIDTH", "728"))
    DESKTOP_TOP_BANNER_HEIGHT = int(env.get("WEB_ADS_DESKTOP_TOP_BANNER_HEIGHT", "90"))
    DESKTOP_TOP_BANNER_INVOKE_URL = _str_env(
        "WEB_ADS_DESKTOP_TOP_BANNER_INVOKE_URL",
        "https://www.highperformanceformat.com/9626363529c248162c9238de39d16745/invoke.js",
    )

    DESKTOP_INLINE_BANNER_KEY = _str_env("WEB_ADS_DESKTOP_INLINE_BANNER_KEY", "49d82824df1bb87901c1aeb13d4a5185")
    DESKTOP_INLINE_BANNER_WIDTH = int(env.get("WEB_ADS_DESKTOP_INLINE_BANNER_WIDTH", "300"))
    DESKTOP_INLINE_BANNER_HEIGHT = int(env.get("WEB_ADS_DESKTOP_INLINE_BANNER_HEIGHT", "250"))
    DESKTOP_INLINE_BANNER_INVOKE_URL = _str_env(
        "WEB_ADS_DESKTOP_INLINE_BANNER_INVOKE_URL",
        "https://www.highperformanceformat.com/49d82824df1bb87901c1aeb13d4a5185/invoke.js",
    )

    MOBILE_TOP_BANNER_KEY = _str_env("WEB_ADS_MOBILE_TOP_BANNER_KEY", "92fbe91aad2179437131dbabf96fc28c")
    MOBILE_TOP_BANNER_WIDTH = int(env.get("WEB_ADS_MOBILE_TOP_BANNER_WIDTH", "320"))
    MOBILE_TOP_BANNER_HEIGHT = int(env.get("WEB_ADS_MOBILE_TOP_BANNER_HEIGHT", "50"))
    MOBILE_TOP_BANNER_INVOKE_URL = _str_env(
        "WEB_ADS_MOBILE_TOP_BANNER_INVOKE_URL",
        "https://www.highperformanceformat.com/92fbe91aad2179437131dbabf96fc28c/invoke.js",
    )

    MOBILE_BOTTOM_BANNER_KEY = _str_env("WEB_ADS_MOBILE_BOTTOM_BANNER_KEY", "49d82824df1bb87901c1aeb13d4a5185")
    MOBILE_BOTTOM_BANNER_WIDTH = int(env.get("WEB_ADS_MOBILE_BOTTOM_BANNER_WIDTH", "300"))
    MOBILE_BOTTOM_BANNER_HEIGHT = int(env.get("WEB_ADS_MOBILE_BOTTOM_BANNER_HEIGHT", "250"))
    MOBILE_BOTTOM_BANNER_INVOKE_URL = _str_env(
        "WEB_ADS_MOBILE_BOTTOM_BANNER_INVOKE_URL",
        "https://www.highperformanceformat.com/49d82824df1bb87901c1aeb13d4a5185/invoke.js",
    )

    DESKTOP_SOCIAL_BAR_URL = _str_env(
        "WEB_ADS_DESKTOP_SOCIAL_BAR_URL",
        "https://cardinaltangible.com/27/fa/cf/27facf136dc45ce0b5faf7b999e9e6f0.js",
    )
    MOBILE_SOCIAL_BAR_URL = _str_env(
        "WEB_ADS_MOBILE_SOCIAL_BAR_URL",
        "https://cardinaltangible.com/27/fa/cf/27facf136dc45ce0b5faf7b999e9e6f0.js",
    )
    SMARTLINK_URL = _str_env(
        "WEB_ADS_SMARTLINK_URL",
        "https://cardinaltangible.com/jpxjm6h69?key=654ea398985fb67f67bc8d74aecdedcf",
    )

    @classmethod
    def _banner_slot(
        cls,
        device: str,
        key: str,
        width: int,
        height: int,
        invoke_url: str,
        *,
        enabled_override: bool | None = None,
    ) -> dict:
        key = str(key or "").strip()
        invoke_url = str(invoke_url or "").strip()
        enabled_flag = cls.ENABLED if enabled_override is None else bool(enabled_override)
        enabled = enabled_flag and bool(key and invoke_url and width and height)
        return {
            "device": device,
            "key": key,
            "width": int(width or 0),
            "height": int(height or 0),
            "invoke_url": invoke_url,
            "enabled": enabled,
        }

    @classmethod
    def template_context(cls, enabled_override: bool | None = None) -> dict:
        enabled_flag = cls.ENABLED if enabled_override is None else bool(enabled_override)
        desktop_top = cls._banner_slot(
            "desktop",
            cls.DESKTOP_TOP_BANNER_KEY,
            cls.DESKTOP_TOP_BANNER_WIDTH,
            cls.DESKTOP_TOP_BANNER_HEIGHT,
            cls.DESKTOP_TOP_BANNER_INVOKE_URL,
            enabled_override=enabled_flag,
        )
        desktop_inline = cls._banner_slot(
            "desktop",
            cls.DESKTOP_INLINE_BANNER_KEY,
            cls.DESKTOP_INLINE_BANNER_WIDTH,
            cls.DESKTOP_INLINE_BANNER_HEIGHT,
            cls.DESKTOP_INLINE_BANNER_INVOKE_URL,
            enabled_override=enabled_flag,
        )
        mobile_top = cls._banner_slot(
            "mobile",
            cls.MOBILE_TOP_BANNER_KEY,
            cls.MOBILE_TOP_BANNER_WIDTH,
            cls.MOBILE_TOP_BANNER_HEIGHT,
            cls.MOBILE_TOP_BANNER_INVOKE_URL,
            enabled_override=enabled_flag,
        )
        mobile_bottom = cls._banner_slot(
            "mobile",
            cls.MOBILE_BOTTOM_BANNER_KEY,
            cls.MOBILE_BOTTOM_BANNER_WIDTH,
            cls.MOBILE_BOTTOM_BANNER_HEIGHT,
            cls.MOBILE_BOTTOM_BANNER_INVOKE_URL,
            enabled_override=enabled_flag,
        )

        desktop_social_bar_url = cls.DESKTOP_SOCIAL_BAR_URL if enabled_flag else ""
        mobile_social_bar_url = cls.MOBILE_SOCIAL_BAR_URL if enabled_flag else ""

        return {
            "enabled": enabled_flag,
            "desktop": {
                "top_banner": desktop_top,
                "inline_banner": desktop_inline,
                "social_bar_url": desktop_social_bar_url,
            },
            "mobile": {
                "top_banner": mobile_top,
                "bottom_banner": mobile_bottom,
                "social_bar_url": mobile_social_bar_url,
            },
            "smartlink_url": cls.SMARTLINK_URL if enabled_flag else "",
            "has_any_banner": any(
                slot["enabled"] for slot in (desktop_top, desktop_inline, mobile_top, mobile_bottom)
            ),
            "has_any_social_bar": bool(desktop_social_bar_url or mobile_social_bar_url),
        }


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
