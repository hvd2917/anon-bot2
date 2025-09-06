import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web
import asyncio

# ==== Settings ====
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") + WEBHOOK_PATH  # https://your-app.onrender.com

DB_PATH = os.getenv("DB_PATH", "chat.db")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ==== User data ====
user_nicks = {}          # user_id -> nick
chat_members = set()     # users who have set a nick
waiting_for_nick = set() # users entering a nick

# ==== DB setup ====
dir_path = os.path.dirname(DB_PATH)
if dir_path:
    os.makedirs(dir_path, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    nick TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    content_type TEXT,
    text TEXT,
    telegram_msg_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS pinned_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    user_id INTEGER,
    content_type TEXT,
    text TEXT
)
""")
conn.commit()
conn.close()

# ==== DB functions ====
def add_user(user_id: int, nick: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO users (user_id, nick) VALUES (?, ?)", (user_id, nick))
    conn.commit()
    conn.close()

def get_nick(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT nick FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else None

def add_message(user_id: int, content_type: str, text: str, telegram_msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (user_id, content_type, text, telegram_msg_id) VALUES (?, ?, ?, ?)",
        (user_id, content_type, text, telegram_msg_id)
    )
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return msg_id

def pin_message(message_id, user_id, content_type, text):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO pinned_messages (message_id, user_id, content_type, text) VALUES (?, ?, ?, ?)",
        (message_id, user_id, content_type, text)
    )
    conn.commit()
    conn.close()

def get_pinned_messages():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT user_id, content_type, text FROM pinned_messages ORDER BY id").fetchall()
    conn.close()
    return rows

# ==== Commands ====
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    waiting_for_nick.add(user_id)
    await message.answer("Hello! 👋 Enter your name for the anonymous chat:")

    # send pinned messages
    pinned = get_pinned_messages()
    for uid, content_type, text in pinned:
        sender_nick = get_nick(uid) or "Anonymous"
        try:
            if content_type == "text":
                await message.answer(f"📌 {sender_nick}: {text}")
        except:
            pass

@dp.message(Command("name"))
async def change_nick_cmd(message: types.Message):
    user_id = message.from_user.id
    waiting_for_nick.add(user_id)
    await message.answer("✏️ Enter your new name:")

@dp.message(Command("members"))
async def members_cmd(message: types.Message):
    to_remove = set()
    for uid in chat_members:
        try:
            await bot.send_chat_action(uid, "typing")
        except:
            to_remove.add(uid)
    for uid in to_remove:
        chat_members.discard(uid)
        user_nicks.pop(uid, None)
    
    if not chat_members:
        await message.answer("The chat is empty 😕")
        return
    
    nick_list = [user_nicks[uid] for uid in chat_members]
    await message.answer("👥 Active chat members:\n" + "\n".join(f"- {n}" for n in nick_list))

@dp.message(Command("pinned"))
async def pinned_cmd(message: types.Message):
    pinned = get_pinned_messages()
    if not pinned:
        await message.answer("No pinned messages yet 📌")
        return
    text = "📌 Pinned messages:\n"
    for uid, content_type, txt in pinned:
        nick = get_nick(uid) or "Anonymous"
        text += f"- {nick}: {txt}\n"
    await message.answer(text)

@dp.message(Command("pin"))
async def pin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Only admin can pin messages")
        return

    if not message.reply_to_message:
        await message.answer("Reply to the message you want to pin with /pin")
        return

    content_type = message.reply_to_message.content_type
    text = message.reply_to_message.text or message.reply_to_message.caption or ""
    telegram_msg_id = message.reply_to_message.message_id
    pin_message(telegram_msg_id, message.reply_to_message.from_user.id, content_type, text)
    await message.answer("✅ Message pinned")

# ==== Message handling ====
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    if user_id in waiting_for_nick:
        nick = text
        add_user(user_id, nick)
        user_nicks[user_id] = nick
        chat_members.add(user_id)
        waiting_for_nick.remove(user_id)
        await message.answer(f"✅ Your name is set: {nick}\nYou can now chat!")

        pinned = get_pinned_messages()
        for uid, content_type, txt in pinned:
            sender_nick = get_nick(uid) or "Anonymous"
            try:
                if content_type == "text":
                    await message.answer(f"📌 {sender_nick}: {txt}")
            except:
                pass
        return

    if user_id in chat_members:
        nick = user_nicks[user_id]
        to_remove = set()
        reply_to_id = message.reply_to_message.message_id if message.reply_to_message else None

        for uid in chat_members:
            if uid == user_id:
                continue
            try:
                if message.text:
                    sent = await bot.send_message(uid, f"**{nick}:** {text}", parse_mode="Markdown", reply_to_message_id=reply_to_id)
                    add_message(user_id, "text", text, sent.message_id)
                elif message.photo:
                    sent = await bot.send_photo(uid, message.photo[-1].file_id, caption=f"**{nick}:** {message.caption or ''}", parse_mode="Markdown", reply_to_message_id=reply_to_id)
                    add_message(user_id, "photo", message.caption or "", sent.message_id)
                elif message.video:
                    sent = await bot.send_video(uid, message.video.file_id, caption=f"**{nick}:** {message.caption or ''}", parse_mode="Markdown", reply_to_message_id=reply_to_id)
                    add_message(user_id, "video", message.caption or "", sent.message_id)
                elif message.audio:
                    sent = await bot.send_audio(uid, audio=message.audio.file_id, caption=f"**{nick}:**", reply_to_message_id=reply_to_id)
                    add_message(user_id, "audio", "", sent.message_id)
                elif message.voice:
                    sent = await bot.send_voice(uid, voice=message.voice.file_id, caption=f"**{nick}:**", reply_to_message_id=reply_to_id)
                    add_message(user_id, "voice", "", sent.message_id)
                elif message.document:
                    sent = await bot.send_document(uid, document=message.document.file_id, caption=f"**{nick}:**", reply_to_message_id=reply_to_id)
                    add_message(user_id, "document", message.document.file_name or "", sent.message_id)
            except Exception as e:
                to_remove.add(uid)
                try:
                    await bot.send_message(ADMIN_ID, f"⚠️ User {uid} unavailable: {e}")
                except:
                    pass
        for uid in to_remove:
            chat_members.discard(uid)
            user_nicks.pop(uid, None)

# ==== Webhook handler ====
async def handle_webhook(request):
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return web.Response()

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)

# ==== Heartbeat ====
async def heartbeat():
    while True:
        try:
            await bot.send_message(ADMIN_ID, "✅ Bot is running smoothly")
        except:
            pass
        await asyncio.sleep(3600)

# ==== Startup ====
async def on_startup():
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(heartbeat())

if __name__ == "__main__":
    import ssl
    port = int(os.getenv("PORT", 8443))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(on_startup())
    web.run_app(app, port=port)
