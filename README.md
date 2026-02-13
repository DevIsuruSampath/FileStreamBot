<h1 align="center">FileStreamBot</h1>
<p align="center">
  <a href="https://github.com/Avipatilpro/FileStreamBot">
    <img src="https://graph.org/file/80d1f94e81bbc1acadb36.jpg" alt="Cover Image" width="550">
  </a>
</p>  
  <p align="center">
   </strong></a>
    <br><b>
    <a href="https://github.com/Avipatilpro/FileStreamBot/issues">Report a Bug</a>
    |
    <a href="https://github.com/Avipatilpro/FileStreamBot/issues">Request Feature</a></b>
  </p>



### 🍁 About :

<p align="center">
    <a href="https://github.com/Avipatilpro/FileStreamBot">
        <img src="https://i.ibb.co/ZJzJ9Hq/link-3x.png" height="100" width="100" alt="FileStreamBot Logo">
    </a>
</p>
<p align='center'>
  This bot provides stream links for Telegram files without the necessity of waiting for the download to complete, offering the ability to store files.
</p>


### ♢ How to Deploy :

<i>Either you could locally host, VPS, or deploy on [Heroku](https://heroku.com)</i>

#### ♢ Click on This Drop-down and get more details

<br>
<details>
  <summary><b>Deploy on Heroku (Paid)  :</b></summary>

- Fork This Repo
- Click on Deploy Easily
- Press the below button to Fast deploy on Heroku


   [![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)
- Go to <a href="#mandatory-vars">variables tab</a> for more info on setting up environmental variables. </details>

<details>
  <summary><b>Deploy Locally :</b></summary>
<br>

```sh
git clone https://github.com/avipatilpro/FileStreamBot
cd FileStreamBot
python3 -m venv ./venv
. ./venv/bin/activate
pip install -r requirements.txt
python3 -m FileStream
```

- To stop the whole bot,
 do <kbd>CTRL</kbd>+<kbd>C</kbd>

- If you want to run this bot 24/7 on the VPS, follow these steps.
```sh
sudo apt install tmux -y
tmux
python3 -m FileStream
```
- now you can close the VPS and the bot will run on it.

  </details>

<details>
  <summary><b>Deploy using Docker :</b></summary>
<br>
* Clone the repository:
```sh
git clone https://github.com/avipatilpro/FileStreamBot
cd FileStreamBot
```
* Build own Docker image:
```sh
docker build -t file-stream .
```

* Create ENV and Start Container:
```sh
docker run -d --restart unless-stopped --name fsb \
-v /PATH/TO/.env:/app/.env \
-p 8000:8000 \
file-stream
```
- if you need to change the variables in .env file after your bot was already started, all you need to do is restart the container for the bot settings to get updated:
```sh
docker restart fsb
```

  </details>

<details>
  <summary><b>Setting up things :</b></summary>


### 1) Create your environment file (required)

If you are deploying on Heroku/Render/Koyeb, set these values in the platform environment variables.
If you are running locally or on VPS, create `.env` in project root:

```sh
cp .env.example .env
```

Then edit `.env` and fill all mandatory values.

### 2) Mandatory environment variables

- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `OWNER_ID`
- `FLOG_CHANNEL`
- `ULOG_CHANNEL`
- `DATABASE_URL`
- `FQDN`

> ⚠️ Bot will not start correctly if mandatory vars are missing.

### 3) Force-subscribe settings

- `FORCE_SUB_ID`: channel ID (usually starts with `-100...`)
- `FORCE_SUB`: `True` / `False`
- `UPDATES_CHANNEL`: optional username without `@`

This repo now supports both:
- `FORCE_SUB` (recommended)
- `FORCE_UPDATES_CHANNEL` (legacy compatibility)

### 4) Example `.env`

```sh
API_ID=123456
API_HASH=your_api_hash
BOT_TOKEN=123456:your_bot_token
OWNER_ID=123456789
FLOG_CHANNEL=-1001234567890
ULOG_CHANNEL=-1001234567890
DATABASE_URL=mongodb://user:pass@host:27017
FQDN=example.com
FORCE_SUB=False
PORT=8080
```
</details>


<details>
  <summary><b>Vars and Details :</b></summary>

#### 📝 Mandatory Vars :

* `API_ID`: API ID of your Telegram account from [my.telegram.org](https://my.telegram.org). `int`
* `API_HASH`: API hash of your Telegram account from [my.telegram.org](https://my.telegram.org). `str`
* `BOT_TOKEN`: Telegram bot token from [@BotFather](https://t.me/BotFather). `str`
* `OWNER_ID`: Your Telegram User ID. `int`
* `FLOG_CHANNEL`: Channel ID where user files are stored. `int`
* `ULOG_CHANNEL`: Channel ID where new-user logs are sent. `int`
* `DATABASE_URL`: MongoDB URI. `str`
* `FQDN`: Public domain/IP used for generated links (without `http/s`). `str`

#### 🗼 MultiClient Vars :
* `MULTI_TOKEN1`: First bot token/session string. `str`
* `MULTI_TOKEN2`: Second bot token/session string. `str`

#### 🪐 Optional Vars :

* `WORKERS`: Max concurrent workers. Default `6`. `int`
* `UPDATES_CHANNEL`: Update channel username without `@`. `str`
* `FORCE_SUB_ID`: Force-subscribe channel ID. Usually starts with `-100`. `str`
* `FORCE_SUB`: Force subscribe switch (`True` / `False`). `bool`
* `FORCE_UPDATES_CHANNEL`: Legacy alias for `FORCE_SUB`. `bool`
* `AUTH_USERS`: Space-separated authorized user IDs. `int list`
* `SLEEP_THRESHOLD`: Flood-wait auto-retry threshold. Default `60`. `int`
* `SESSION_NAME`: DB session name. Default `FileStream`. `str`
* `FILE_PIC`: Image for `/files` command. `str`
* `START_PIC`: Image for `/start` command. `str`
* `VERIFY_PIC`: Image for force-sub verification. `str`
* `PORT`: Web app port. Default `8080`. `int`
* `BIND_ADDRESS`: Bind address. Default `0.0.0.0`. `str`
* `MODE`: Set `secondary` to run serving mode only. `str`
* `NO_PORT`: Hide port in generated links (`True`/`False`). `bool`
* `HAS_SSL`: Use `https` links (`True`/`False`). `bool`
* `URL_SHORTENER_SITE`: Optional shortener provider/site id (for GPLinks use `api.gplinks.com`). `str`
* `URL_SHORTENER_API_KEY`: Optional shortener API key. `str`
* `URL_SHORTENER_TIMEOUT`: Shortener API request timeout in seconds. Default `5`. `float`
* `URL_SHORTENER_FAIL_THRESHOLD`: Failures before shortener cooldown starts. Default `2`. `int`
* `URL_SHORTENER_COOLDOWN`: Cooldown duration in seconds after repeated failures. Default `300`. `int`

#### 🔒 NudeNet (NSFW Block)
* `NUDENET_ENABLE`: Enable NudeNet scanning. Defaults to `True`.
* `NUDENET_THRESHOLD`: Score threshold (0-1). Defaults to `0.6`.
* `NUDENET_SCAN_IMAGES`: Scan images. Defaults to `True`.
* `NUDENET_SCAN_VIDEOS`: Scan videos. Defaults to `True`.
* `NUDENET_MAX_VIDEO_FRAMES`: Frames to sample per video. Defaults to `12`.
* `NUDENET_FRAME_INTERVAL`: Seconds between sampled frames. Defaults to `5`.
* `NUDENET_BLOCK_ON_ERROR`: Block if scan fails. Defaults to `False`.
* `NUDENET_TEMP_DIR`: Temp path for scans. Defaults to `/tmp/filestream_nsfw`.
* `NUDENET_CHANNEL`: Channel ID for NSFW reports.

</details>

<details>
  <summary><b>How to Use :</b></summary>

:warning: **Before using the  bot, don't forget to add the bot to the `LOG_CHANNEL` as an Admin**
 
#### ‍☠️ Bot Commands :

```sh
/start      : To check the bot is alive or not.
/help       : To Get Help Message.
/about      : To check About the Bot.
/files      : To Get All Files List of User.
/del        : To Delete Files from DB with FileID. [ADMIN]
/ban        : To Ban Any Channel or User to use bot. [ADMIN]
/unban      : To Unban Any Channel or User to use bot. [ADMIN]
/status     : To Get Bot Status and Total Users. [ADMIN]
/broadcast  : To Broadcast any message to all users of bot. [ADMIN]
```

#### 🍟 Channel Support :

*Bot also Supported with Channels. Just add bot Channel as Admin. If any new file comes in Channel it will edit it with **Get Download Link** Button.*

</details>

### ❤️ Thanks To :

- [**Me**](https://github.com/AvishkarPatil) : Owner of This FileStreamBot
- [**Deekshith SH**](https://github.com/DeekshithSH) : for some modules.
- [**EverythingSuckz**](https://github.com/EverythingSuckz) : for his [FileStreamBot](https://github.com/EverythingSuckz/FileStreamBot)
- [**Biisal**](https://github.com/biisal) : for Stream Page UI

---
<h4 align='center'>© 2024 Aνιѕнкαя Pαтιℓ</h4>



