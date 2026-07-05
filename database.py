import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from config import PRIMARY_MONGO

db_client = AsyncIOMotorClient(PRIMARY_MONGO, tlsCAFile=certifi.where())
db_main = db_client["NovusDB"]
users_col = db_main["users"]

async def get_user_doc(user_id: int):
    doc = await users_col.find_one({"user_id": user_id})
    if not doc:
        doc = {"user_id": user_id, "accounts": {}, "databases": {}}
        await users_col.insert_one(doc)
    return doc

async def update_user_doc(user_id: int, update_dict: dict):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": update_dict},
        upsert=True
    )
