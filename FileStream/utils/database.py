import pymongo
import time
import mimetypes
import secrets
import motor.motor_asyncio
from bson.objectid import ObjectId
from bson.errors import InvalidId
from FileStream.server.exceptions import FileNotFound
from FileStream.utils.category import detect_category

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.black = self.db.blacklist
        self.file = self.db.file
        self.settings = self.db.settings  # <--- NEW COLLECTION
        self.folders = self.db.folders
        self.nsfw_reports = self.db.nsfw_reports
        self.public_links = self.db.public_links

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
            self.file.find({"user_id": user_id})
            .sort('_id', pymongo.DESCENDING)
            .skip(start - 1)
            .limit(end - start + 1)
        )
        total_files = await self.file.count_documents({"user_id": user_id})
        return user_files, total_files

    async def get_file(self, _id):
        try:
            file_info=await self.file.find_one({"_id": ObjectId(_id)})
            if not file_info:
                raise FileNotFound

            updates = {}

            # Backfill missing mime_type using file extension
            if not file_info.get("mime_type") and file_info.get("file_name"):
                mime, _ = mimetypes.guess_type(file_info.get("file_name"))
                if mime:
                    updates["mime_type"] = mime

            # Backfill file_ext if missing
            if not file_info.get("file_ext") and file_info.get("file_name"):
                import os
                updates["file_ext"] = os.path.splitext(file_info.get("file_name") or "")[1].lower()

            detected_category = detect_category(
                file_name=file_info.get("file_name"),
                mime_type=updates.get("mime_type", file_info.get("mime_type")),
                file_ext=updates.get("file_ext", file_info.get("file_ext")),
            )

            current_category = (file_info.get("category") or "").strip()
            if not current_category:
                updates["category"] = detected_category
            elif current_category in {"Movies", "Other"} and detected_category not in {"Movies", "Other"}:
                # Auto-correct older generic categories when we can now detect a better one.
                updates["category"] = detected_category

            if updates:
                await self.file.update_one(
                    {"_id": file_info["_id"]},
                    {"$set": updates}
                )
                file_info.update(updates)

            return file_info
        except InvalidId:
            raise FileNotFound
    
    async def get_file_by_fileuniqueid(self, id, file_unique_id, many=False):
        if many:
            return self.file.find({"user_id": id, "file_unique_id": file_unique_id})
        else:
            file_info=await self.file.find_one({"user_id": id, "file_unique_id": file_unique_id})
        if file_info:
            return file_info
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
        except InvalidId:
            return

    async def update_file_flog_msg(self, _id, msg_id: int):
        try:
            await self.file.update_one({"_id": ObjectId(_id)}, {"$set": {"flog_msg_id": int(msg_id)}})
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
            return False
        return bool(settings.get("status", False))

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
            self.folders.find({"user_id": int(user_id)})
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
        return await self.public_links.find_one(
            {"type": str(target_type), "target_id": str(target_id), "revoked": {"$ne": True}},
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
        if current:
            await self._touch_public_link(current["_id"], file_name=file_name, file_type=file_type)
            current["file_name"] = file_name
            current["file_type"] = file_type
            return current
        return await self.create_public_link(
            "file",
            target_id,
            file_name=file_name,
            file_type=file_type,
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
        link = await self.get_public_link(public_id)
        await self._assert_public_link_active(link)
        if link.get("type") != "file":
            raise FileNotFound("File link not found")
        file_info = await self.get_file(link.get("target_id"))
        if increment_click:
            await self.increment_public_link_click(link["_id"])
            link["click_count"] = int(link.get("click_count", 0)) + 1
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
        try:
            file_info = await self.get_file(value)
            link = await self.ensure_public_link_for_file(file_info)
            return file_info, link
        except FileNotFound:
            pass
        return await self.resolve_public_file(value, increment_click=increment_click)

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
        res = await self.public_links.update_one(
            {"_id": str(public_id)},
            {"$set": {"expires_at": expires_at, "updated_at": time.time()}},
        )
        if res.matched_count == 0:
            raise FileNotFound("Public link not found")

    async def set_active_public_link_expiry_for_target(self, target_type: str, target_id: str, expires_at: float | None):
        link = await self.get_active_public_link_for_target(target_type, str(target_id))
        if not link:
            raise FileNotFound("Public link not found")
        await self.set_public_link_expiry(link["_id"], expires_at)
        link["expires_at"] = expires_at
        return link
