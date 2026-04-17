import asyncio
import contextlib
import logging
from typing import Dict, Union
from FileStream.bot import work_loads
from FileStream.config import Server
from pyrogram import Client, utils, raw
from .file_properties import get_file_ids
from .client_balance import ensure_client_stat, record_stream_completed, record_stream_failed
from .stream_cache import stream_cache
from pyrogram.session import Session, Auth
from pyrogram.errors import AuthBytesInvalid
from pyrogram.file_id import FileId, FileType, ThumbnailSource
from pyrogram.types import Message

class ByteStreamer:
    def __init__(self, client: Client):
        self.clean_timer = 30 * 60
        self.client: Client = client
        self.cached_file_ids: Dict[str, FileId] = {}
        asyncio.create_task(self.clean_cache())

    async def get_file_properties(self, db_id: str, multi_clients) -> FileId:
        """
        Returns the properties of a media of a specific message in a FIleId class.
        if the properties are cached, then it'll return the cached results.
        or it'll generate the properties from the Message ID and cache them.
        """
        if not db_id in self.cached_file_ids:
            logging.debug("Before Calling generate_file_properties")
            await self.generate_file_properties(db_id, multi_clients)
            logging.debug(f"Cached file properties for file with ID {db_id}")
        return self.cached_file_ids[db_id]
    
    async def generate_file_properties(self, db_id: str, multi_clients) -> FileId:
        """
        Generates the properties of a media file on a specific message.
        returns ths properties in a FIleId class.
        """
        logging.debug("Before calling get_file_ids")
        file_id = await get_file_ids(self.client, db_id, multi_clients, None)
        logging.debug(f"Generated file ID and Unique ID for file with ID {db_id}")
        self.cached_file_ids[db_id] = file_id
        logging.debug(f"Cached media file with ID {db_id}")
        return self.cached_file_ids[db_id]

    async def reset_media_session(self, client: Client, dc_id: int) -> None:
        media_session = client.media_sessions.pop(dc_id, None)
        if media_session is None:
            return
        with contextlib.suppress(Exception):
            await media_session.stop()

    async def generate_media_session(self, client: Client, file_id: FileId, *, refresh: bool = False) -> Session:
        """
        Generates the media session for the DC that contains the media file.
        This is required for getting the bytes from Telegram servers.
        """
        if refresh:
            await self.reset_media_session(client, file_id.dc_id)

        media_session = client.media_sessions.get(file_id.dc_id, None)

        if media_session is None:
            if file_id.dc_id != await client.storage.dc_id():
                media_session = Session(
                    client,
                    file_id.dc_id,
                    await Auth(
                        client, file_id.dc_id, await client.storage.test_mode()
                    ).create(),
                    await client.storage.test_mode(),
                    is_media=True,
                )
                await media_session.start()

                for _ in range(6):
                    exported_auth = await client.invoke(
                        raw.functions.auth.ExportAuthorization(dc_id=file_id.dc_id)
                    )

                    try:
                        await media_session.invoke(
                            raw.functions.auth.ImportAuthorization(
                                id=exported_auth.id, bytes=exported_auth.bytes
                            )
                        )
                        break
                    except AuthBytesInvalid:
                        logging.debug(
                            f"Invalid authorization bytes for DC {file_id.dc_id}"
                        )
                        continue
                else:
                    with contextlib.suppress(Exception):
                        await media_session.stop()
                    await self.reset_media_session(client, file_id.dc_id)
                    raise AuthBytesInvalid
            else:
                media_session = Session(
                    client,
                    file_id.dc_id,
                    await client.storage.auth_key(),
                    await client.storage.test_mode(),
                    is_media=True,
                )
                await media_session.start()
            logging.debug(f"Created media session for DC {file_id.dc_id}")
            client.media_sessions[file_id.dc_id] = media_session
        else:
            logging.debug(f"Using cached media session for DC {file_id.dc_id}")
        return media_session


    @staticmethod
    async def get_location(file_id: FileId) -> Union[raw.types.InputPhotoFileLocation,
                                                     raw.types.InputDocumentFileLocation,
                                                     raw.types.InputPeerPhotoFileLocation,]:
        """
        Returns the file location for the media file.
        """
        file_type = file_id.file_type

        if file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id, access_hash=file_id.chat_access_hash
                )
            else:
                if file_id.chat_access_hash == 0:
                    peer = raw.types.InputPeerChat(chat_id=-file_id.chat_id)
                else:
                    peer = raw.types.InputPeerChannel(
                        channel_id=utils.get_channel_id(file_id.chat_id),
                        access_hash=file_id.chat_access_hash,
                    )

            location = raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
        elif file_type == FileType.PHOTO:
            location = raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )
        else:
            location = raw.types.InputDocumentFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )
        return location

    async def yield_file(
        self,
        file_key: str,
        file_id: FileId,
        index: int,
        offset: int,
        first_part_cut: int,
        last_part_cut: int,
        part_count: int,
        chunk_size: int,
    ) -> Union[str, None]:
        """
        Custom generator that yields the bytes of the media file.
        Modded from <https://github.com/eyaadh/megadlbot_oss/blob/master/mega/telegram/utils/custom_download.py#L20>
        Thanks to Eyaadh <https://github.com/eyaadh>
        """
        client = self.client
        logging.debug(f"Starting to yielding file with client {index}.")

        loop = asyncio.get_running_loop()
        start_time = loop.time()
        bytes_sent = 0
        telegram_bytes = 0
        telegram_started_at = None
        telegram_first_byte_delay = None
        client_load_acquired = False
        pending_fetch = None
        stream_failed = False

        try:
            current_part = 1
            media_session = None
            location = None
            media_session_lock = asyncio.Lock()
            prefetch_depth = max(1, min(int(Server.STREAM_PREFETCH_CHUNKS), int(part_count), 8))
            pending_fetches: dict[int, asyncio.Task] = {}
            next_part_to_schedule = 1

            async def ensure_media_ready():
                nonlocal media_session, location

                if media_session is not None and location is not None:
                    return media_session, location

                async with media_session_lock:
                    if media_session is not None and location is not None:
                        return media_session, location

                    last_exc = None
                    for attempt in range(2):
                        try:
                            media_session = await self.generate_media_session(
                                client,
                                file_id,
                                refresh=(attempt > 0),
                            )
                            location = await self.get_location(file_id)
                            return media_session, location
                        except AuthBytesInvalid as exc:
                            last_exc = exc
                            logging.warning(
                                "Media session auth failed for DC %s on client %s (attempt %s/2)",
                                file_id.dc_id,
                                index,
                                attempt + 1,
                            )
                            await self.reset_media_session(client, file_id.dc_id)

                    raise last_exc or AuthBytesInvalid

            async def fetch_chunk_from_telegram(part_offset: int) -> bytes:
                nonlocal media_session, location, telegram_started_at, telegram_first_byte_delay, client_load_acquired

                if not client_load_acquired:
                    ensure_client_stat(index)
                    work_loads[index] = work_loads.get(index, 0) + 1
                    client_load_acquired = True

                if telegram_started_at is None:
                    telegram_started_at = loop.time()

                media_session, location = await ensure_media_ready()

                r = await self._fetch_chunk(media_session, location, part_offset, chunk_size)
                if not isinstance(r, raw.types.upload.File):
                    return b""

                chunk = bytes(r.bytes or b"")
                if chunk and telegram_first_byte_delay is None and telegram_started_at is not None:
                    telegram_first_byte_delay = loop.time() - telegram_started_at
                return chunk

            async def get_part(part_number: int):
                part_offset = offset + ((part_number - 1) * chunk_size)
                remaining_bytes = max(int(file_id.file_size or 0) - part_offset, 0)
                expected_size = min(chunk_size, remaining_bytes) if remaining_bytes else chunk_size
                return await stream_cache.get_or_fetch_chunk(
                    file_key=file_key,
                    offset=part_offset,
                    expected_size=expected_size,
                    fetcher=lambda: fetch_chunk_from_telegram(part_offset),
                )

            while next_part_to_schedule <= prefetch_depth:
                pending_fetches[next_part_to_schedule] = asyncio.create_task(
                    get_part(next_part_to_schedule)
                )
                next_part_to_schedule += 1

            try:
                while current_part <= part_count:
                    pending_fetch = pending_fetches.pop(current_part, None)
                    if pending_fetch is None:
                        break
                    chunk, cache_hit = await pending_fetch

                    if next_part_to_schedule <= part_count:
                        pending_fetches[next_part_to_schedule] = asyncio.create_task(
                            get_part(next_part_to_schedule)
                        )
                        next_part_to_schedule += 1

                    if not chunk:
                        break
                    if not cache_hit:
                        telegram_bytes += len(chunk)

                    if part_count == 1:
                        payload = chunk[first_part_cut:last_part_cut]
                    elif current_part == 1:
                        payload = chunk[first_part_cut:]
                    elif current_part == part_count:
                        payload = chunk[:last_part_cut]
                    else:
                        payload = chunk

                    if payload:
                        bytes_sent += len(payload)
                        yield payload

                    current_part += 1
            except (TimeoutError, AttributeError):
                stream_failed = True
                if client_load_acquired:
                    record_stream_failed(index)
            except Exception:
                stream_failed = True
                if client_load_acquired:
                    record_stream_failed(index)
                raise
        finally:
            pending_tasks = []
            if pending_fetch is not None and not pending_fetch.done():
                pending_tasks.append(pending_fetch)
            pending_tasks.extend(task for task in locals().get("pending_fetches", {}).values() if not task.done())
            for task in pending_tasks:
                task.cancel()
            for task in pending_tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            duration = max(loop.time() - start_time, 0.001)
            if client_load_acquired:
                work_loads[index] = max(work_loads.get(index, 1) - 1, 0)

            if telegram_bytes > 0 and not stream_failed:
                telegram_duration = max(loop.time() - (telegram_started_at or start_time), 0.001)
                record_stream_completed(
                    index,
                    bytes_sent=telegram_bytes,
                    duration_s=telegram_duration,
                    first_byte_s=telegram_first_byte_delay,
                )

            logging.debug(f"Finished yielding file with {locals().get('current_part', 0)} parts.")
            logging.debug(
                "Stream duration %.3fs, yielded %s bytes, telegram fetched %s bytes",
                duration,
                bytes_sent,
                telegram_bytes,
            )

    @staticmethod
    async def _fetch_chunk(
        media_session: Session,
        location: Union[
            raw.types.InputPhotoFileLocation,
            raw.types.InputDocumentFileLocation,
            raw.types.InputPeerPhotoFileLocation,
        ],
        offset: int,
        chunk_size: int,
    ):
        return await media_session.invoke(
            raw.functions.upload.GetFile(
                location=location,
                offset=offset,
                limit=chunk_size,
            ),
        )

    
    async def clean_cache(self) -> None:
        """
        function to clean the cache to reduce memory usage
        """
        while True:
            await asyncio.sleep(self.clean_timer)
            self.cached_file_ids.clear()
            logging.debug("Cleaned the cache")
