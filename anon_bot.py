import asyncio
import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ==== Settings ====
API_TOKEN = os.getenv("API_TOKEN")  # Telegram bot token
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Your Telegram ID for notifications
DB_PATH = os.getenv("DB_PATH", "chat.db")  # SQLite path; use /data/chat.db on Render Paid

if not API_TOKEN or not ADMIN_ID:
    raise ValueError("Set API_TOKEN and ADMIN_ID in Environment Variables")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot=bot)

# ==== User data ====
user_nicks = {}          # user_id -> nick
chat_members = set()     # users who have set a nick
waiting_for_nick = set() # users currently entering a nick

# ==== DB setup ====
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()
conn.close()

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

def add_message(user_id: int, nick: str, content_type: str, text: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (user_id, content_type, text) VALUES (?, ?, ?)",
        (user_id, content_type, text)
    )
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return msg_id

def get_message_preview(msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT content_type, text FROM messages WHERE id=?", (msg_id,)).fetchone()
    conn.close()
    if not row:
        return ""
    content_type, text = row
    if content_type == "text":
        preview = text[:50] + ("..." if len(text) > 50 else "")
    elif content_type == "photo":
        preview = "📷 Photo"
    elif content_type == "video":
        preview = "📹 Video"
    elif content_type == "document":
        preview = "📎 Document"
    elif content_type == "voice":
        preview = "🎤 Voice"
    elif content_type == "audio":
        preview = "🎵 Audio"
    else:
        preview = "🗂 Message"
    return preview

# ==== Commands ====
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    waiting_for_nick.add(user_id)
    await message.answer("Hello! 👋 Enter your name for the anonymous chat:")

@dp.message(Command("name"))
async def change_nick_cmd(message: types.Message):
    user_id = message.from_user.id
    waiting_for_nick.add(user_id)
    await message.answer("✏️ Enter your new name:")

@dp.message(Command("members"))
async def members_cmd(message: types.Message):
    # Remove unavailable users
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

# ==== Message handling ====
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    # Set or change nick
    if user_id in waiting_for_nick:
        nick = text
        add_user(user_id, nick)
        user_nicks[user_id] = nick
        chat_members.add(user_id)
        waiting_for_nick.remove(user_id)
        await message.answer(f"✅ Your name is set: {nick}\nYou can now chat!")
        return

    # Relay messages to all others
    if user_id in chat_members:
        nick = user_nicks[user_id]
        msg_id = add_message(user_id, nick, message.content_type, text or message.caption)
        reply_text = ""
        if message.reply_to_message:
            reply_text = f"(Reply to: {get_message_preview(msg_id-1)})\n"

        to_remove = set()
        for uid in chat_members:
            if uid == user_id:
                continue
            try:
                # Text
                if message.text:
                    await bot.send_message(uid, f"{reply_text}**{nick}:** {text}", parse_mode="Markdown")
                # Photo
                if message.photo:
                    await bot.send_photo(uid, message.photo[-1].file_id, caption=f"{reply_text}**{nick}:** {message.caption or ''}", parse_mode="Markdown")
                # Video
                if message.video:
                    await bot.send_video(uid, message.video.file_id, caption=f"{reply_text}**{nick}:** {message.caption or ''}", parse_mode="Markdown")
                # Audio
                if message.audio:
                    await bot.send_audio(uid, audio=message.audio.file_id, caption=f"{reply_text}**{nick}**")
                # Voice
                if message.voice:
                    await bot.send_voice(uid, voice=message.voice.file_id, caption=f"{reply_text}**{nick}**")
                # Document
                if message.document:
                    await bot.send_document(uid, document=message.document.file_id, caption=f"{reply_text}**{nick}**")

            except Exception as e:
                to_remove.add(uid)
                try:
                    await bot.send_message(ADMIN_ID, f"⚠️ User {uid} unavailable: {e}")
                except:
                    pass
        for uid in to_remove:
            chat_members.discard(uid)
            user_nicks.pop(uid, None)

# ==== HeartBeat ====
async def heartbeat():
    while True:
        try:
            await bot.send_message(ADMIN_ID, "✅ Bot is running smoothly")
        except:
            pass
        await asyncio.sleep(3600)

# ==== Main ====
async def main():
    asyncio.create_task(heartbeat())
    try:
        await dp.start_polling(bot)
    except Exception as e:
        try:
            await bot.send_message(ADMIN_ID, f"❌ Bot crashed: {e}")
        except:
            print(f"Failed to notify admin: {e}")

if __name__ == "__main__":
    asyncio.run(main())
