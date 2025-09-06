import os
import asyncio
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ===== Settings =====
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.onrender.com
PORT = int(os.getenv("PORT", 8443))
DB_PATH = os.getenv("DB_PATH", "chat.db")  # use "/data/chat.db" on Paid plan

if not API_TOKEN or not ADMIN_ID or not WEBHOOK_URL:
    raise ValueError("Set API_TOKEN, ADMIN_ID, WEBHOOK_URL in Environment Variables")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"

# ===== Database =====
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                nick TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pinned_messages (
                message_id TEXT PRIMARY KEY,
                content TEXT
            )
        """)
        await db.commit()

asyncio.run(init_db())

# ===== In-memory structures =====
chat_members = set()
waiting_for_nick = set()
pinned_messages = {}

# ===== Commands =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    waiting_for_nick.add(user_id)
    await message.answer("Hello! 👋 Enter your nickname for the anonymous chat:")

@dp.message(Command("name"))
async def cmd_change_nick(message: types.Message):
    user_id = message.from_user.id
    waiting_for_nick.add(user_id)
    await message.answer("✏️ Enter your new nickname:")

@dp.message(Command("members"))
async def cmd_members(message: types.Message):
    if not chat_members:
        await message.answer("The chat is empty 😕")
        return
    nick_list = []
    async with aiosqlite.connect(DB_PATH) as db:
        for uid in chat_members:
            async with db.execute("SELECT nick FROM users WHERE user_id=?", (uid,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    nick_list.append(row[0])
    await message.answer("👥 Active chat members:\n" + "\n".join(f"- {n}" for n in nick_list))

@dp.message(Command("pin"))
async def cmd_pin(message: types.Message):
    if not message.reply_to_message:
        await message.answer("Reply to a message to pin it!")
        return
    content = f"{message.reply_to_message.text or '[non-text content]'}"
    pinned_messages[str(message.reply_to_message.message_id)] = content
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO pinned_messages (message_id, content) VALUES (?, ?)",
                         (str(message.reply_to_message.message_id), content))
        await db.commit()
    await message.answer("📌 Message pinned!")

# ===== Message Handler =====
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text or ""

    # Set or change nick
    if user_id in waiting_for_nick:
        nick = text.strip()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO users (user_id, nick) VALUES (?, ?)", (user_id, nick))
            await db.commit()
        chat_members.add(user_id)
        waiting_for_nick.remove(user_id)
        await message.answer(f"✅ Your nickname is set: {nick}\nYou can now chat!")

        # Send pinned messages
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT content FROM pinned_messages") as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    await message.answer(f"📌 Pinned: {row[0]}")
        return

    # Relay messages
    if user_id not in chat_members:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT nick FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            nick = row[0] if row else "Anonymous"

    to_remove = set()
    for uid in chat_members:
        if uid == user_id:
            continue
        try:
            # Text
            if message.text:
                if message.reply_to_message:
                    await bot.send_message(uid, f"**{nick} (reply):** {text}", parse_mode="Markdown")
                else:
                    await bot.send_message(uid, f"**{nick}:** {text}", parse_mode="Markdown")
            # Photo
            if message.photo:
                await bot.send_photo(uid, photo=message.photo[-1].file_id,
                                     caption=f"**{nick}:** {message.caption or ''}", parse_mode="Markdown")
            # Video
            if message.video:
                await bot.send_video(uid, video=message.video.file_id,
                                     caption=f"**{nick}:** {message.caption or ''}", parse_mode="Markdown")
            # Audio
            if message.audio:
                await bot.send_audio(uid, audio=message.audio.file_id)
            # Voice
            if message.voice:
                await bot.send_voice(uid, voice=message.voice.file_id)
            # Document
            if message.document:
                await bot.send_document(uid, document=message.document.file_id)
        except Exception as e:
            to_remove.add(uid)
            try:
                await bot.send_message(ADMIN_ID, f"⚠️ User {uid} unavailable: {e}")
            except: pass
    for uid in to_remove:
        chat_members.discard(uid)

# ===== Heartbeat =====
async def heartbeat():
    while True:
        try:
            await bot.send_message(ADMIN_ID, "✅ Bot is running")
        except: pass
        await asyncio.sleep(3600)

# ===== Webhook Server =====
async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.update_router.feed_update(update)  # ✅ correct for aiogram v3
    return web.Response(text="OK")

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)

# ===== Run =====
async def main():
    asyncio.create_task(heartbeat())
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Webhook running on {WEBHOOK_URL + WEBHOOK_PATH}")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
