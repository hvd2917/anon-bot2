import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Telegram token з Replit Secrets
API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    raise ValueError("Вкажи API_TOKEN у Secrets Replit")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot=bot)

# словники для ніків та користувачів
user_nicks = {}   # user_id -> nick
chat_members = set()

# команда /start
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привіт! 👋 Введи свій нік для анонімного чату:")

# обробка повідомлень
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id

    # встановлюємо нік, якщо його ще немає
    if user_id not in user_nicks:
        nick = message.text.strip()
        user_nicks[user_id] = nick
        chat_members.add(user_id)
        await message.answer(f"✅ Твій нік встановлено: {nick}\nТепер можеш писати у чат!")
        return

    # розсилка повідомлень всім, крім відправника
    nick = user_nicks[user_id]
    text = message.text
    for uid in chat_members:
        if uid != user_id:
            try:
                await bot.send_message(uid, f"**{nick}:** {text}", parse_mode="Markdown")
            except:
                pass

# запуск бота
async def main():
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Помилка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
