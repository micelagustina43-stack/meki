from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.raw import functions
from database import save_user_data, get_user_data
from config import API_ID, API_HASH

# Dictionary untuk menyimpan client user yang sedang aktif di memori
active_clients = {}

@Client.on_message(filters.command("login") & filters.private)
async def login_session(client, message):
    if len(message.command) < 2:
        return await message.reply("Gunakan format: `/login <String_Session>`")
    
    session_string = message.command[1]
    user_id = message.from_user.id
    
    msg = await message.reply("Mencoba masuk...")
    
    try:
        user_client = Client(f"user_{user_id}", session_string=session_string, api_id=API_ID, api_hash=API_HASH)
        await user_client.start()
        
        # Simpan ke DB Utama agar aman saat ganti VPS
        await save_user_data(user_id, "session", session_string)
        active_clients[user_id] = user_client
        
        me = await user_client.get_me()
        await msg.edit(
            f"✅ **Berhasil Masuk!**\n\n"
            f"**Nama:** {me.first_name} {me.last_name or ''}\n"
            f"**Username:** @{me.username or 'Tidak ada'}\n"
            f"**User ID:** `{me.id}`\n\n"
            f"Session telah diamankan di Database Utama."
        )
    except Exception as e:
        await msg.edit(f"❌ Gagal masuk: {str(e)}")

@Client.on_message(filters.command("terminate") & filters.private)
async def terminate_others(client, message):
    user_id = message.from_user.id
    if user_id not in active_clients:
        return await message.reply("Anda belum login! Gunakan /login.")
    
    user_client = active_clients[user_id]
    try:
        # Memanggil API Raw untuk mereset/mengeluarkan device lain
        await user_client.invoke(functions.auth.ResetAuthorizations())
        await message.reply("✅ Semua sesi di device lain berhasil dikeluarkan!")
    except Exception as e:
        await message.reply(f"❌ Gagal mengeluarkan device lain: {str(e)}")

@Client.on_message(filters.command("chats") & filters.private)
async def get_target_chats(client, message):
    if len(message.command) < 2:
        return await message.reply("Gunakan format: `/chats <username_target>`")
    
    target = message.command[1]
    user_id = message.from_user.id
    
    if user_id not in active_clients:
        return await message.reply("Anda belum login! Gunakan /login.")
    
    user_client = active_clients[user_id]
    
    try:
        messages = []
        async for msg in user_client.get_chat_history(target, limit=100): # Ambil 100 terakhir
            text = msg.text or "[Media/Sticker]"
            sender = "Saya" if msg.outgoing else target
            messages.append(f"**{sender}**: {text[:50]}...")
            
        if not messages:
            return await message.reply("Tidak ada riwayat chat.")
            
        # Simpan sementara di memori (idealnya pakai DB/Cache jika berskala besar)
        if not hasattr(client, "temp_chats"):
            client.temp_chats = {}
        client.temp_chats[f"{user_id}_{target}"] = messages
        
        await send_chat_page(message, client, user_id, target, 0)
        
    except Exception as e:
        await message.reply(f"❌ Gagal mengambil chat: {str(e)}")

async def send_chat_page(message, bot_client, user_id, target, page):
    chat_data = bot_client.temp_chats.get(f"{user_id}_{target}", [])
    start_idx = page * 10
    end_idx = start_idx + 10
    page_chats = chat_data[start_idx:end_idx]
    
    text = f"**Riwayat Chat dengan {target} (Page {page+1}):**\n\n"
    text += "\n".join(page_chats)
    
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cpage_{target}_{page-1}"))
    if end_idx < len(chat_data):
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"cpage_{target}_{page+1}"))
        
    markup = InlineKeyboardMarkup([buttons]) if buttons else None
    
    if hasattr(message, "message"): # Jika dari CallbackQuery
        await message.message.edit(text, reply_markup=markup)
    else:
        await message.reply(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^cpage_"))
async def paginate_chats(client, callback_query):
    _, target, page = callback_query.data.split("_")
    user_id = callback_query.from_user.id
    await send_chat_page(callback_query, client, user_id, target, int(page))
