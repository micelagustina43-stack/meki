import certifi
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.raw import functions
from motor.motor_asyncio import AsyncIOMotorClient
from database import get_user_doc, update_user_doc
from config import API_ID, API_HASH

print("✅ Plugin bot_logic berhasil dimuat!")

USER_STATE = {}
TEMP_DATA = {}
SECONDARY_DB_CLIENTS = {}
TEMP_CHATS = {}

def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Kelola Akun Telegram", callback_data="menu_accounts")],
        [InlineKeyboardButton("🗄️ Kelola Database Mongo", callback_data="menu_db")]
    ])

async def send_accounts_menu(message_or_query, user_id):
    doc = await get_user_doc(user_id)
    accounts = doc.get("accounts", {})
    buttons = []
    
    for name in accounts.keys():
        buttons.append([InlineKeyboardButton(f"👤 {name}", callback_data=f"actmenu_{name}")])
        
    buttons.append([InlineKeyboardButton("➕ Tambah Akun Baru", callback_data="add_account")])
    buttons.append([InlineKeyboardButton("🔙 Kembali ke Utama", callback_data="main_menu")])
    
    text = "**👥 Menu Kelola Akun Telegram**\nPilih akun yang tersimpan atau tambahkan yang baru:"
    markup = InlineKeyboardMarkup(buttons)
    
    if hasattr(message_or_query, "message"):
        await message_or_query.message.edit(text, reply_markup=markup)
    else:
        await message_or_query.reply(text, reply_markup=markup)

async def send_db_menu(message_or_query, user_id):
    doc = await get_user_doc(user_id)
    dbs = doc.get("databases", {})
    buttons = []
    
    for name in dbs.keys():
        buttons.append([InlineKeyboardButton(f"🗄️ {name}", callback_data=f"dbmenu_{name}")])
        
    buttons.append([InlineKeyboardButton("➕ Tambah Database Baru", callback_data="add_db")])
    buttons.append([InlineKeyboardButton("🔙 Kembali ke Utama", callback_data="main_menu")])
    
    text = "**🗄️ Menu Kelola Database (MongoDB)**\nPilih database yang tersimpan atau tambahkan baru:"
    markup = InlineKeyboardMarkup(buttons)
    
    if hasattr(message_or_query, "message"):
        await message_or_query.message.edit(text, reply_markup=markup)
    else:
        await message_or_query.reply(text, reply_markup=markup)

@Client.on_message(filters.command("start") & filters.private)
async def start_msg(client, message):
    USER_STATE.pop(message.from_user.id, None) 
    await message.reply(
        "👋 **Selamat datang di Novus Manager.**\n\n"
        "Semua sistem menggunakan navigasi tombol. Silakan pilih menu di bawah ini:",
        reply_markup=get_main_menu()
    )

@Client.on_message(filters.private & ~filters.command("start"))
async def state_listener(client, message):
    user_id = message.from_user.id
    state = USER_STATE.get(user_id)
    
    if not state:
        return 
        
    text = message.text
    
    if state == "wait_account_session":
        TEMP_DATA[f"{user_id}_new_session"] = text
        USER_STATE[user_id] = "wait_account_name"
        await message.reply("✅ String Session diterima.\n\nSekarang kirimkan **Nama** untuk akun ini (contoh: Akun Utama):")
        
    elif state == "wait_account_name":
        session = TEMP_DATA.get(f"{user_id}_new_session")
        name = text
        doc = await get_user_doc(user_id)
        accounts = doc.get("accounts", {})
        accounts[name] = session
        await update_user_doc(user_id, {"accounts": accounts})
        
        USER_STATE.pop(user_id, None)
        await message.reply(f"✅ Akun **{name}** berhasil diamankan ke database utama!")
        await send_accounts_menu(message, user_id)
        
    elif state == "wait_db_url":
        TEMP_DATA[f"{user_id}_new_db_url"] = text
        USER_STATE[user_id] = "wait_db_name"
        await message.reply("✅ URL MongoDB diterima.\n\nSekarang kirimkan **Nama** untuk database ini (contoh: Database Web):")
        
    elif state == "wait_db_name":
        url = TEMP_DATA.get(f"{user_id}_new_db_url")
        name = text
        doc = await get_user_doc(user_id)
        dbs = doc.get("databases", {})
        dbs[name] = url
        await update_user_doc(user_id, {"databases": dbs})
        
        USER_STATE.pop(user_id, None)
        await message.reply(f"✅ Database **{name}** berhasil disimpan!")
        await send_db_menu(message, user_id)
        
    elif state == "wait_chat_target":
        target = text
        account_name = TEMP_DATA.get(f"{user_id}_active_account")
        USER_STATE.pop(user_id, None)
        await process_chat_history(client, message, user_id, account_name, target)

