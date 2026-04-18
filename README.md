# 🚀 FileStreamBot

A powerful, high-performance Telegram bot that streams files directly from Telegram channels to the web. Watch videos and download files instantly without waiting, with no server storage required.

<p align="center">
  <img src="https://graph.org/file/80d1f94e81bbc1acadb36.jpg" alt="FileStreamBot Cover" width="600">
</p>

<p align="center">
    <a href="https://github.com/Avipatilpro/FileStreamBot/issues">Report Bug</a>
    ·
    <a href="https://github.com/Avipatilpro/FileStreamBot/issues">Request Feature</a>
</p>

## ✨ Features

- **Stream Instantly:** Stream directly from Telegram, with optional local hot-chunk caching for repeat downloads.
- **Multi-Client Support:** Add multiple bot sessions to handle heavy traffic and bypass limits.
- **Web Player:** Integrated HTML5 video player (Plyr) for seamless watching.
- **Direct Download Links:** Generate fast, resume-supported download links.
- **Force Subscribe:** Require users to join a channel before using the bot.
- **NSFW Detection:** Optional automatic scanning and blocking of NSFW content (using NudeNet).
- **URL Shortener:** Monetize links with integrated shortener support.
- **Banning System:** Ban abusive users or channels.
- **Broadcast:** Send messages to all bot users.
- **Customizable:** Easily configure images, text, and settings via environment variables.

## 🛠 Deployment

You can deploy this bot on Heroku, Render, VPS, or locally.

### ⚡ One-Click Deploy (Heroku)

