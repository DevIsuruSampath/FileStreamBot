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

- **Stream Instantly:** No need to download files to the server. Stream directly from Telegram.
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
    cp .env.example .env
    nano .env  # Add your variables
    ```

3.  **Run the bot:**
    ```bash
    python3 -m FileStream
    ```

## ⚙️ Environment Variables

Create a `.env` file with the following (or set them in your cloud provider):

### Mandatory
- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `BOT_TOKEN`: Your Bot Token from @BotFather.
- `OWNER_ID`: Your Telegram User ID.
- `FLOG_CHANNEL`: Channel ID where user files are stored.
- `ULOG_CHANNEL`: Channel ID for new user logs.
- `DATABASE_URL`: MongoDB Connection URI.
- `FQDN`: Your public domain or IP (e.g., `files.example.com`).

### Optional
- `MULTI_TOKEN1`, `MULTI_TOKEN2`: Additional bot tokens for load balancing and user-facing bot replies.
- `MULTI_TOKEN3` ... `MULTI_TOKENN`: You can continue numbering upward for more bots.
- `WORKERS`: Number of workers (Default: 6).
- Multi-token note: every `MULTI_TOKEN*` bot now starts with updates enabled, uses the same handlers as the primary bot, and generates its own bot-specific `/start` links/buttons during active chats.
- `FORCE_SUB_ID`: Channel ID for force subscription.
- `FORCE_SUB`: Set to `True` to enable.
- `NUDENET_ENABLE`: Set to `True` to enable NSFW scanning.
- `URL_SHORTENER_SITE`: Shortener domain (e.g., `api.gplinks.com`).
- `URL_SHORTENER_API_KEY`: API Key for the shortener.
- `FILE_PIC`: Image for `/files` command.
- `FOLDERS_PIC`: Image for `/folders` command.
- `START_PIC`: Image for `/start` command.
- `VERIFY_PIC`: Image for force subscribe verification.

## 🧰 Admin Toggles

- `/urlshortener` → Show URL shortener status.
- `/urlshortener on|off` → Enable/disable URL shortener monetization.

> Legacy `/ads` is still accepted as an alias for `/urlshortener`.

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

<p align="center">© 2024 FileStreamBot</p>
