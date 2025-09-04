import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Беремо токен з Replit Secrets
API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    raise ValueError("Вкажи API_TOKEN у Secrets Replit")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot=bot)

# словники для ніків та користувачів
user_nicks = {}         # user_id -> nick
chat_members = set()    # користувачі, які вже ввели нік
waiting_for_nick = set()  # користувачі, які зараз вводять нік

# команда /start
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    waiting_for_nick.add(user_id)
    await message.answer("Привіт! 👋 Введи свій нік для анонімного чату:")

# команда /nick — зміна ніку
@dp.message(Command("nick"))
async def change_nick_cmd(message: types.Message):
    user_id = message.from_user.id
    waiting_for_nick.add(user_id)
    await message.answer("✏️ Введи новий нік, який хочеш встановити:")

# обробка всіх повідомлень
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    # Якщо користувач чекає на введення ніку
    if user_id in waiting_for_nick:
        nick = text
        user_nicks[user_id] = nick
        chat_members.add(user_id)
        waiting_for_nick.remove(user_id)
        await message.answer(f"✅ Твій нік встановлено: {nick}\nТепер можеш писати у чат!")
        return

    # Relay повідомлень всім іншим
    if user_id in chat_members:
        nick = user_nicks[user_id]
        for uid in chat_members:
            if uid != user_id:
                try:
                    await bot.send_message(uid, f"**{nick}:** {text}", parse_mode="Markdown")
                except:
                    pass
