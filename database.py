from motor.motor_asyncio import AsyncIOMotorClient
from config import PRIMARY_MONGO

db_client = AsyncIOMotorClient(PRIMARY_MONGO)
db_main = db_client["BotDB"]
users_col = db_main["users"]

async def save_user_data(user_id: int, key: str, value: str):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {key: value}},
        upsert=True
    )

async def get_user_data(user_id: int, key: str):
    user = await users_col.find_one({"user_id": user_id})
    if user:
        return user.get(key)
    return None
