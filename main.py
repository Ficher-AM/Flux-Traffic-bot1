from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from app import handlers
import os
from dotenv import load_dotenv
import logging
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


load_dotenv()

logging.basicConfig(level=logging.INFO)


BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    exit("Error: no token pr                                                                                                                                                          и  ovided")

# Создаем объекты бота и диспетчерая
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

dp.include_router(handlers.router)

if __name__ == '__main__':
    dp.run_polling(bot)