async def process_chat_history(bot_client, message, user_id, account_name, target):
    msg = await message.reply("🔄 Sedang memuat riwayat chat, harap tunggu...")
    doc = await get_user_doc(user_id)
    session = doc.get("accounts", {}).get(account_name)
    
    if not session:
        return await msg.edit("❌ Sesi tidak ditemukan di database.")
    
    try:
        user_client = Client(f"tmp_{user_id}", session_string=session, api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await user_client.start()
        
        messages = []
        async for m in user_client.get_chat_history(target, limit=100):
            txt = m.text or "[Media/Sticker]"
            sender = "Saya" if m.outgoing else target
            messages.append(f"**{sender}**: {txt[:50]}...")
            
        await user_client.stop()
        
        if not messages:
            return await msg.edit("Tidak ada riwayat chat dengan target tersebut.")
            
        TEMP_CHATS[f"{user_id}_chats"] = messages
        TEMP_DATA[f"{user_id}_chat_target"] = target
        
        await msg.delete()
        await send_chat_page(bot_client, message, user_id, 0)
        
    except Exception as e:
        await msg.edit(f"❌ Error mengambil chat: {str(e)}")

async def send_chat_page(bot_client, message_or_query, user_id, page):
    chat_data = TEMP_CHATS.get(f"{user_id}_chats", [])
    target = TEMP_DATA.get(f"{user_id}_chat_target", "Target")
    
    start_idx = page * 10
    end_idx = start_idx + 10
    page_chats = chat_data[start_idx:end_idx]
    
    text = f"💬 **Riwayat Chat dengan {target} (Page {page+1}):**\n\n"
    text += "\n".join(page_chats)
    
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cpage_{page-1}"))
    if end_idx < len(chat_data):
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"cpage_{page+1}"))
        
    layout = [buttons] if buttons else []
    layout.append([InlineKeyboardButton("🔙 Tutup Chat", callback_data="menu_accounts")])
    
    markup = InlineKeyboardMarkup(layout)
    
    if hasattr(message_or_query, "message"):
        await message_or_query.message.edit(text, reply_markup=markup)
    else:
        await message_or_query.reply(text, reply_markup=markup)

