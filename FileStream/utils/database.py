import asyncio
import pymongo
import time
import mimetypes
import secrets
import motor.motor_asyncio
from bson.objectid import ObjectId
from bson.errors import InvalidId
from FileStream.config import Server, WebAds
from FileStream.server.exceptions import FileNotFound
from FileStream.utils.category import detect_category
from FileStream.utils.runtime_cache import (
    cache_file_info,
    cache_file_reference,
    get_cached_file_info,
    get_cached_file_reference,
    invalidate_file_runtime,
)

class Database:
    _clients: dict[str, motor.motor_asyncio.AsyncIOMotorClient] = {}
    _index_locks: dict[tuple[str, str], asyncio.Lock] = {}
    _indexes_ready: set[tuple[str, str]] = set()

    def __init__(self, uri, database_name):
        self._uri = str(uri)
        self._database_name = str(database_name)
        if self._uri not in self._clients:
            self._clients[self._uri] = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self._client = self._clients[self._uri]
        self.db = self._client[database_name]
        self.col = self.db.users
        self.black = self.db.blacklist
        self.file = self.db.file
        self.settings = self.db.settings  # <--- NEW COLLECTION
        self.folders = self.db.folders
        self.nsfw_reports = self.db.nsfw_reports
        self.public_links = self.db.public_links
        self.donations = self.db.donations

    @staticmethod
    def normalize_file_doc(file_info: dict | None) -> dict | None:
        if not file_info:
            return file_info

        normalized = dict(file_info)
        file_name = normalized.get("file_name") or ""

        mime_type = normalized.get("mime_type") or ""
        if not mime_type and file_name:
            guessed_mime, _ = mimetypes.guess_type(file_name)
            mime_type = guessed_mime or ""

        file_ext = normalized.get("file_ext") or ""
        if not file_ext and file_name:
            import os

            file_ext = os.path.splitext(file_name)[1].lower()

        detected_category = detect_category(
            file_name=file_name,
            mime_type=mime_type,
            file_ext=file_ext,
        )

        current_category = (normalized.get("category") or "").strip()
        if not current_category:
            current_category = detected_category
        elif current_category in {"Movies", "Other"} and detected_category not in {"Movies", "Other"}:
            current_category = detected_category

        normalized["mime_type"] = mime_type
        normalized["file_ext"] = file_ext
        normalized["category"] = current_category
        return normalized

    async def ensure_indexes(self) -> None:
        key = (self._uri, self._database_name)
        if key in self._indexes_ready:
            return

        if key not in self._index_locks:
            self._index_locks[key] = asyncio.Lock()
        lock = self._index_locks[key]
        async with lock:
            if key in self._indexes_ready:
                return

            index_specs = (
                (self.col, [("id", pymongo.ASCENDING)]),
                (self.black, [("id", pymongo.ASCENDING)]),
                (self.file, [("user_id", pymongo.ASCENDING), ("_id", pymongo.DESCENDING)]),
                (self.file, [("user_id", pymongo.ASCENDING), ("file_unique_id", pymongo.ASCENDING)]),
                (self.file, [("flog_msg_id", pymongo.ASCENDING)]),
                (self.file, [("flog_channel_id", pymongo.ASCENDING), ("flog_msg_id", pymongo.ASCENDING)]),
                (self.folders, [("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)]),
                (self.folders, [("files", pymongo.ASCENDING)]),
                (self.public_links, [("type", pymongo.ASCENDING), ("target_id", pymongo.ASCENDING), ("revoked", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)]),
                (self.public_links, [("expires_at", pymongo.ASCENDING)]),
                (self.donations, [("user_id", pymongo.ASCENDING), ("paid_at", pymongo.DESCENDING)]),
                (self.donations, [("telegram_payment_charge_id", pymongo.ASCENDING)]),
            )

            for collection, spec in index_specs:
                try:
                    await collection.create_index(spec)
                except Exception:
                    pass

            self._indexes_ready.add(key)

#---------------------[ NEW USER ]---------------------#
    def new_user(self, id):
        return dict(
            id=id,
            join_date=time.time(),
            Links=0
        )

# ---------------------[ ADD USER ]---------------------#
    async def add_user(self, id):
        # Atomic upsert to prevent duplicates in concurrent calls
        res = await self.col.update_one(
            {"id": int(id)},
            {"$setOnInsert": self.new_user(id)},
            upsert=True,
        )
        return res.upserted_id is not None

# ---------------------[ GET USER ]---------------------#
    async def get_user(self, id):
        user = await self.col.find_one({'id': int(id)})
        return user

# ---------------------[ CHECK USER ]---------------------#
    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        all_users = self.col.find({})
        return all_users

# ---------------------[ REMOVE USER ]---------------------#
    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

# ---------------------[ BAN, UNBAN USER ]---------------------#
    def black_user(self, id):
        return dict(
            id=id,
            ban_date=time.time()
        )

    async def ban_user(self, id):
        user = self.black_user(id)
        await self.black.update_one({"id": int(id)}, {"$setOnInsert": user}, upsert=True)

    async def unban_user(self, id):
        await self.black.delete_many({'id': int(id)})

    async def is_user_banned(self, id):
        user = await self.black.find_one({'id': int(id)})
        return True if user else False

    async def total_banned_users_count(self):
        count = await self.black.count_documents({})
        return count
        
# ---------------------[ ADD FILE TO DB ]---------------------#
    async def add_file(self, file_info):
        file_info = self.normalize_file_doc(dict(file_info))
        file_info["time"] = time.time()
        file_unique_id = file_info.get("file_unique_id")
        if file_unique_id:
            fetch_old = await self.get_file_by_fileuniqueid(file_info["user_id"], file_unique_id)
            if fetch_old:
                await self.ensure_public_link_for_file(fetch_old)
                return fetch_old["_id"]
        await self.count_links(file_info["user_id"], "+")
        inserted_id = (await self.file.insert_one(file_info)).inserted_id
        file_doc = dict(file_info)
        file_doc["_id"] = inserted_id
        await self.ensure_public_link_for_file(file_doc)
        return inserted_id

# ---------------------[ FIND FILE IN DB ]---------------------#
    async def find_files(self, user_id, range):
        start, end = range
        if start > end:
            return self.file.find({"_id": None}), 0
        user_files = (
            self.file.find({"user_id": user_id}, {"_id": 1, "file_name": 1})
            .sort('_id', pymongo.DESCENDING)
            .skip(start - 1)
            .limit(end - start + 1)
        )
        total_files = await self.file.count_documents({"user_id": user_id})
        return user_files, total_files

    async def get_file(self, _id):
        try:
            cache_key = str(_id)
            cached = get_cached_file_info(cache_key)
            if cached:
                return cached

            file_info = await self.file.find_one({"_id": ObjectId(_id)})
            if not file_info:
                raise FileNotFound
            file_info = self.normalize_file_doc(file_info)
            cache_file_info(file_info)
            return file_info
        except InvalidId:
            raise FileNotFound
    
    async def get_file_by_fileuniqueid(self, id, file_unique_id, many=False):
        if many:
            return self.file.find({"user_id": id, "file_unique_id": file_unique_id})
        else:
            file_info = await self.file.find_one({"user_id": id, "file_unique_id": file_unique_id})
        if file_info:
            return self.normalize_file_doc(file_info)
        return False

# ---------------------[ TOTAL FILES ]---------------------#
    async def total_files(self, id=None):
        if id:
            return await self.file.count_documents({"user_id": id})
        return await self.file.count_documents({})

# ---------------------[ DELETE FILES ]---------------------#
    async def delete_one_file(self, _id):
        try:
            await self.file.delete_one({'_id': ObjectId(_id)})
            await self.revoke_public_link(target_type="file", target_id=str(_id))
        except InvalidId:
            return

# ---------------------[ UPDATE FILES ]---------------------#
    async def update_file_ids(self, _id, file_ids: dict):
        try:
            await self.file.update_one({"_id": ObjectId(_id)}, {"$set": {"file_ids": file_ids}})
            invalidate_file_runtime(str(_id))
        except InvalidId:
            return

    async def update_file_flog_msg(self, _id, msg_id: int, channel_id: int | None = None):
        try:
            updates = {"flog_msg_id": int(msg_id)}
            if channel_id not in (None, ""):
                updates["flog_channel_id"] = int(channel_id)
            await self.file.update_one({"_id": ObjectId(_id)}, {"$set": updates})
            invalidate_file_runtime(str(_id))
        except Exception:
            return
        
    async def count_links(self, id, operation: str):
        if operation == "-":
            # Prevent negative counts and avoid creating a new user on decrement
            await self.col.update_one(
                {"id": id, "Links": {"$gt": 0}},
                {"$inc": {"Links": -1}},
            )
        elif operation == "+":
            update = {"$setOnInsert": {"join_date": time.time()}, "$inc": {"Links": 1}}
            await self.col.update_one({"id": id}, update, upsert=True)

# ---------------------[ URL SHORTENER / WEB ADS SETTINGS ]---------------------#
    async def update_urlshortener_status(self, status: bool):
        await self.settings.update_one(
            {"_id": "urlshortener"},
            {"$set": {"status": bool(status)}},
            upsert=True
        )

    async def get_urlshortener_status(self):
        # New key
        settings = await self.settings.find_one({"_id": "urlshortener"})
        if settings is not None:
            return bool(settings.get("status", False))

        # Backward compatibility with legacy key
        legacy = await self.settings.find_one({"_id": "ads"})
        if legacy is not None:
            return bool(legacy.get("status", False))

        return False

    async def update_web_ads_status(self, status: bool):
        await self.settings.update_one(
            {"_id": "webads"},
            {"$set": {"status": bool(status)}},
            upsert=True
        )

    async def get_web_ads_status(self):
        settings = await self.settings.find_one({"_id": "webads"})
        if not settings:
            return bool(WebAds.ENABLED)
        return bool(settings.get("status", False))

    async def update_flog_storage_mode(self, mode: str):
        normalized = "admin" if str(mode or "").strip().lower() == "admin" else "main"
        await self.settings.update_one(
            {"_id": "flog_storage"},
            {"$set": {"mode": normalized}},
            upsert=True,
        )

    async def get_flog_storage_mode(self) -> str:
        settings = await self.settings.find_one({"_id": "flog_storage"})
        if not settings:
            return "main"
        return "admin" if str(settings.get("mode", "main")).strip().lower() == "admin" else "main"

    async def get_admin_flog_user_ids(self) -> list[int]:
        settings = await self.settings.find_one({"_id": "admin_flog_users"})
        raw_users = settings.get("users", []) if settings else []
        user_ids: list[int] = []
        seen: set[int] = set()
        for raw in raw_users:
            try:
                user_id = int(raw)
            except Exception:
                continue
            if user_id in seen:
                continue
            seen.add(user_id)
            user_ids.append(user_id)
        return user_ids

    async def is_admin_flog_user(self, user_id: int) -> bool:
        try:
            normalized_user_id = int(user_id)
        except Exception:
            return False
        return bool(
            await self.settings.find_one(
                {"_id": "admin_flog_users", "users": normalized_user_id},
                {"_id": 1},
            )
        )

    async def set_admin_flog_user(self, user_id: int, enabled: bool) -> None:
        normalized_user_id = int(user_id)
        if enabled:
            await self.settings.update_one(
                {"_id": "admin_flog_users"},
                {"$addToSet": {"users": normalized_user_id}},
                upsert=True,
            )
            return

        await self.settings.update_one(
            {"_id": "admin_flog_users"},
            {"$pull": {"users": normalized_user_id}},
            upsert=True,
        )

    # ---- Backward compatibility helpers (legacy /ads command code paths) ----
    async def update_ads_status(self, status: bool):
        await self.update_urlshortener_status(status)

    async def get_ads_status(self):
        return await self.get_urlshortener_status()

# ---------------------[ FOLDERS ]---------------------#
    async def create_folder(self, user_id: int, file_list: list[str]):
        # Deduplicate while preserving order
        seen = set()
        unique_files = []
        for fid in file_list:
            if fid in seen:
                continue
            seen.add(fid)
            unique_files.append(fid)

        if not unique_files:
            raise FileNotFound

        folder_id = secrets.token_urlsafe(8).replace("-", "").replace("_", "")
        while await self.folders.find_one({"_id": folder_id}):
            folder_id = secrets.token_urlsafe(8).replace("-", "").replace("_", "")

        doc = {
            "_id": folder_id,
            "user_id": int(user_id),
            "files": unique_files,
            "title": None,
            "created_at": time.time(),
        }
        await self.folders.insert_one(doc)
        await self.ensure_public_link_for_folder(doc)
        return folder_id

    async def get_folder(self, folder_id: str):
        folder = await self.folders.find_one({"_id": str(folder_id)})
        if not folder:
            raise FileNotFound
        return folder

    async def get_folder_for_user(self, folder_id: str, user_id: int):
        folder = await self.folders.find_one({"_id": str(folder_id), "user_id": int(user_id)})
        if not folder:
            raise FileNotFound
        return folder

    async def list_folders(self, user_id: int, range):
        start, end = range
        if start > end:
            return self.folders.find({"_id": None}), 0
        folders = (
            self.folders.find({"user_id": int(user_id)}, {"_id": 1, "title": 1, "created_at": 1, "files": 1})
            .sort('created_at', pymongo.DESCENDING)
            .skip(start - 1)
            .limit(end - start + 1)
        )
        total = await self.folders.count_documents({"user_id": int(user_id)})
        return folders, total

    async def total_folders(self, user_id: int):
        return await self.folders.count_documents({"user_id": int(user_id)})

    async def update_folder_title(self, folder_id: str, user_id: int, title: str):
        title = (title or "").strip()
        if not title:
            raise FileNotFound
        res = await self.folders.update_one(
            {"_id": str(folder_id), "user_id": int(user_id)},
            {"$set": {"title": title}}
        )
        if res.matched_count == 0:
            raise FileNotFound

    async def delete_folder(self, folder_id: str, user_id: int):
        res = await self.folders.delete_one({"_id": str(folder_id), "user_id": int(user_id)})
        if res.deleted_count == 0:
            raise FileNotFound
        await self.revoke_public_link(target_type="folder", target_id=str(folder_id))

    async def delete_folder_by_id(self, folder_id: str):
        res = await self.folders.delete_one({"_id": str(folder_id)})
        if res.deleted_count == 0:
            raise FileNotFound
        await self.revoke_public_link(target_type="folder", target_id=str(folder_id))

    async def remove_file_from_folders(self, file_id: str):
        try:
            await self.folders.update_many({"files": str(file_id)}, {"$pull": {"files": str(file_id)}})
        except Exception:
            pass

    async def add_nsfw_report(self, doc: dict):
        await self.nsfw_reports.insert_one(doc)

    async def update_nsfw_report(self, report_id: str, updates: dict):
        await self.nsfw_reports.update_one({"_id": str(report_id)}, {"$set": updates})

    async def get_nsfw_report(self, report_id: str):
        return await self.nsfw_reports.find_one({"_id": str(report_id)})

# ---------------------[ DONATIONS ]---------------------#
    async def record_donation(
        self,
        *,
        user_id: int,
        amount: int,
        currency: str,
        payload: str,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str = "",
        first_name: str = "",
        username: str = "",
    ) -> dict:
        now = time.time()
        doc = {
            "user_id": int(user_id),
            "amount": int(amount),
            "currency": str(currency or ""),
            "payload": str(payload or ""),
            "telegram_payment_charge_id": str(telegram_payment_charge_id or ""),
            "provider_payment_charge_id": str(provider_payment_charge_id or ""),
            "first_name": str(first_name or ""),
            "username": str(username or ""),
            "paid_at": now,
        }
        await self.donations.update_one(
            {"telegram_payment_charge_id": doc["telegram_payment_charge_id"]},
            {"$setOnInsert": doc},
            upsert=True,
        )
        return await self.donations.find_one({"telegram_payment_charge_id": doc["telegram_payment_charge_id"]})

    async def get_user_donations(self, user_id: int, limit: int = 10) -> list[dict]:
        cursor = self.donations.find({"user_id": int(user_id)}).sort("paid_at", pymongo.DESCENDING).limit(int(limit))
        return [doc async for doc in cursor]

    async def get_user_donation_stats(self, user_id: int) -> dict:
        user_id = int(user_id)
        total_count = await self.donations.count_documents({"user_id": user_id})
        total_stars = 0
        async for row in self.donations.aggregate(
            [
                {"$match": {"user_id": user_id}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ):
            total_stars = int(row.get("total", 0) or 0)
        return {"count": total_count, "total_stars": total_stars}

# ---------------------[ PUBLIC LINK MAPPING ]---------------------#
    async def _generate_public_id(self, length: int = 12) -> str:
        while True:
            public_id = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:length]
            if len(public_id) < 8:
                continue
            exists = await self.public_links.find_one({"_id": public_id})
            if not exists:
                return public_id

    def _build_public_link_doc(
        self,
        public_id: str,
        target_type: str,
        target_id: str,
        *,
        file_name: str = "",
        file_type: str = "",
        folder_name: str = "",
        flags: dict | None = None,
        expires_at: float | None = None,
    ) -> dict:
        now = time.time()
        return {
            "_id": public_id,
            "public_id": public_id,
            "type": str(target_type),
            "target_id": str(target_id),
            "file_name": str(file_name or ""),
            "file_type": str(file_type or ""),
            "folder_name": str(folder_name or ""),
            "created_at": now,
            "updated_at": now,
            "click_count": 0,
            "flags": flags or {},
            "expires_at": expires_at,
            "revoked": False,
            "revoked_at": None,
        }

    async def get_public_link(self, public_id: str):
        link = await self.public_links.find_one({"_id": str(public_id)})
        if not link:
            raise FileNotFound("Public link not found")
        return link

    async def get_active_public_link_for_target(self, target_type: str, target_id: str):
        now = time.time()
        return await self.public_links.find_one(
            {
                "type": str(target_type),
                "target_id": str(target_id),
                "revoked": {"$ne": True},
                "$or": [
                    {"expires_at": None},
                    {"expires_at": {"$gt": now}},
                    {"expires_at": {"$exists": False}},
                ],
            },
            sort=[("created_at", pymongo.DESCENDING)],
        )

    async def _touch_public_link(
        self,
        public_id: str,
        *,
        file_name: str | None = None,
        file_type: str | None = None,
        folder_name: str | None = None,
    ):
        updates = {"updated_at": time.time()}
        if file_name is not None:
            updates["file_name"] = str(file_name or "")
        if file_type is not None:
            updates["file_type"] = str(file_type or "")
        if folder_name is not None:
            updates["folder_name"] = str(folder_name or "")
        await self.public_links.update_one({"_id": str(public_id)}, {"$set": updates})

    async def create_public_link(
        self,
        target_type: str,
        target_id: str,
        *,
        file_name: str = "",
        file_type: str = "",
        folder_name: str = "",
        flags: dict | None = None,
        expires_at: float | None = None,
    ) -> dict:
        public_id = await self._generate_public_id()
        doc = self._build_public_link_doc(
            public_id,
            target_type,
            target_id,
            file_name=file_name,
            file_type=file_type,
            folder_name=folder_name,
            flags=flags,
            expires_at=expires_at,
        )
        await self.public_links.insert_one(doc)
        return doc

    async def ensure_public_link_for_file(self, file_info: dict) -> dict:
        if not file_info:
            raise FileNotFound
        target_id = str(file_info.get("_id"))
        current = await self.get_active_public_link_for_target("file", target_id)
        file_name = file_info.get("file_name") or "file"
        file_type = file_info.get("mime_type") or file_info.get("category") or ""
        default_expiry = None
        if int(Server.PUBLIC_FILE_EXPIRE_HOURS or 0) > 0:
            default_expiry = time.time() + int(Server.PUBLIC_FILE_EXPIRE_HOURS) * 3600
        if current:
            updates = {"updated_at": time.time(), "file_name": file_name, "file_type": file_type}
            if current.get("expires_at") is None and default_expiry is not None:
                updates["expires_at"] = default_expiry
            await self.public_links.update_one({"_id": str(current["_id"])}, {"$set": updates})
            current["file_name"] = file_name
            current["file_type"] = file_type
            if current.get("expires_at") is None and default_expiry is not None:
                current["expires_at"] = default_expiry
            return current
        return await self.create_public_link(
            "file",
            target_id,
            file_name=file_name,
            file_type=file_type,
            expires_at=default_expiry,
        )

    async def ensure_public_link_for_folder(self, folder: dict) -> dict:
        if not folder:
            raise FileNotFound
        target_id = str(folder.get("_id"))
        current = await self.get_active_public_link_for_target("folder", target_id)
        folder_name = (folder.get("title") or "").strip() or f"Folder {target_id}"
        if current:
            await self._touch_public_link(current["_id"], folder_name=folder_name)
            current["folder_name"] = folder_name
            return current
        return await self.create_public_link(
            "folder",
            target_id,
            folder_name=folder_name,
        )

    async def increment_public_link_click(self, public_id: str):
        await self.public_links.update_one({"_id": str(public_id)}, {"$inc": {"click_count": 1}})

    async def _assert_public_link_active(self, link: dict) -> dict:
        if not link:
            raise FileNotFound("Public link not found")
        if link.get("revoked"):
            raise FileNotFound("This link has been revoked")
        expires_at = link.get("expires_at")
        if expires_at is not None and float(expires_at) <= time.time():
            raise FileNotFound("This link has expired")
        return link

    async def resolve_public_target(self, public_id: str, *, increment_click: bool = False) -> tuple[dict, dict]:
        link = await self.get_public_link(public_id)
        await self._assert_public_link_active(link)
        if increment_click:
            await self.increment_public_link_click(link["_id"])
            link["click_count"] = int(link.get("click_count", 0)) + 1
        return link, link

    async def resolve_public_file(self, public_id: str, *, increment_click: bool = False) -> tuple[dict, dict]:
        if not increment_click:
            cached = get_cached_file_reference(public_id)
            if cached:
                return cached

        link = await self.get_public_link(public_id)
        await self._assert_public_link_active(link)
        if link.get("type") != "file":
            raise FileNotFound("File link not found")
        file_info = await self.get_file(link.get("target_id"))
        if increment_click:
            await self.increment_public_link_click(link["_id"])
            link["click_count"] = int(link.get("click_count", 0)) + 1
        else:
            cache_file_reference(public_id, file_info, link)
        return file_info, link

    async def resolve_public_folder(self, public_id: str, *, increment_click: bool = False) -> tuple[dict, dict]:
        link = await self.get_public_link(public_id)
        await self._assert_public_link_active(link)
        if link.get("type") != "folder":
            raise FileNotFound("Folder link not found")
        folder = await self.get_folder(link.get("target_id"))
        if increment_click:
            await self.increment_public_link_click(link["_id"])
            link["click_count"] = int(link.get("click_count", 0)) + 1
        return folder, link

    async def resolve_file_reference(self, value: str, *, increment_click: bool = False) -> tuple[dict, dict | None]:
        if not increment_click:
            cached = get_cached_file_reference(value)
            if cached:
                file_info, link = cached
                if link is None:
                    link = await self.ensure_public_link_for_file(file_info)
                    cache_file_reference(str(file_info["_id"]), file_info, link)
                return file_info, link

        try:
            file_info = await self.get_file(value)
            link = await self.ensure_public_link_for_file(file_info)
            if not increment_click:
                cache_file_reference(value, file_info, link)
            return file_info, link
        except FileNotFound:
            pass
        file_info, link = await self.resolve_public_file(value, increment_click=increment_click)
        if not increment_click:
            cache_file_reference(value, file_info, link)
        return file_info, link

    async def resolve_folder_reference(self, value: str, *, increment_click: bool = False) -> tuple[dict, dict | None]:
        try:
            folder = await self.get_folder(value)
            link = await self.ensure_public_link_for_folder(folder)
            return folder, link
        except FileNotFound:
            pass
        return await self.resolve_public_folder(value, increment_click=increment_click)

    async def revoke_public_link(self, public_id: str | None = None, *, target_type: str | None = None, target_id: str | None = None):
        link = None
        if public_id:
            link = await self.public_links.find_one({"_id": str(public_id)})
        elif target_type and target_id is not None:
            link = await self.get_active_public_link_for_target(target_type, str(target_id))
        if not link:
            return None
        await self.public_links.update_one(
            {"_id": link["_id"]},
            {"$set": {"revoked": True, "revoked_at": time.time(), "updated_at": time.time()}},
        )
        link["revoked"] = True
        link["revoked_at"] = time.time()
        if link.get("type") == "file":
            invalidate_file_runtime(str(link.get("target_id") or ""), str(link.get("_id") or ""))
        return link

    async def regenerate_public_link(
        self,
        target_type: str,
        target_id: str,
        *,
        file_name: str = "",
        file_type: str = "",
        folder_name: str = "",
        flags: dict | None = None,
        expires_at: float | None = None,
    ) -> dict:
        await self.revoke_public_link(target_type=target_type, target_id=str(target_id))
        return await self.create_public_link(
            target_type,
            str(target_id),
            file_name=file_name,
            file_type=file_type,
            folder_name=folder_name,
            flags=flags,
            expires_at=expires_at,
        )

    async def set_public_link_expiry(self, public_id: str, expires_at: float | None):
        link = await self.get_public_link(public_id)
        res = await self.public_links.update_one(
            {"_id": str(public_id)},
            {"$set": {"expires_at": expires_at, "updated_at": time.time()}},
        )
        if res.matched_count == 0:
            raise FileNotFound("Public link not found")
        if link.get("type") == "file":
            invalidate_file_runtime(str(link.get("target_id") or ""), str(link.get("_id") or ""))

    async def set_active_public_link_expiry_for_target(self, target_type: str, target_id: str, expires_at: float | None):
        link = await self.get_active_public_link_for_target(target_type, str(target_id))
        if not link:
            raise FileNotFound("Public link not found")
        await self.set_public_link_expiry(link["_id"], expires_at)
        link["expires_at"] = expires_at
        return link
