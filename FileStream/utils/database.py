import pymongo
import time
import mimetypes
import motor.motor_asyncio
from bson.objectid import ObjectId
from bson.errors import InvalidId
from FileStream.server.exceptions import FileNotFound

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
                return fetch_old["_id"]
        await self.count_links(file_info["user_id"], "+")
        return (await self.file.insert_one(file_info)).inserted_id

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

            # Backfill missing mime_type using file extension
            if not file_info.get("mime_type") and file_info.get("file_name"):
                mime, _ = mimetypes.guess_type(file_info.get("file_name"))
                if mime:
                    await self.file.update_one(
                        {"_id": file_info["_id"]},
                        {"$set": {"mime_type": mime}}
                    )
                    file_info["mime_type"] = mime
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

# ---------------------[ ADS SETTINGS ]---------------------#
    async def update_ads_status(self, status: bool):
        await self.settings.update_one(
            {"_id": "ads"},
            {"$set": {"status": bool(status)}},
            upsert=True
        )

    async def get_ads_status(self):
        settings = await self.settings.find_one({"_id": "ads"})
        if not settings:
            return False
        return bool(settings.get("status", False))

# ---------------------[ FOLDERS ]---------------------#
    async def create_folder(self, user_id: int, file_list: list[str]):
        import secrets
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

    async def delete_folder_by_id(self, folder_id: str):
        res = await self.folders.delete_one({"_id": str(folder_id)})
        if res.deleted_count == 0:
            raise FileNotFound

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
