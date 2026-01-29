import asyncio
import logging
import cloudscraper
from abc import ABC, abstractmethod
from base64 import b64encode
from random import random, choice
from urllib.parse import quote
from functools import partial

from FileStream.config import Telegram

# Configure Logger
logger = logging.getLogger(__name__)

class ShortenerPlugin(ABC):
    @classmethod
    @abstractmethod
    def matches(cls, domain: str) -> bool:
        pass
    
    @abstractmethod
    def shorten(self, url: str, api_key: str) -> str:
        """
        Note: Removed 'async' to allow running in executor 
        since cloudscraper is synchronous.
        """
        pass

class LinkvertisePlugin(ShortenerPlugin):
    @classmethod
    def matches(cls, domain: str) -> bool:
        return "linkvertise" in domain
    
    def shorten(self, url: str, api_key: str) -> str:
        encoded_url = quote(b64encode(url.encode("utf-8")))
        return choice([
            f"https://link-to.net/{api_key}/{random() * 1000}/dynamic?r={encoded_url}",
            f"https://up-to-down.net/{api_key}/{random() * 1000}/dynamic?r={encoded_url}",
            f"https://direct-link.net/{api_key}/{random() * 1000}/dynamic?r={encoded_url}",
            f"https://file-link.net/{api_key}/{random() * 1000}/dynamic?r={encoded_url}",
        ])

class BitlyPlugin(ShortenerPlugin):
    @classmethod
    def matches(cls, domain: str) -> bool:
        return "bitly.com" in domain
    
    def shorten(self, url: str, api_key: str) -> str:
        if not self.session:
            return url
        response = self.session.post(
            "https://api-ssl.bit.ly/v4/shorten",
            json={"long_url": url},
            headers={"Authorization": f"Bearer {api_key}"}
        )
        if response.status_code == 200:
            return response.json()["link"]
        return url

class OuoIoPlugin(ShortenerPlugin):
    @classmethod
    def matches(cls, domain: str) -> bool:
        return "ouo.io" in domain
    
    def shorten(self, url: str, api_key: str) -> str:
        if not self.session:
            return url
        response = self.session.get(f"http://ouo.io/api/{api_key}?s={url}")
        if response.status_code == 200 and response.text:
            return response.text
        return url

class CuttLyPlugin(ShortenerPlugin):
    @classmethod
    def matches(cls, domain: str) -> bool:
        return "cutt.ly" in domain
    
    def shorten(self, url: str, api_key: str) -> str:
        if not self.session:
            return url
        response = self.session.get(f"http://cutt.ly/api/api.php?key={api_key}&short={url}")
        if response.status_code == 200:
            return response.json()["url"]["shortLink"]
        return url

class GenericShortenerPlugin(ShortenerPlugin):
    @classmethod
    def matches(cls, domain: str) -> bool:
        return True
    
    def shorten(self, url: str, api_key: str) -> str:
        if not self.session:
            return url
        try:
            # Standard Shortener API format
            target_url = f"https://{self.domain}/api?api={api_key}&url={quote(url)}"
            response = self.session.get(target_url)
            if response.status_code == 200:
                data = response.json()
                return data.get("shortenedUrl", url)
        except Exception as e:
            logger.error(f"Generic Shortener Error: {e}")
        return url

class ShortenerSystem:
    def __init__(self):
        self.session = None
        self.plugin = None
        self.ready = False
    
    def _get_plugin_class(self, domain: str):
        for plugin_class in ShortenerPlugin.__subclasses__():
            if plugin_class.matches(domain):
                return plugin_class
        return GenericShortenerPlugin
    
    async def initialize(self) -> bool:
        if self.ready:
            return True
        
        # Get Config from Telegram class
        site = getattr(Telegram, "URL_SHORTENER_SITE", "")
        api_key = getattr(Telegram, "URL_SHORTENER_API_KEY", "")
        
        if not (site and api_key):
            logger.warning("Shortener Config missing: SITE or API_KEY not set.")
            return False
        
        try:
            # Run cloudscraper creation in thread to avoid blocking startup
            self.session = await asyncio.get_running_loop().run_in_executor(
                None,
                partial(
                    cloudscraper.create_scraper,
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'desktop': True,
                        'mobile': False
                    },
                    delay=1
                )
            )
            
            plugin_class = self._get_plugin_class(site)
            self.plugin = plugin_class()
            self.plugin.session = self.session
            self.plugin.domain = site
            self.ready = True
            logger.info(f"Shortener System Initialized for: {site}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ShortenerSystem: {e}", exc_info=True)
            return False
    
    async def short_url(self, url: str) -> str:
        if not self.ready:
            if not await self.initialize():
                return url
        
        try:
            # cloudscraper is blocking, so we run the shorten method in a separate thread
            # to keep the bot responsive.
            return await asyncio.get_running_loop().run_in_executor(
                None, 
                self.plugin.shorten, 
                url, 
                Telegram.URL_SHORTENER_API_KEY
            )
        except Exception as e:
            logger.error(f"Error shortening URL {url}: {e}", exc_info=True)
            return url

_system = ShortenerSystem()

async def shorten(url: str) -> str:
    if not _system.ready:
        await _system.initialize()
    return await _system.short_url(url)

# Alias for backward compatibility with bot_utils.py
get_short_link = shorten
