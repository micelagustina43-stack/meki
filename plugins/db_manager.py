from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from database import save_user_data, get_user_data

# Menyimpan koneksi sekunder agar tidak perlu connect ulang terus
secondary_clients = {}

@Client.on_message(filters.command("setdb") & filters.private)
async def set_secondary_db(client, message):
    if len(message.command) < 2:
        return await message.reply("Gunakan format: `/setdb [URL_MONGO_SEKUNDER]`")
    
    db_url = message.command[1]
    user_id = message.from_user.id
    
    # Simpan URL ke DB Utama
    await save_user_data(user_id, "sec_db", db_url)
    
    # Inisialisasi koneksi sekunder
    secondary_clients[user_id] = AsyncIOMotorClient(db_url)
    await message.reply("✅ URL Database Sekunder berhasil disimpan di DB Utama dan dikoneksikan!")

@Client.on_message(filters.command("db") & filters.private)
async def view_db_folders(client, message):
    user_id = message.from_user.id
    sec_url = await get_user_data(user_id, "sec_db")
    
    if not sec_url:
        return await message.reply("Anda belum mengatur DB Sekunder. Gunakan `/setdb [URL_MONGO_SEKUNDER]`.")
        
    if user_id not in secondary_clients:
        secondary_clients[user_id] = AsyncIOMotorClient(sec_url)
        
    sec_client = secondary_clients[user_id]
    
    try:
        # Mengambil daftar database yang ada di Mongo URL tersebut
        dbs = await sec_client.list_database_names()
        # Untuk kesederhanaan, kita ambil database pertama, atau buat konfigurasi khusus
        db_name = dbs[0] 
        db = sec_client[db_name]
        
        collections = await db.list_collection_names()
        
        text = f"📂 **Folders (Collections) di {db_name}:**\nSilakan pilih untuk melihat isi:"
        buttons = [[InlineKeyboardButton(col, callback_data=f"viewcol_{col}_0")] for col in collections]
        
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
        
    except Exception as e:
        await message.reply(f"❌ Error membaca DB: {str(e)}")

@Client.on_callback_query(filters.regex(r"^viewcol_"))
async def paginate_db_docs(client, callback_query):
    user_id = callback_query.from_user.id
    _, col_name, page_str = callback_query.data.split("_")
    page = int(page_str)
    
    sec_client = secondary_clients.get(user_id)
    if not sec_client:
        return await callback_query.answer("Koneksi DB hilang. Ulangi /db", show_alert=True)
        
    db_name = (await sec_client.list_database_names())[0]
    collection = sec_client[db_name][col_name]
    
    # Pagination dokumen
    limit = 5 # Menampilkan 5 dokumen per halaman
    skip = page * limit
    
    cursor = collection.find({}).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    total_docs = await collection.count_documents({})
    
    text = f"📂 **Isi Folder: `{col_name}`** (Total: {total_docs})\n\n"
    
    if not docs:
        text += "_Kosong_"
    else:
        for i, doc in enumerate(docs):
            # Batasi panjang string agar tidak membludak di chat Telegram
            doc_str = str(doc)[:150] 
            text += f"**{skip + i + 1}.** `{doc_str}...`\n"
            
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"viewcol_{col_name}_{page-1}"))
    if skip + limit < total_docs:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"viewcol_{col_name}_{page+1}"))
        
    # Tombol keluar (kembali ke root)
    buttons_layout = [buttons, [InlineKeyboardButton("🔙 Keluar Folder", callback_data="back_to_db")]]
    
    await callback_query.message.edit(text, reply_markup=InlineKeyboardMarkup(buttons_layout))

@Client.on_callback_query(filters.regex(r"^back_to_db$"))
async def back_to_db_root(client, callback_query):
    # Memanggil ulang fungsi list folder
    await view_db_folders(client, callback_query)