@Client.on_callback_query()
async def callback_handler(client, query):
    data = query.data
    user_id = query.from_user.id
    
    if USER_STATE.get(user_id):
        USER_STATE.pop(user_id, None)
        
    if data == "main_menu":
        await query.message.edit("**Menu Utama Novus Manager**\n\nPilih menu di bawah ini:", reply_markup=get_main_menu())
        
    elif data == "menu_accounts":
        await send_accounts_menu(query, user_id)
        
    elif data == "menu_db":
        await send_db_menu(query, user_id)
        
    elif data == "add_account":
        USER_STATE[user_id] = "wait_account_session"
        await query.message.edit("📝 **Kirimkan String Session** untuk akun Telegram baru:")
        
    elif data == "add_db":
        USER_STATE[user_id] = "wait_db_url"
        await query.message.edit("📝 **Kirimkan URL MongoDB**:")
        
    elif data.startswith("actmenu_"):
        name = data.split("_", 1)[1]
        buttons = [
            [InlineKeyboardButton("💬 Cek Chat Akun", callback_data=f"chatact_{name}")],
            [InlineKeyboardButton("🛑 Terminate Device Lain", callback_data=f"termact_{name}")],
            [InlineKeyboardButton("❌ Hapus Akun dari Database", callback_data=f"delact_{name}")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu_accounts")]
        ]
        await query.message.edit(f"👤 **Kelola Akun: {name}**\nPilih aksi yang ingin dilakukan:", reply_markup=InlineKeyboardMarkup(buttons))
        
    elif data.startswith("chatact_"):
        name = data.split("_", 1)[1]
        TEMP_DATA[f"{user_id}_active_account"] = name
        USER_STATE[user_id] = "wait_chat_target"
        await query.message.edit(f"📝 **Kirimkan Username/User ID target**:")
        
    elif data.startswith("termact_"):
        name = data.split("_", 1)[1]
        doc = await get_user_doc(user_id)
        session = doc.get("accounts", {}).get(name)
        
        await query.message.edit("🔄 Sedang memproses terminate perangkat lain...")
        try:
            user_client = Client(f"tmp_{user_id}", session_string=session, api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await user_client.start()
            await user_client.invoke(functions.auth.ResetAuthorizations())
            await user_client.stop()
            await query.message.edit(f"✅ **Berhasil!** Semua perangkat lain telah dikeluarkan.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"actmenu_{name}")]]))
        except Exception as e:
            await query.message.edit(f"❌ Gagal: {str(e)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"actmenu_{name}")]]))
            
    elif data.startswith("delact_"):
        name = data.split("_", 1)[1]
        doc = await get_user_doc(user_id)
        accounts = doc.get("accounts", {})
        if name in accounts:
            del accounts[name]
            await update_user_doc(user_id, {"accounts": accounts})
        await query.answer(f"Akun {name} dihapus!", show_alert=True)
        await send_accounts_menu(query, user_id)

    elif data.startswith("cpage_"):
        page = int(data.split("_")[1])
        await send_chat_page(client, query, user_id, page)

    elif data.startswith("dbmenu_"):
        name = data.split("_", 1)[1]
        buttons = [
            [InlineKeyboardButton("📂 Buka & Eksplor Database", callback_data=f"opendb_{name}")],
            [InlineKeyboardButton("❌ Hapus dari Daftar", callback_data=f"deldb_{name}")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu_db")]
        ]
        await query.message.edit(f"🗄️ **Kelola Database: {name}**\nPilih aksi:", reply_markup=InlineKeyboardMarkup(buttons))
        
    elif data.startswith("deldb_"):
        name = data.split("_", 1)[1]
        doc = await get_user_doc(user_id)
        dbs = doc.get("databases", {})
        if name in dbs:
            del dbs[name]
            await update_user_doc(user_id, {"databases": dbs})
        await query.answer(f"Database {name} dihapus!", show_alert=True)
        await send_db_menu(query, user_id)
        
    elif data.startswith("opendb_"):
        name = data.split("_", 1)[1]
        doc = await get_user_doc(user_id)
        url = doc.get("databases", {}).get(name)
        
        await query.message.edit("🔄 Mencoba terhubung ke Database...")
        client_db = AsyncIOMotorClient(url, tlsCAFile=certifi.where())
        SECONDARY_DB_CLIENTS[f"{user_id}_db"] = client_db
        TEMP_DATA[f"{user_id}_dbname"] = name
        
        try:
            dbs = await client_db.list_database_names()
            target_db = next((d for d in dbs if d not in ["admin", "local"]), dbs[0])
            db = client_db[target_db]
            cols = await db.list_collection_names()
            
            TEMP_DATA[f"{user_id}_cols"] = cols 
            TEMP_DATA[f"{user_id}_target_db_name"] = target_db
            
            buttons = [[InlineKeyboardButton(f"📁 {c}", callback_data=f"opencol_{i}")] for i, c in enumerate(cols)]
            buttons.append([InlineKeyboardButton("🔙 Kembali ke Menu DB", callback_data=f"dbmenu_{name}")])
            
            await query.message.edit(f"🗄️ **Terhubung ke: {name} ({target_db})**\n📂 **Pilih Folder:**", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await query.message.edit(f"❌ Error koneksi DB: {str(e)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"dbmenu_{name}")]]))
            
    elif data.startswith("opencol_") or data.startswith("pgcol_"):
        is_page = data.startswith("pgcol_")
        val = int(data.split("_")[1])
        
        if not is_page:
            colname = TEMP_DATA[f"{user_id}_cols"][val]
            TEMP_DATA[f"{user_id}_activecol"] = colname
            page = 0
        else:
            colname = TEMP_DATA[f"{user_id}_activecol"]
            page = val
            
        client_db = SECONDARY_DB_CLIENTS.get(f"{user_id}_db")
        if not client_db:
            return await query.answer("Koneksi DB terputus. Silakan buka ulang dari awal.", show_alert=True)
            
        target_db = TEMP_DATA[f"{user_id}_target_db_name"]
        col = client_db[target_db][colname]
        db_alias = TEMP_DATA[f"{user_id}_dbname"]
        
        limit = 5
        skip = page * limit
        
        docs = await col.find({}).skip(skip).limit(limit).to_list(length=limit)
        total = await col.count_documents({})
        
        text = f"📂 **Isi Folder: `{colname}`** (Total Data: {total})\n\n"
        if not docs:
            text += "_Folder ini kosong._"
        else:
            for i, d in enumerate(docs):
                text += f"**{skip + i + 1}.** `{str(d)[:150]}...`\n"
                
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"pgcol_{page-1}"))
        if skip + limit < total:
            buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"pgcol_{page+1}"))
            
        layout = [buttons] if buttons else []
        layout.append([InlineKeyboardButton("🔙 Keluar Folder", callback_data=f"opendb_{db_alias}")])
        
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(layout))
