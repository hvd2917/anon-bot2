
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

API_TOKEN = "8434961706:AAGl85iuVzvIxFdtP8cyB3tvFJ40Nwr9SyI"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# словники для збереження ніків і користувачів
user_nicks = {}   # user_id -> nick
chat_members = set()

# команда старту
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "Привіт! 👋 Введи свій нік для анонімного чату:"
    )

# перше повідомлення з ніком
@dp.message(lambda msg: msg.from_user.id not in user_nicks)
async def set_nick(message: types.Message):
    nick = message.text.strip()
    user_nicks[message.from_user.id] = nick
    chat_members.add(message.from_user.id)
    await message.answer(f"✅ Твій нік встановлено: {nick}\nТепер можеш писати у чат!")

# обробка всіх інших повідомлень
@dp.message()
async def relay_message(message: types.Message):
    sender_id = message.from_user.id
    nick = user_nicks.get(sender_id, "Анонім")

    text = message.text

    # розсилаємо всім, крім відправника
    for uid in chat_members:
        if uid != sender_id:
            try:
                await bot.send_message(uid, f"**{nick}:** {text}", parse_mode="Markdown")
            except:
                pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
