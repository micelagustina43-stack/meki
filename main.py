from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN

# in_memory=True memastikan tidak ada file NovusManager.session yang dibuat di folder
bot = Client(
    "NovusManager",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True, 
    plugins=dict(root="plugins")
)

if __name__ == "__main__":
    print("Mulai menjalankan Novus Manager Bot (In-Memory Mode)...")
    bot.run()