[![Deploy on Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Avipatilpro/FileStreamBot)

### 🐳 Deploy with Docker

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/avipatilpro/FileStreamBot
    cd FileStreamBot
    ```

2.  **Build the image:**
    ```bash
    docker build -t file-stream .
    ```

3.  **Run the container:**
    ```bash
    docker run -d --restart unless-stopped --name fsb \
      -v $(pwd)/.env:/app/.env \
      -p 8080:8080 \
      file-stream
    ```

### 🖥️ Local / VPS Deployment

1.  **Clone and install dependencies:**
    ```bash
    git clone https://github.com/avipatilpro/FileStreamBot
    cd FileStreamBot
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

2.  **Configure environment:**
    ```bash
    cp example.env .env
    nano .env  # Add your variables
    ```

3.  **Run the bot:**
    ```bash
    python3 -m FileStream
    ```

## ⚙️ Environment Variables

Create a `.env` file with the following (or set them in your cloud provider):

### Core Required
- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `BOT_TOKEN`: Your Bot Token from @BotFather.
  The bot username is auto-detected from this token at runtime. No separate bot username setting is required.
- `OWNER_ID`: Your Telegram User ID.
- `DATABASE_URL`: MongoDB Connection URI.
- `FQDN`: Your public domain or IP (e.g., `files.example.com`).

### Recommended Channels
- `FLOG_CHANNEL`: Strongly recommended primary cache channel used to keep per-client file IDs in sync for stable streaming and multi-client mode.
- `ADMIN_FLOG_CHANNEL`: Optional second cache/storage channel. Admins can switch new uploads between `FLOG_CHANNEL` and `ADMIN_FLOG_CHANNEL` with `/flogstorage`.
- `ULOG_CHANNEL`: Optional channel ID for new user logs and error logs.
- `BIN_CHANNEL`: Optional legacy storage channel. Current code primarily uses `FLOG_CHANNEL`.
- `NUDENET_CHANNEL`: Optional review/moderation channel for NSFW reports.

### Optional
- `MULTI_TOKEN1`, `MULTI_TOKEN2`: Additional bot tokens for load balancing and user-facing bot replies.
- `MULTI_TOKEN3` ... `MULTI_TOKENN`: You can continue numbering upward for more bots.
- `WORKERS`: Number of workers (Default: 6).
- `PORT`: Web server port (Default: `8080`).
- `BIND_ADDRESS`: Web server bind address (Default: `0.0.0.0`).
- `PING_INTERVAL`: Health/ping interval for the web process (Default: 1200).
- `HAS_SSL`: Generate `https://` links when your reverse proxy/domain uses SSL.
- `NO_PORT`: Hide the explicit port from generated links when your proxy already terminates on the public host.
- `STREAM_CHUNK_SIZE_MB`: Telegram stream chunk size in MB (Default: `1`). Telegram only allows `1 MB` here, so higher values are clamped to `1`.
- `STREAM_PREFETCH_CHUNKS`: Number of Telegram chunks to keep in-flight per stream (Default: `4`, max: `8`).
- `STREAM_LOCAL_CACHE_ENABLED`: Enable local disk cache for hot stream chunks (Default: `True`).
- `STREAM_CACHE_DIR`: Directory for local stream chunk cache (Default: `/tmp/filestream_stream_cache`).
- `STREAM_CACHE_MAX_GB`: Max local stream cache size in GB before old chunks are pruned (Default: `10`).
- `STREAM_CACHE_TTL_HOURS`: How long cached chunks stay valid before pruning (Default: `24`).
- `SESSION_NAME`: Mongo database/session namespace (Default: `FileStream`).
- `AUTH_USERS`: Space-separated user IDs allowed to use the bot when access restriction is enabled.
- `MODE`: Use `secondary` if you only want server-side file serving.
- `UPDATES_CHANNEL`: Public updates channel username shown to users.
- Multi-token note: every `MULTI_TOKEN*` bot now starts with updates enabled, uses the same handlers as the primary bot, and generates its own bot-specific `/start` links/buttons during active chats.
- `FORCE_SUB_ID`: Channel ID for force subscription.
- `FORCE_SUB`: Set to `True` to enable.
- `FORCE_UPDATES_CHANNEL`: Legacy alias for `FORCE_SUB`.
- `NUDENET_ENABLE`: Set to `True` to enable NSFW scanning.
- `NUDENET_BLOCK_ON_ERROR`: Block content if a scan fails.
- `NUDENET_THRESHOLD`: NSFW score threshold (Default: `0.6`).
- `NUDENET_SCAN_IMAGES`: Scan images for adult content.
- `NUDENET_SCAN_VIDEOS`: Scan videos for adult content.
- `NUDENET_MAX_VIDEO_FRAMES`: Max sampled frames per video.
- `NUDENET_FRAME_INTERVAL`: Seconds between sampled frames.
- `NUDENET_TEMP_DIR`: Temporary directory used during scans.
- `URL_SHORTENER_SITE`: Shortener domain (e.g., `api.gplinks.com`).
- `URL_SHORTENER_API_KEY`: API Key for the shortener.
- `URL_SHORTENER_TIMEOUT`: Shortener request timeout in seconds.
- `URL_SHORTENER_FAIL_THRESHOLD`: Failures before shortener cooldown starts.
- `URL_SHORTENER_COOLDOWN`: Cooldown duration in seconds after repeated failures.
- `FILE_PIC`: Image for `/files` command. Supports an HTTP URL, Telegram `file_id`, or a local path like `images/files.png`.
- `FOLDERS_PIC`: Image for `/folders` command. Supports an HTTP URL, Telegram `file_id`, or a local path like `images/folders.png`.
- `START_PIC`: Image for `/start` command. Supports an HTTP URL, Telegram `file_id`, or a local path like `images/start.png`.
- `VERIFY_PIC`: Image for force subscribe verification. Supports an HTTP URL, Telegram `file_id`, or a local path like `images/verify.png`.
- `WEB_ADS_ENABLED`: Set to `True`/`False` to globally enable or disable web ad slots and social bar scripts.
- `WEB_ADS_DESKTOP_TOP_BANNER_KEY`, `WEB_ADS_DESKTOP_TOP_BANNER_INVOKE_URL`, `WEB_ADS_DESKTOP_TOP_BANNER_WIDTH`, `WEB_ADS_DESKTOP_TOP_BANNER_HEIGHT`: Desktop top banner slot config. Defaults keep the current `728x90` placement.
- `WEB_ADS_DESKTOP_INLINE_BANNER_KEY`, `WEB_ADS_DESKTOP_INLINE_BANNER_INVOKE_URL`, `WEB_ADS_DESKTOP_INLINE_BANNER_WIDTH`, `WEB_ADS_DESKTOP_INLINE_BANNER_HEIGHT`: Desktop inline banner slot config. Defaults keep the current `300x250` placement.
- `WEB_ADS_MOBILE_TOP_BANNER_KEY`, `WEB_ADS_MOBILE_TOP_BANNER_INVOKE_URL`, `WEB_ADS_MOBILE_TOP_BANNER_WIDTH`, `WEB_ADS_MOBILE_TOP_BANNER_HEIGHT`: Mobile top banner slot config. Defaults keep the current `320x50` placement.
- `WEB_ADS_MOBILE_BOTTOM_BANNER_KEY`, `WEB_ADS_MOBILE_BOTTOM_BANNER_INVOKE_URL`, `WEB_ADS_MOBILE_BOTTOM_BANNER_WIDTH`, `WEB_ADS_MOBILE_BOTTOM_BANNER_HEIGHT`: Mobile bottom banner slot config. Defaults keep the current `300x250` placement.
- `WEB_ADS_DESKTOP_SOCIAL_BAR_URL`: Desktop social bar script URL. Defaults to the current hardcoded value.
- `WEB_ADS_MOBILE_SOCIAL_BAR_URL`: Mobile social bar script URL. Defaults to the current hardcoded value.
- `WEB_ADS_SMARTLINK_URL`: Smartlink/click-through URL used by the web ad gate. Defaults to the current hardcoded value.

### Web Ads Notes
- Leave a banner `*_KEY` or `*_INVOKE_URL` blank to disable just that placement gracefully.
- Leave a social bar URL blank to disable that social bar gracefully.
- If you do not set any of the new web ads variables, FileStreamBot keeps the current ad behavior by using the existing hardcoded values as defaults in config.
- The repo template file is `example.env`; copy it to `.env` before running locally.

## 🧰 Admin Toggles

- `/urlshortener` → Show URL shortener status.
- `/urlshortener on|off` → Enable/disable URL shortener monetization.

> Legacy `/ads` is still accepted as an alias for `/urlshortener`.

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

<p align="center">© 2024 FileStreamBot</p>
