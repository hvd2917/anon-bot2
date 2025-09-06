import asyncio
import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # твій Telegram ID

# Використовуємо Persistent Disk, якщо він є (наприклад /data/chat.db)
DB_PATH = os.getenv("DB_PATH", "chat.db")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ---------------- DB ---------------- #
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            nick TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)
    conn.commit()
    conn.close()

# ---------------- Bot logic ---------------- #
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привіт! 👋 Введи свій нік для анонімного чату:")

@dp.message()
async def handle_message(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT nick FROM users WHERE user_id=?", (message.from_user.id,))
    row = c.fetchone()

    if not row:
        nick = message.text.strip()
        c.execute("INSERT OR REPLACE INTO users (user_id, nick) VALUES (?, ?)", 
                  (message.from_user.id, nick))
        conn.commit()
        await message.answer(f"✅ Твій нік встановлено: {nick}")
    else:
        nick = row[0]
        c.execute("INSERT INTO messages (user_id, content) VALUES (?, ?)", 
                  (message.from_user.id, message.text))
        conn.commit()
        # Тут можна робити розсилку іншим учасникам
    conn.close()

# ---------------- Monitoring ---------------- #
async def monitor():
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("SELECT 1")
            conn.close()
        except Exception as e:
            if ADMIN_ID:
                await bot.send_message(ADMIN_ID, f"⚠️ Bot/DB error: {e}")
        await asyncio.sleep(60)  # перевірка щохвилини

# ---------------- Main ---------------- #
async def main():
    init_db()
    asyncio.create_task(monitor())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
