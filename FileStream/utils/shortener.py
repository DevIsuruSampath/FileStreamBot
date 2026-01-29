import aiohttp
import logging
from FileStream.config import Telegram

async def get_short_link(link):
    # 1. Check if API config exists
    if not Telegram.URL_SHORTENER_API_KEY or not Telegram.URL_SHORTENER_SITE:
        return link

    # 2. Prepare URL (Standard Format: https://site.com/api?api=KEY&url=LINK)
    shortener_url = f"https://{Telegram.URL_SHORTENER_SITE}/api?api={Telegram.URL_SHORTENER_API_KEY}&url={link}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(shortener_url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # 3. Check for common JSON response format
                    if "shortenedUrl" in data:
                        return data["shortenedUrl"]
                    
                    # Some sites might return plain text or different keys
                    return link
                else:
                    logging.error(f"Shortener API Error: {response.status}")
                    return link
    except Exception as e:
        logging.error(f"Shortener Exception: {e}")
        return link
