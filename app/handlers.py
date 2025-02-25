import os
import requests
import json
import asyncio
from aiogram import Router, Bot, types, F
from aiogram.filters import Command
import sqlite3
import datetime
from datetime import datetime, timedelta
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery ,InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramForbiddenError
from dotenv import load_dotenv, set_key
import logging
from lexicon.lexicon_ru import LEXICON_RU
from keyboards.keyboards import reply_kb, out1_kb, create_out, admin_panel_keyboard, register_btn, ok_rules_btn, \
    channels_check, support_btn, out_money_btn, admins_btn, add_money_btn
from db_manager import get_user_db, get_users_sorted_by, create_user_db, add_links, get_unused_link,get_user_rank, \
    mark_link_as_used, get_link_by_user_and_type, add_offer, get_offer_by_name, get_all_offers, \
    delete_offer, toggle_offer_status, get_offer_links, get_offer_manual_link, get_links_by_offer_id,update_user_balance, cursor, conn, get_referrals, calculate_referral_rewards
from db_manager import get_today_payouts, get_total_payouts, add_payout, get_daily_top, get_all_time_top
import pytz

router = Router()
load_dotenv()

# Константы
CRYPTO_BOT_API_TOKEN = os.getenv('CRYPTO_BOT_API_TOKEN')
MIN_WITHDRAWAL = int(os.getenv('MIN_WITHDRAWAL', 150))
USDT_RUB_RATE = float(os.getenv('USDT_RUB_RATE', 90))  # Получаем фиксированный курс
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    exit("Error: no token provided")

ADMINS = {int(admin_id) for admin_id in os.getenv('ADMINS', '7498299981').split(',')} #Получаем админов через os.getenv
CHANNELS = ["@FluxTraffic", "@Rekvils"]

POST_MESSAGE_ID = None
GROUP_CHAT_ID = "-1002423312131"

MESSAGE_ID_FILE = "post_message_id.txt"

bot = Bot(BOT_TOKEN)
logger = logging.getLogger(__name__)


# --- Перемещаем объявление класса CreateOutState сюда ---
class AdminState(StatesGroup):
    waiting_for_new_admin_id = State()
    waiting_for_del_admin_id = State()
    waiting_for_new_usdt_rate = State() # Добавлено новое состояние

class CreateOutState(StatesGroup):
    waiting_for_out_amount = State() #Состояние ожидания ввода суммы вывода

class AddOfferState(StatesGroup):
    waiting_for_offer_name = State()
    waiting_for_manual_link = State()
    waiting_for_price = State()
    waiting_for_links = State()

class Registration(StatesGroup):
    waiting_for_registration = State()

class Payout(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_payout_amount = State()

class BroadcastState(StatesGroup):
    waiting_for_broadcast_type = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_photo = State()
    waiting_for_broadcast_photo_with_text = State()

class AddMoneyState(StatesGroup):  # Новый класс состояний для начисления денег
    waiting_for_user_link = State()
    waiting_for_amount = State()

class DeleteLinksState(StatesGroup):
    waiting_for_links = State()

@router.callback_query(F.data == 'admin_cash_pressed')
async def admin_cash_callback(query: types.CallbackQuery):
    today_payouts = get_today_payouts()
    total_payouts = get_total_payouts()

    await query.message.answer(
        f"<b>💰Касса:</b>\n"
        f"├ Касса за сегодня: <b>{today_payouts}₽</b>\n"
        f"└ Касса за все время: <b>{total_payouts}₽</b>",
        parse_mode="HTML"
    )
    await query.answer()

@router.message(Command("Мут"))
async def mute_user(message: Message, bot: Bot):
    # Проверяем, что команда выполняется в группе или супергруппе
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах.")
        return

    # Проверяем, является ли отправитель команды админом
    if message.from_user.id not in ADMINS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    # Проверяем, является ли сообщение ответом на другое сообщение
    if not message.reply_to_message:
        await message.answer("Эта команда должна быть ответом на сообщение пользователя, которого нужно замутить.")
        return

    # Получаем ID пользователя, которого нужно замутить
    user_to_mute = message.reply_to_message.from_user.id

    # Получаем количество часов из текста команды
    try:
        hours = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("Неверный формат команды. Используйте: Мут {количество часов}")
        return

    # Вычисляем время окончания мута
    mute_until = datetime.now() + timedelta(hours=hours)

    # Блокируем пользователя на указанное время
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=user_to_mute,
            permissions=types.ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            ),
            until_date=mute_until
        )
        await message.answer(f"Пользователь лишен права слова на {hours} час(ов).")
        logger.info(f"Admin {message.from_user.id} замутил пользователя {user_to_mute} на {hours} часов.")
    except Exception as e:
        await message.answer(f"Не удалось замутить пользователя: {e}")
        logger.error(f"Ошибка при муте пользователя {user_to_mute}: {e}")

async def send_profit_notification(user_id: int, amount: float, offer_name: str):
    """Отправляет уведомление о выплате в группы."""
    user = get_user_db(user_id)
    if not user:
        logger.warning(f"User {user_id} not found in database.")
        return

    user_status = user[2]  # Статус пользователя
    referral_rewards = calculate_referral_rewards(user_id, amount, notify=False)

    # Формируем сообщение для групп с названием оффера
    message_text = (
        f"<b>🚀Профит у <a href='tg://user?id={user_id}'>{user_status}</a>!</b>\n\n"
        f"├ Направление: <b>{offer_name}</b>\n"
        f"└ Сумма: <b>{amount}₽</b>"
    )

    if referral_rewards:
        message_text += "\n\n<b>Доля рефереров:</b>\n"
        for ref_id, reward in referral_rewards.items():
            message_text += f"└ <a href='tg://user?id={ref_id}'>Реферер</a>: <b>{reward}₽</b>\n"

    # Получаем список всех групп, в которых состоит бот
    groups = await get_bot_groups()

    # Отправляем сообщение в каждую группу
    for group_id in groups:
        try:
            await bot.send_message(chat_id=group_id, text=message_text, parse_mode="HTML")
            logger.info(f"Сообщение отправлено в группу {group_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в группу {group_id}: {e}")

@router.message(F.text == LEXICON_RU['help_button'])
async def main_menu(message: Message):
    sticker_help = "CAACAgIAAxkBAAEMS4ZnpN8OyIqiB-w_xKdTzAABRrO1tyoAAgZOAALPqUBLprBrkUU-Dkc2BA"
    await bot.send_sticker(message.chat.id, sticker=sticker_help)
    await message.answer(text=LEXICON_RU['support_help'], reply_markup=support_btn)

@router.message(F.text == LEXICON_RU['referals_button'])
async def main_menu(message: Message):
    user_id = message.from_user.id
    user = get_user_db(user_id)
    if user is None:
        await message.answer("Пожалуйста, сначала запустите бота командой /start")
        return

    if user:
        earned_referrals = int(user[5])  # Заработанные реферальные вознаграждения
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        referral_link = f"https://t.me/{bot_username}?start={user_id}"

        # Получаем количество рефералов 1-го и 2-го уровня
        referrals_1_count, referrals_2_count = get_referrals(user_id)
        to_share_btn = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Поделиться", switch_inline_query=f"{referral_link}\n\nЗарабатываю на арбитраже трафика!Попробуй и ты!")]
        ])
        referrals = referrals_1_count + referrals_2_count
        await bot.send_photo(chat_id=message.chat.id,
                             photo="AgACAgIAAxkBAAIfemezg0JaTAbaVzN3pyhGVPNGm8ybAALW6jEbdJqgScv5Ce6gxgrwAQADAgADeQADNgQ",
                             caption=f'<a href="https://telegra.ph/Kak-i-gde-iskat-referalov-02-17">КАК И ГДЕ НАЙТИ РЕФЕРАЛОВ?</a>\n\n'
            f'❗<b>Реферал 1 уровня - это человек, который впервые заходит в бота по вашей ссылке.</b> Когда человек зайдёт в бота по вашей ссылке, он навсегда становится вашим рефералом 1 уровня. - Когда ваш <b>Реферал 1 уровня</b> получает выплату  вы получаете 5% от его заработка на ваш баланс\n\n'
            f'❗️<b>Реферал 2 уровня - это тот человек, который впервые заходит в бота по ссылке вашего Реферала 1 уровня.</b> - Когда ваш <b>Реферал 2 уровня</b> получает выплату за задание вы получаете 3% от его заработка на ваш баланс.'
            f'\n\n<b><tg-spoiler>⚠️Важно! Ваш партнерский процент не вычитается из заработка рефералов. Они получают все заработанные средства, а ваш бонус выплачивается отдельно.</tg-spoiler></b>'
            f'\n\n\n<b>👥Ваши рефералы:</b>\n\n'
            f'Приглашено рефералов всего: <b>{referrals}</b>\n'
            f'Заработано с рефералов: <b>{earned_referrals}₽</b>\n\n'
            f'<b>🔗Ваша реферальная ссылка:</b>\n<code>{referral_link}</code>\n\n'
            f'<b>1️⃣Рефералов 1-го уровня:\n└ {referrals_1_count}</b>\n\n'
            f'<b>2️⃣Рефералов 2-го уровня:\n└ {referrals_2_count}</b>',
                             reply_markup=to_share_btn,
                             parse_mode="HTML")

@router.message(F.text == LEXICON_RU['profile_button'])
async def main_menu(message: Message):
    user_id = message.from_user.id
    user = get_user_db(user_id)
    if user is None:
        await message.answer("Пожалуйста, сначала запустите бота командой /start")
        return

    if user:
        date_entrance = user[1]
        level = user[2]  # Статус пользователя
        balance = int(user[4])  # Текущий баланс
        total_earned = int(user[8])  # Общая сумма заработанных средств
        earned_referrals = int(user[5])  # Заработанные реферальные вознаграждения
        referrals_1_count, referrals_2_count = get_referrals(user_id)
        referrals = referrals_1_count + referrals_2_count

        users_by_balance = get_users_sorted_by('balance')
        users_by_referrals = get_users_sorted_by('referrals')
        users_by_earned_referrals = get_users_sorted_by('earned_referrals')

        place_balance = get_user_rank(user_id, users_by_balance)
        place_referals = get_user_rank(user_id, users_by_referrals)
        place_earned_referrals = get_user_rank(user_id, users_by_earned_referrals)


        sticker_profile = "CAACAgIAAxkBAAEMWeZnp0q1OyUGKUAj9H85by9j_52fZgACwksAAhauQEuV2Of_Z6zJ2DYE"
        await bot.send_sticker(message.chat.id, sticker=sticker_profile)
        await message.answer(
            f'<b>🪪Ваш профиль:</b>\n\nID: <b>{message.from_user.id}</b>\nРегистрация: <b>{date_entrance}</b>'
            f'\nСтатус: <b>{level}</b>'
            f'\n\nБаланс: <b>{balance}₽</b>'
            f'\nЗаработано всего: <b>{total_earned}₽</b>\n\n'
            f'👨‍👩‍👦‍👦Приглашено рефералов: <b>{referrals}</b>\nЗаработано с рефералов: <b>{earned_referrals}₽</b>'
            f'\n\n<b>📊Место в топе:</b>\n├ по заработку: {place_balance}'
            f'\n└ по заработку с рефералов: {place_earned_referrals}', reply_markup=out_money_btn)

@router.message(F.text == LEXICON_RU['traffic_button'])
async def traffic_directions(message: Message):
    sticker_up = "CAACAgIAAxkBAAEMXP9np7g49h39298OLMkR0niMkoEKxwAC904AAguVQEsXvniq50hS0zYE"
    await bot.send_sticker(message.chat.id, sticker=sticker_up)

    # #1 - Получаем список активных офферов
    offers = get_all_offers()
    active_offers = [offer for offer in offers if offer[2] == 1]
    print(active_offers)
    # #2 - Создаем инлайн кнопки
    buttons = []
    for offer in active_offers:
        buttons.append([InlineKeyboardButton(text=f"{offer[1]} - {offer[4]}₽", callback_data=f'{offer[1]}_button_pressed')])  # Добавили цену в текст кнопки

    if buttons:
        directions_btn = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text=LEXICON_RU['traffic_directions'], reply_markup=directions_btn)
    else:
        await message.answer("<b>Нет активных направлений для трафика</b>")

@router.message(F.text == LEXICON_RU['manuals_button'])
async def main_menu(message: Message):
    sticker_manuals = "CAACAgIAAxkBAAEMXRtnp7ouPSh4VzpkcUkFSU1YWeaOdwACiFUAAohbQUsAAeKA_M0E9ts2BA"
    await bot.send_sticker(message.chat.id, sticker=sticker_manuals)
    await bot.send_photo(chat_id=message.chat.id,
                         photo="AgACAgIAAxkBAAIZu2ent2YgDzt5hH2eo9o4YZy3s7P7AAK77zEbFkNASfvPZRvPEEP7AQADAgADeQADNgQ",
                         caption=LEXICON_RU['manuals'],
                         parse_mode="HTML")

@router.message(F.text == LEXICON_RU['out1_button'])
async def main_menu(message: Message):
    await message.answer('⬇<b>Вы вернулись назад</b>', reply_markup=reply_kb)

@router.callback_query(lambda c: c.data.startswith('delete_links_offer_'))
async def delete_links_offer_callback(query: types.CallbackQuery, state: FSMContext):
    offer_id = int(query.data.split('_')[3])  # Получаем ID оффера из callback_data
    await state.update_data(offer_id=offer_id)  # Сохраняем ID оффера в состояние
    await query.message.answer("<b>Введите ссылку или ссылки, которые вы хотите удалить (через запятую):</b>")
    await state.set_state(DeleteLinksState.waiting_for_links)
    await query.answer()

@router.message(DeleteLinksState.waiting_for_links)
async def process_delete_links(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        offer_id = data['offer_id']  # Получаем ID оффера из состояния
        links_to_delete = message.text.split(',')  # Разделяем ссылки по запятой

        # Удаляем каждую ссылку из базы данных
        for link in links_to_delete:
            link = link.strip()  # Убираем лишние пробелы
            cursor.execute("DELETE FROM links WHERE link = ? AND offer_id = ?", (link, offer_id))
            conn.commit()

        await message.answer(f"<b>Ссылки успешно удалены для оффера с ID {offer_id}.</b>")
    except Exception as e:
        logger.error(f"Error deleting links: {e}")
        await message.answer(f"<b>Ошибка при удалении ссылок: {e}</b>")
    finally:
        await state.clear()

def load_message_id():
    """Загружает сохраненный message_id из файла"""
    global POST_MESSAGE_ID
    if os.path.exists(MESSAGE_ID_FILE):
        with open(MESSAGE_ID_FILE, 'r') as f:
            try:
                POST_MESSAGE_ID = int(f.read().strip())
            except ValueError:
                POST_MESSAGE_ID = None

def save_message_id(message_id):
    """Сохраняет message_id в файл"""
    global POST_MESSAGE_ID
    POST_MESSAGE_ID = message_id
    with open(MESSAGE_ID_FILE, 'w') as f:
        f.write(str(message_id))

def format_number(number):
    """Форматирует число с пробелами как разделителями тысяч"""
    return "{:,}".format(int(number)).replace(",", " ")

def get_moscow_time():
    """Получает текущее время в Москве"""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow_tz).strftime("%H:%M")


def create_post_message():
    """Создает текст сообщения для поста"""
    total_payouts = get_total_payouts()
    today_payouts = get_today_payouts()
    update_time = get_moscow_time()

    return (
        "⚡️F.T. (@FluxTrafficBot)\n\n"
        "<b><a href=\"https://t.me/FluxTraffic\">•Основной канал</a>\n"
        "<a href=\"https://t.me/+nhNNbOA_nTNmYWNi\">•Канал с выплатами</a>\n"
        "<a href=\"https://t.me/FeedbackTrafficBot\">•Тех.Поддержка</a>"
        "<a href=\"https://telegra.ph/Pravila-obshcheniya-v-Flux-Traffic--CHat-02-22\">•Правила чата</a></b>\n\n"
        f"💰Всего заработано: <b>{format_number(total_payouts)}₽</b>\n"
        f"└Касса за сегодня: <b>{format_number(today_payouts)}₽</b>\n\n"
        f"Время последнего обновления: <b>{update_time} по МСК</b>"
    )

load_message_id()


@router.message(Command("post"))
async def post_command(message: types.Message, bot: Bot):
    """Обработчик команды /post для первого создания сообщения"""
    global POST_MESSAGE_ID

    if message.from_user.id not in ADMINS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    if POST_MESSAGE_ID is not None:
        await message.answer("Сообщение уже было создано ранее. Оно будет обновляться автоматически при профитах.")
        return

    try:
        # Отправляем новое сообщение
        sent_message = await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=create_post_message(),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        save_message_id(sent_message.message_id)
        await message.answer("Пост успешно опубликован! Теперь он будет обновляться автоматически при каждом профите.")
    except Exception as e:
        logger.error(f"Error in post_command: {e}")
        await message.answer(f"Произошла ошибка при публикации поста: {e}")


async def update_post_message(bot: Bot):
    """Обновляет существующее сообщение"""
    global POST_MESSAGE_ID
    if POST_MESSAGE_ID is not None:
        try:
            await bot.edit_message_text(
                chat_id=GROUP_CHAT_ID,
                message_id=POST_MESSAGE_ID,
                text=create_post_message(),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error updating post message: {e}")

async def send_profit_notification(user_id: int, amount: float, offer_name: str, bot: Bot):
    """Отправляет уведомление о выплате в группы и обновляет пост"""
    user = get_user_db(user_id)
    if not user:
        logger.warning(f"User {user_id} not found in database.")
        return

    user_status = user[2]  # Статус пользователя
    referral_rewards = calculate_referral_rewards(user_id, amount, notify=False)

    # Формируем сообщение для групп с названием оффера
    message_text = (
        f"<b>🚀Профит у <a href='tg://user?id={user_id}'>{user_status}</a>!</b>\n\n"
        f"├ Направление: <b>{offer_name}</b>\n"
        f"└  Сумма: <b>{amount}₽</b>"
    )

    if referral_rewards:
        message_text += "\n\n<b>Доля рефереров:</b>\n"
        for ref_id, reward in referral_rewards.items():
            message_text += f"└ <a href='tg://user?id={ref_id}'>Реферер</a>: <b>{reward}₽</b>\n"

    # Получаем список всех групп
    groups = await get_bot_groups()

    # Отправляем сообщение в каждую группу
    for group_id in groups:
        try:
            await bot.send_message(
                chat_id=group_id,
                text=message_text,
                parse_mode="HTML"
            )
            logger.info(f"Сообщение отправлено в группу {group_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в группу {group_id}: {e}")

    # Обновляем пост после отправки уведомления
    await update_post_message(bot)

# Модифицируем process_amount для автоматического обновления
@router.message(AddMoneyState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        data = await state.get_data()
        user_id = data['user_id']

        # Получаем уникальную ссылку из состояния
        user_link = data.get('user_link')

        # Получаем offer_id по ссылке
        cursor.execute("SELECT offer_id FROM links WHERE link = ?", (user_link,))
        offer_data = cursor.fetchone()
        if not offer_data:
            await message.answer("<b>Не удалось определить оффер по данной ссылке.</b>")
            await state.clear()
            return
        offer_id = offer_data[0]

        # Получаем название оффера
        cursor.execute("SELECT name FROM offers WHERE id = ?", (offer_id,))
        offer_name_data = cursor.fetchone()
        offer_name = offer_name_data[0] if offer_name_data else "Неизвестный оффер"

        # Обновляем баланс и общую сумму заработанных средств
        update_user_balance(user_id, amount, update_total_earned=True)

        # Начисляем реферальные вознаграждения
        calculate_referral_rewards(user_id, amount)

        # Записываем выплату в базу данных
        add_payout(user_id, amount)

        # Отправляем сообщение пользователю
        sticker_profit = 'CAACAgIAAxkBAAEMoSdnsj5lKqu2hSV-KommMRkAAVijGIAAAjVRAALsBEhLL_BaF7G5Chk2BA'
        await bot.send_sticker(user_id, sticker_profit)
        await bot.send_message(
            user_id,
            f"<b>🚀Успешный профит!</b>\n├ Направление: <b>{offer_name}</b>\n└  Сумма профита: <b>{amount}₽</b>",
            parse_mode="HTML"
        )

        # Отправляем уведомление в группы и обновляем пост
        await send_profit_notification(user_id, amount, offer_name, bot)

        await message.answer(f"<b>Успешно начислено {amount}₽ пользователю с ID {user_id} по офферу '{offer_name}'.</b>")
    except ValueError:
        await message.answer("<b>Неверный формат суммы. Пожалуйста, введите число.</b>")
    except Exception as e:
        logger.error(f"Error in process_amount: {e}")
        await message.answer(f"<b>Ошибка при обработке запроса на выплату: {e}</b>")
    finally:
        await state.clear()

def create_crypto_bot_check(amount_usdt: float, user_id: int) -> str | None:
    """Создает чек в Crypto Bot для USDT. Возвращает ссылку на чек или None в случае ошибки."""
    url = "https://pay.crypt.bot/api/createCheck"

    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_API_TOKEN,
        "Content-Type": "application/json",
    }
    amount_usdt = round(amount_usdt, 8)  # Округляем до 8 знаков после запятой
    data = {
        "asset": "USDT",
        "amount": str(amount_usdt),
        "pin_to_user_id": user_id
    }
    logger.info(f"create_crypto_bot_check request {data}")  # Log request data
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        result = response.json()
        if result and result['ok']:
            return result['result']['bot_check_url']
        else:
            logger.error(f"Error creating check: {result}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with Crypto Bot: {e}")
        logger.error(f"Response: {response.text}")  # Логируем тело ответа
        return None
    except KeyError as e:
        logger.error(f"Unexpected response from Crypto Bot API: Missing key {e} in the response.")
        return None



# Модифицируем process_amount для обновления поста после выплаты
@router.message(AddMoneyState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    global POST_MESSAGE_ID

    try:
        amount = float(message.text)
        data = await state.get_data()
        user_id = data['user_id']

        # Получаем уникальную ссылку из состояния
        user_link = data.get('user_link')

        # Получаем offer_id по ссылке
        cursor.execute("SELECT offer_id FROM links WHERE link = ?", (user_link,))
        offer_data = cursor.fetchone()
        if not offer_data:
            await message.answer("<b>Не удалось определить оффер по данной ссылке.</b>")
            await state.clear()
            return
        offer_id = offer_data[0]

        # Получаем название оффера
        cursor.execute("SELECT name FROM offers WHERE id = ?", (offer_id,))
        offer_name_data = cursor.fetchone()
        offer_name = offer_name_data[0] if offer_name_data else "Неизвестный оффер"

        # Обновляем баланс и общую сумму заработанных средств
        update_user_balance(user_id, amount, update_total_earned=True)

        # Начисляем реферальные вознаграждения
        calculate_referral_rewards(user_id, amount)

        # Записываем выплату в базу данных
        add_payout(user_id, amount)

        # Отправляем сообщение пользователю
        sticker_profit = 'CAACAgIAAxkBAAEMoSdnsj5lKqu2hSV-KommMRkAAVijGIAAAjVRAALsBEhLL_BaF7G5Chk2BA'
        await bot.send_sticker(user_id, sticker_profit)
        await bot.send_message(
            user_id,
            f"<b>🚀Успешный профит!</b>\n├ Направление: <b>{offer_name}</b>\n└ Сумма профита: <b>{amount}₽</b>",
            parse_mode="HTML"
        )

        # Отправляем сообщение в группы
        await send_profit_notification(user_id, amount, offer_name)

        # Обновляем пост в группе
        if POST_MESSAGE_ID:
            await bot.edit_message_text(
                chat_id=GROUP_CHAT_ID,
                message_id=POST_MESSAGE_ID,
                text=create_post_message(),
                parse_mode="HTML",
                disable_web_page_preview=True
            )

        await message.answer(
            f"<b>Успешно начислено {amount}₽ пользователю с ID {user_id} по офферу '{offer_name}'.</b>")
    except ValueError:
        await message.answer("<b>Неверный формат суммы. Пожалуйста, введите число.</b>")
    except Exception as e:
        logger.error(f"Error in process_amount: {e}")
        await message.answer(f"<b>Ошибка при обработке запроса на выплату: {e}</b>")
    finally:
        await state.clear()

@router.callback_query(F.data == 'manuals_support_button_pressed')
async def ok_rules_button_pressed(callback: types.CallbackQuery):
    await callback.message.delete()
    sticker_manuals = "CAACAgIAAxkBAAEMXRtnp7ouPSh4VzpkcUkFSU1YWeaOdwACiFUAAohbQUsAAeKA_M0E9ts2BA"
    await bot.send_sticker(callback.message.chat.id, sticker=sticker_manuals)
    await bot.send_photo(chat_id=callback.message.chat.id,
                         photo="AgACAgIAAxkBAAIZu2ent2YgDzt5hH2eo9o4YZy3s7P7AAK77zEbFkNASfvPZRvPEEP7AQADAgADeQADNgQ",
                         caption=LEXICON_RU['manuals'],
                         parse_mode="HTML")

@router.message(CreateOutState.waiting_for_out_amount)
async def process_out_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        user_id = message.from_user.id
        user = get_user_db(user_id)
        if user is None:
            await message.answer("<b>Пожалуйста, сначала запустите бота командой /start</b>")
            await state.clear()
            return

        earned = int(user[4])
        if amount < MIN_WITHDRAWAL:
            sticker_noyp = "CAACAgIAAxkBAAEMXRdnp7nMqVHBYUFaYsqYi-oHG6rVSQACrE8AAjUMSUu4nD3i5jky1TYE"
            await bot.send_sticker(message.chat.id, sticker=sticker_noyp)
            await message.answer(f"<b>Минимальная сумма для вывода {MIN_WITHDRAWAL}₽</b>", reply_markup=reply_kb)
            await state.clear()
            return
        if amount > earned:
            sticker_cry = "CAACAgIAAxkBAAEMXRFnp7mMseKJ7RAy3dVNbpbysMUPzgACxEoAAn72QUt--FTNDz-CATYE"
            await bot.send_sticker(message.chat.id, sticker=sticker_cry)
            await message.answer("<b>Сумма вывода превышает ваш баланс</b>", reply_markup=reply_kb)
            await state.clear()
            return

        #  Конвертируем рубли в USDT
        amount_usdt = amount / USDT_RUB_RATE

        check_link = create_crypto_bot_check(amount_usdt, user_id) # Используем create_crypto_bot_check

        if check_link:
            await message.answer(f"<b>Ваш чек на {amount:.2f}₽ ({amount_usdt:.2f} USDT):</b>\n{check_link}", reply_markup=reply_kb)  # Изменили текст
            update_user_balance(user_id, -amount)
        else:
            await message.answer("<b>Ошибка создания чека. Попробуйте позже.</b>", reply_markup=reply_kb)

    except ValueError:
        await message.answer("<b>Неверный формат суммы. Пожалуйста, введите число.</b>", reply_markup=reply_kb)
    except Exception as e:
        logger.exception(f"Error in process_out_amount: {e}")
        await message.answer(f"<b>Ошибка при обработке запроса на вывод: {e}</b>", reply_markup=reply_kb)
    finally:
      await state.clear()

async def get_bot_groups():
    """Возвращает список ID групп, в которых состоит бот."""
    # Пример реальных ID групп
    groups = [
        -1002423312131,  # Замените на реальные ID групп
        -1002450691631
    ]
    return groups

def create_crypto_bot_invoice_app(amount_usdt: float) -> str | None:
   """Создает инвойс (чек) в Crypto Bot для пополнения баланса приложения. Возвращает ссылку на инвойс или None в случае ошибки."""
   url = "https://pay.crypt.bot/api/createInvoice"  # URL для основного API (Mainnet)
   # url = "https://testnet-pay.crypt.bot/api/createInvoice"  # URL для тестовой сети (Testnet)
   headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_API_TOKEN,
       "Content-Type": "application/json",
   }
   data = {
        "asset": "USDT",  # Обязательно указываем USDT
        "amount": str(amount_usdt),  # Сумма в USDT (строкой)
       "description": f"Пополнение баланса приложения на сумму {amount_usdt:.2f} USDT"
   }
   logger.info(f"create_crypto_bot_invoice_app request: {data}")
   try:
      response = requests.post(url, headers=headers, data=json.dumps(data))
      response.raise_for_status()  # Проверяем статус ответа
      result = response.json()
      if result and result['ok']:
          #  Возвращаем URL инвойса
          return result['result']['bot_invoice_url']
      else:
           logger.error(f"Error creating invoice: {result}")
           return None
   except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with Crypto Bot: {e}")
        return None
   except KeyError as e:
       logger.error(f"Unexpected response from Crypto Bot API: Missing key {e} in the response.")
       return None


class AddMoneyState(StatesGroup):  # Новый класс состояний для начисления денег
    waiting_for_user_link = State()
    waiting_for_amount = State()


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Проверяет, подписан ли пользователь на все каналы."""
    for channel in CHANNELS:
        try:
            chat_member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                return False  # Пользователь не подписан на канал
        except TelegramForbiddenError:
            logger.warning(f"Could not get chat member for channel {channel} for user {user_id}.")
            return False  # Бот не имеет доступа к каналу
        except Exception as e:
            logger.exception(f"Unexpected error while checking subscription for user {user_id} in {channel}: {e}")
            return False  # Произошла ошибка
    return True  # Пользователь подписан на все каналы

class AddBalanceState(StatesGroup):
    waiting_for_amount = State()
@router.message(Command("add"))
async def add_balance_command(message: types.Message, state: FSMContext):
  await message.answer("<b>Введите сумму в рублях для пополнения баланса приложения</b>")
  await state.set_state(AddBalanceState.waiting_for_amount)
@router.message(AddBalanceState.waiting_for_amount)
async def process_add_balance_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0:
            await message.answer("<b>Сумма должна быть больше нуля.</b>")
            await state.clear()
            return
        amount_usdt = amount / USDT_RUB_RATE
        invoice_link = create_crypto_bot_invoice_app(amount_usdt)
        if invoice_link:
           await message.answer(f"<b>Перейдите по ссылке чтобы пополнить баланс приложения на сумму {amount:.2f}₽:</b>\n{invoice_link}")
        else:
           await message.answer("<b>Ошибка при создании счета.</b>")
    except ValueError:
         await message.answer("<b>Неверный формат суммы. Пожалуйста, введите число.</b>")
    except Exception as e:
        logger.exception(f"Error in process_add_balance_amount: {e}")
        await message.answer(f"<b>Ошибка при обработке запроса на пополнение: {e}</b>")
    finally:
         await state.clear()



def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMINS

def update_admins_env():
    """Обновляет переменную ADMINS в файле .env"""
    admins_str = ",".join(map(str, ADMINS))
    set_key(".env", "ADMINS", admins_str)


@router.message(Command("start"), F.chat.type == "private")
async def process_start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    referrer_id = None  # Реферер 1-го уровня
    referrer_id_2 = None  # Реферер 2-го уровня

    # Проверяем подписку на каналы
    if not await check_subscription(bot, user_id):
        sticker_check = "CAACAgIAAxkBAAEMS5VnpOB5a-N4fuKOP1aGhhKhA7TS4AACaUkAAknSQUvGaTcGapfS_TYE"
        await bot.send_sticker(message.chat.id, sticker=sticker_check)
        await message.answer(
            "<b>Для использования бота подпишитесь на наши каналы:</b>\n\n1)Наш информационный канал\n2)Канал со схемами заработка",
            reply_markup=channels_check  # Клавиатура с кнопками для подписки
        )
        return  # Прерываем выполнение, если пользователь не подписан

    try:
        if message.text and len(message.text.split()) > 1:
            try:
                referrer_id = int(message.text.split()[1])  # Получаем ID реферера 1-го уровня
                if referrer_id == user_id:
                    await message.answer('Вы не можете быть рефералом самого себя.')
                    return

                # Получаем данные реферера 1-го уровня
                referrer = get_user_db(referrer_id)
                if referrer:
                    # Если у реферера 1-го уровня есть свой реферер, это будет реферер 2-го уровня
                    referrer_id_2 = referrer[6]  # referrer_id реферера 1-го уровня
                else:
                    # Если реферер 1-го уровня не найден, обнуляем оба реферера
                    referrer_id = None
                    referrer_id_2 = None

            except ValueError:
                referrer_id = None
                referrer_id_2 = None

        # Проверяем, зарегистрирован ли пользователь
        user = get_user_db(user_id)
        if user:
            await message.answer(text=LEXICON_RU['restart'], reply_markup=reply_kb)
            return

        # Сохраняем данные о реферерах в состояние
        await state.set_state(Registration.waiting_for_registration)
        await state.update_data(referrer_id=referrer_id, referrer_id_2=referrer_id_2)

        # Отправляем сообщение с приветствием и кнопкой регистрации
        await bot.send_photo(chat_id=message.chat.id,
                             photo="AgACAgIAAxkBAAIZkWentEOKI7JGhmenWJb5HJtSz9GHAAKl7zEbFkNASVh_O4i8qULuAQADAgADeQADNgQ",
                             caption=LEXICON_RU['/start'],
                             parse_mode="HTML",
                             reply_markup=register_btn)

    except Exception as e:
        logger.exception(f"Error in process_start_command for user {user_id}: {e}")
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_subscription(bot, user_id):
        await callback.message.answer("Спасибо за подписку! Теперь вы можете продолжить использование бота.")
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo="AgACAgIAAxkBAAIZkWentEOKI7JGhmenWJb5HJtSz9GHAAKl7zEbFkNASVh_O4i8qULuAQADAgADeQADNgQ",
                             caption=LEXICON_RU['/start'],
                             parse_mode="HTML",
                             reply_markup=register_btn)
    else:
        await callback.message.answer("Вы всё ещё не подписаны на все каналы. Пожалуйста, подпишитесь и попробуйте снова.", reply_markup=channels_check)


@router.message(Command("start"), F.chat.type.in_(["group", "supergroup", "channel"]))
async def process_start_command(message: Message):
    await message.answer(text=LEXICON_RU['no_command'])


@router.callback_query(F.data == 'register_button_pressed')
async def register_button_pressed(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(text=LEXICON_RU['register'], reply_markup=ok_rules_btn)

@router.callback_query(F.data == 'out_money_button_pressed')
async def ok_rules_button_pressed(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer('💸')
    user_id = callback.from_user.id
    user = get_user_db(user_id)
    if user is None:
        await callback.message.answer("Пожалуйста, сначала запустите бота командой /start")
        return

    if user:
        earned = int(user[4])
        await callback.message.answer(f'<b>‼Минимальная сумма вывода 150₽</b>\n\nДоступный баланс: <b>{earned}₽</b>',
                                      reply_markup=create_out)



async def process_payout_command(message: types.Message, state: FSMContext, bot: Bot):
   try:
        await message.answer('Введите ID пользователя которому надо сделать выплату:')
        await state.set_state(Payout.waiting_for_user_id)
   except Exception as e:
        logger.exception(f"Error in process_payout_command: {e}")
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")

@router.message(Payout.waiting_for_user_id, F.text)
async def process_payout_user_id(message: Message, state: FSMContext, bot: Bot):
    try:
      await state.update_data(user_id=message.text)
      await message.answer("Введите сумму выплаты:")
      await state.set_state(Payout.waiting_for_payout_amount)
    except Exception as e:
       logger.exception(f"Error in process_payout_user_id: {e}")
       await message.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")



@router.message(Payout.waiting_for_payout_amount, F.text)
async def process_payout_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        data = await state.get_data()
        user_id = int(data['user_id'])
        payout_amount = float(message.text)
        user = get_user_db(user_id)
        if user is None:
            await message.answer("Такого пользователя не существует")
            await state.clear()
            return

        # Начисляем выплату плательщику
        update_user_balance(user_id, payout_amount)
        await message.answer(f"Пользователю с ID {user_id} начислена выплата в размере {payout_amount}")

        # Начисляем реферальные вознаграждения
        calculate_referral_rewards(user_id, payout_amount)  # Вызываем функцию для начисления реферальных вознаграждений

        await state.clear()
    except ValueError:
        await message.answer("Неправильный формат суммы")
    except Exception as e:
        logger.exception(f"Error in process_payout_amount: {e}")
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")



@router.callback_query(F.data == 'create_out_button_pressed')
async def create_out_button_pressed(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer('<b>Введите сумму вывода:</b>', reply_markup=out1_kb)
    await state.set_state(CreateOutState.waiting_for_out_amount)

@router.message(CreateOutState.waiting_for_out_amount)
async def process_out_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        user_id = message.from_user.id
        user = get_user_db(user_id)
        if user is None:
            await message.answer("<b>Пожалуйста, сначала запустите бота командой /start</b>")
            await state.clear()
            return

        earned = int(user[4])
        if amount < MIN_WITHDRAWAL:
            await message.answer(f"<b>Минимальная сумма для вывода {MIN_WITHDRAWAL}₽</b>", reply_markup=reply_kb)
            await state.clear()
            return
        if amount > earned:
            await message.answer("<b>Сумма вывода превышает ваш баланс</b>", reply_markup=reply_kb)
            await state.clear()
            return

        #  Конвертируем рубли в USDT (необходимо реализовать логику конвертации)
        amount_usdt = amount  # Здесь будет логика конвертации
        description = f"Выплата для пользователя {user_id} на сумму {amount_usdt} USDT."

        invoice_link = create_crypto_bot_invoice(amount_usdt, description) # Заменил на create_crypto_bot_invoice
        if invoice_link:
            # Отправляем ссылку на чек пользователю
            await message.answer(f"<b>Ваш чек для вывода {amount}₽ в USDT:</b>\n{invoice_link}")
            calculate_referral_rewards(user_id, amount)
            update_user_balance(user_id, -amount) # Уменьшаем баланс пользователя в БД
        else:
          await message.answer("<b>Ошибка создания чека. Попробуйте позже.</b>", reply_markup=reply_kb)
    except ValueError:
       await message.answer("<b>Неверный формат суммы. Пожалуйста, введите число.</b>", reply_markup=reply_kb)
    except Exception as e:
       logger.exception(f"Error in process_out_amount: {e}")
       await message.answer(f"<b>Ошибка при обработке запроса на вывод: {e}</b>", reply_markup=reply_kb)
    finally:
      await state.clear()




@router.callback_query(F.data == "confirm_registration")
async def confirm_registration(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    referrer_id_2 = data.get("referrer_id_2")
    await callback.message.delete()
    await create_user_db(user_id, referrer_id, referrer_id_2)  # Сохраняем пользователя
    await callback.message.answer(text=LEXICON_RU['registration_successful'], reply_markup=reply_kb)
    await state.clear()


import db_manager
@router.callback_query(lambda c: c.data and c.data.endswith('_button_pressed'))
async def offer_button_pressed(callback: types.CallbackQuery):
    await callback.message.delete()
    offer_type = callback.data.replace('_button_pressed', '')
    user_id = callback.from_user.id
    try:
        offer = db_manager.get_offer_by_name(offer_type)
        if not offer:
            await callback.message.answer("<b>Данное направление не доступно</b>")
            return

        price_person = db_manager.get_offer_links(offer[0])  # Используем  db_manager.get_offer_links
        if price_person is None:
            await callback.message.answer("Цена не определена для этого оффера")
            return
        if not isinstance(price_person, (int, float)):
            logger.error(f"get_offer_links returned unexpected type: {type(price_person)}₽")
            await callback.message.answer("Ошибка получения цены.")
            return

        price_person_100 = price_person * 100

        # ... Получение ссылки ...
        user_link_data = db_manager.get_link_by_user_and_type(user_id, offer_type, offer[0]) # Используем  db_manager
        if user_link_data:
            user_link, offer_id = user_link_data
        else:
            link_data = db_manager.get_unused_link(offer_type, offer[0]) # Используем  db_manager
            if link_data:
                link_id, user_link = link_data
                db_manager.mark_link_as_used(link_id, user_id) # Используем  db_manager
            else:
                await callback.message.answer('Нет доступных ссылок')
                return

        manual_link = db_manager.get_offer_manual_link(offer[0])

        sticker_napravlenie = "CAACAgIAAxkBAAEMXQFnp7ipy_eyrMMiaEE0PFt6gDvs8wAC_lEAAreYQUtYi-eRmtVLBDYE"
        await bot.send_sticker(callback.message.chat.id, sticker=sticker_napravlenie)
        await bot.send_photo(chat_id=callback.message.chat.id,
                             photo="AgACAgIAAxkBAAIZkWentEOKI7JGhmenWJb5HJtSz9GHAAKl7zEbFkNASVh_O4i8qULuAQADAgADeQADNgQ",
                             caption=f'<b>📘<a href="{manual_link}">Мануал по данному направлению</a></b>\n\n<b>Выплата за 1 человека: {price_person}₽\n'
                                     f'<tg-spoiler>{price_person_100}₽ За 100 человек</tg-spoiler></b>\n\n<b>Ваша уникальная ссылка для залива трафика:</b> {user_link}',
                             parse_mode="HTML")

    except Exception as e:
        logger.exception(f"Error in offer_button_pressed: {e}")
        await callback.message.answer("Произошла ошибка. Попробуйте позже.")


@router.callback_query(lambda c: c.data == "admin_broadcast_pressed")
async def admin_broadcast_callback(query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Текст", callback_data="broadcast_text")],
        [InlineKeyboardButton(text="Фото", callback_data="broadcast_photo")],
        [InlineKeyboardButton(text="Фото с текстом", callback_data="broadcast_photo_with_text")],
    ])
    await query.message.answer("<b>Выберите тип рассылки:</b>", reply_markup=keyboard)
    await state.set_state(BroadcastState.waiting_for_broadcast_type)

@router.callback_query(BroadcastState.waiting_for_broadcast_type, lambda c: c.data.startswith("broadcast_"))
async def process_broadcast_type(query: types.CallbackQuery, state: FSMContext):
    if query.data == "broadcast_text":
        await query.message.answer("<b>Введите текст для рассылки:</b>")
        await state.set_state(BroadcastState.waiting_for_broadcast_text)
    elif query.data == "broadcast_photo":
        await query.message.answer("<b>Отправьте фото для рассылки:</b>")
        await state.set_state(BroadcastState.waiting_for_broadcast_photo)
    elif query.data == "broadcast_photo_with_text":
        await query.message.answer("<b>Отправьте фото для рассылки:</b>")
        await state.set_state(BroadcastState.waiting_for_broadcast_photo_with_text)

@router.message(BroadcastState.waiting_for_broadcast_text)
async def process_broadcast_text(message: types.Message, state: FSMContext):
    text = message.text
    await broadcast_message(text=text)
    await message.answer("<b>Рассылка завершена</b>")
    await state.clear()

@router.message(BroadcastState.waiting_for_broadcast_photo, F.photo)
async def process_broadcast_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1].file_id  # Получаем file_id наибольшего качества фото
    await broadcast_message(photo=photo)
    await message.answer("<b>Рассылка завершена</b>")
    await state.clear()

@router.message(BroadcastState.waiting_for_broadcast_photo_with_text, F.photo)
async def process_broadcast_photo_with_text(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("<b>Теперь отправьте текст для рассылки:</b>")
    await state.set_state(BroadcastState.waiting_for_broadcast_photo_with_text)

@router.message(BroadcastState.waiting_for_broadcast_photo_with_text)
async def process_broadcast_photo_with_text_text(message: types.Message, state: FSMContext):
   text = message.text
   data = await state.get_data()
   photo = data.get('photo')
   await broadcast_message(text=text, photo=photo)
   await message.answer("<b>Рассылка завершена</b>")
   await state.clear()

async def broadcast_message(text: str = None, photo: str = None):
    """Функция рассылки сообщения всем пользователям"""
    users = db_manager.get_all_users_ids()  # Получаем ID всех пользователей
    if not users:
        logging.warning("No users found to send broadcast message.")
        return

    logging.info(f"Starting broadcast message: text={text}, photo={photo}")
    for user_id in users:
        await send_message_to_user(user_id, text=text, photo=photo)
        await asyncio.sleep(0.1)  # Ограничение скорости
    logging.info("Broadcast finished")


async def send_message_to_user(user_id: int, text: str = None, photo: str = None):
    """Функция отправки сообщения одному пользователю с обработкой ошибок"""
    try:
        if text and not photo:
            # Отправка текстового сообщения с HTML-разметкой
            await bot.send_message(user_id, text=text, parse_mode="HTML")
            logging.info(f"Message sent to {user_id}")
        elif photo and not text:
            # Отправка фото без текста
            await bot.send_photo(user_id, photo=photo, parse_mode="HTML")
            logging.info(f"Photo sent to {user_id}")
        elif photo and text:
            # Отправка фото с текстом (caption) и HTML-разметкой
            await bot.send_photo(user_id, photo=photo, caption=text, parse_mode="HTML")
            logging.info(f"Photo with caption sent to {user_id}")
    except TelegramForbiddenError:
        logging.warning(f"User {user_id} blocked the bot")
    except Exception as e:
        logging.error(f"Error sending message to {user_id}: {e}")



@router.callback_query(F.data == 'admin_admins_pressed')
async def admin_admins_callback(callback: types.CallbackQuery):
    admins_str = "\n".join(map(str, ADMINS))
    await callback.message.answer('👑')
    await callback.message.answer(f'<b>Админы:</b>\n{admins_str}', reply_markup=admins_btn)

@router.callback_query(F.data == 'delete_links_pressed')
async def delete_links_callback(query: types.CallbackQuery):
    # Получаем список всех офферов
    offers = get_all_offers()
    if not offers:
        await query.message.answer("<b>Нет доступных направлений</b>")
        return

    # Создаем кнопки для каждого оффера
    buttons = []
    for offer in offers:
        buttons.append([InlineKeyboardButton(text=offer[1], callback_data=f'delete_links_offer_{offer[0]}')])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await query.message.answer("<b>Выберите оффер для удаления ссылок:</b>", reply_markup=markup)
    await query.answer()

@router.message(Command(commands=["admin_panel"]))
async def admin_panel_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if is_admin(user_id):
        await state.clear()
        await message.answer("Админ-панель:", reply_markup=admin_panel_keyboard)
    else:
        await message.answer("У вас нет доступа к этой команде.")

@router.callback_query(F.data == 'add_admin_pressed')
async def add_admin_callback(query: types.CallbackQuery, state: FSMContext):
     await query.message.answer("<b>Введите ID нового администратора:</b>")
     await state.set_state(AdminState.waiting_for_new_admin_id)


@router.message(AdminState.waiting_for_new_admin_id)
async def process_new_admin_id(message: types.Message, state: FSMContext):
    try:
        new_admin_id = int(message.text)
        ADMINS.add(new_admin_id)
        update_admins_env()
        await message.answer(f"<b>Администратор с ID {new_admin_id} успешно добавлен.</b>")
    except ValueError:
        await message.answer("<b>Неверный формат ID. Пожалуйста, введите числовой ID.</b>")
    await state.clear()

@router.callback_query(F.data == 'del_admin_pressed')
async def add_admin_callback(query: types.CallbackQuery, state: FSMContext):
     await query.message.answer("<b>🆔Введите ID дмина которого надо удалить:</b>")
     await state.set_state(AdminState.waiting_for_del_admin_id)

@router.message(AdminState.waiting_for_del_admin_id)
async def process_del_admin_id(message: types.Message, state: FSMContext):
    try:
        del_admin_id = int(message.text)
        ADMINS.remove(del_admin_id)
        update_admins_env()
        await message.answer(f'<b>Администратор с ID {del_admin_id} успешно удален.</b>')
    except ValueError:
        await message.answer("<b>Неверный формат ID. Пожалуйста, введите числовой ID.</b>")
    except KeyError:
        await message.answer("<b>Нет такого ID в списке администраторов</b>")
    await state.clear()

@router.callback_query(F.data == 'add_offer_pressed')
async def add_offer_callback(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer(LEXICON_RU['ask_offer_name'])
    await state.set_state(AddOfferState.waiting_for_offer_name)


@router.message(AddOfferState.waiting_for_offer_name)
async def process_offer_name(message: types.Message, state: FSMContext):
    offer_name = message.text
    if get_offer_by_name(offer_name):
        await message.answer(LEXICON_RU['offer_name_exists'].format(offer_name=offer_name))
        return
    await state.update_data(offer_name=message.text)
    await message.answer(LEXICON_RU['ask_manual_link'])
    await state.set_state(AddOfferState.waiting_for_manual_link)


@router.message(AddOfferState.waiting_for_manual_link)
async def process_manual_link(message: types.Message, state: FSMContext):
    await state.update_data(manual_link=message.text)
    await message.answer(LEXICON_RU['ask_price_per_person'])  # Запрашиваем цену за человека
    await state.set_state(AddOfferState.waiting_for_price)



@router.message(AddOfferState.waiting_for_links)
async def process_offer_links(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_name = data['offer_name']
    links = message.text.splitlines()
    manual_link = data['manual_link']
    price_per_person = data['price_per_person']

    offer_id = add_offer(offer_name, manual_link, price_per_person)
    if offer_id:
        add_links(links, offer_name, offer_id)
        await message.answer(LEXICON_RU['offer_created'].format(offer_name=offer_name))
        await state.clear()
    else:
        await message.answer(LEXICON_RU['offer_creation_error'].format(offer_name=offer_name))
        await state.clear()


@router.message(Command(commands=["add_links"]))
async def add_links_command(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "Пожалуйста, введите тип ссылок и ссылки после команды /add_links, разделяя их пробелами. Например /add_links tg offer_name link1 link2")
        return
    link_type = parts[1]
    offer_name = parts[2]
    links = parts[3:]

    offer = get_offer_by_name(offer_name)
    if not offer:
        await message.answer(f"<b>Направление {offer_name} не найдено, сначала добавьте оффер</b>")
        return

    if links:
        add_links(links, link_type, offer[0])
        await message.answer(f"Добавлено {len(links)} новых ссылок типа {link_type} для оффера {offer_name}.")
    else:
        await message.answer("Пожалуйста, введите ссылки после команды /add_links, разделяя их пробелами")


# Обработчики callback
@router.callback_query(lambda c: c.data == "admin_offer_pressed")
async def admin_offer_callback(query: types.CallbackQuery):
    offers = get_all_offers()
    if not offers:
        await query.message.answer("<b>Нет доступных направлений</b>")
        return
    buttons = []
    for offer in offers:
        buttons.append([InlineKeyboardButton(text=offer[1], callback_data=f'offer_selected_{offer[0]}')])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await query.message.answer("<b>Доступные направления:</b>", reply_markup=markup)
    await query.answer()

@router.callback_query(lambda c: c.data.startswith('offer_selected_'))
async def offer_selected_callback(query: types.CallbackQuery):
    offer_id = int(query.data.split('_')[2])
    buttons = [
        [InlineKeyboardButton(text='Удалить оффер', callback_data=f'delete_offer_{offer_id}')],
        [InlineKeyboardButton(text='Заморозить/Разморозить', callback_data=f'toggle_offer_{offer_id}')],
        [InlineKeyboardButton(text='Действующие ссылки', callback_data=f'links_offer_{offer_id}')]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await query.message.answer("<b>Действия:</b>", reply_markup=markup)
    await query.answer()

@router.callback_query(F.data == 'change_usdt_rate_pressed')
async def change_usdt_rate_callback(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("<b>Введите новый курс USDT/RUB:</b>")
    await state.set_state(AdminState.waiting_for_new_usdt_rate)

@router.message(AdminState.waiting_for_new_usdt_rate)
async def process_new_usdt_rate(message: types.Message, state: FSMContext):
    try:
        new_rate = float(message.text)
        if new_rate <= 0:
           await message.answer("<b>Курс должен быть больше нуля.</b>")
           await state.clear()
           return
        global USDT_RUB_RATE  # Объявляем переменную как глобальную
        USDT_RUB_RATE = new_rate
        set_key(".env", "USDT_RUB_RATE", str(new_rate)) # Обновляем значение в .env файле
        await message.answer(f"<b>Курс USDT/RUB успешно изменен на {new_rate}</b>")
    except ValueError:
        await message.answer("<b>Неверный формат курса. Пожалуйста, введите число.</b>")
    except Exception as e:
        logger.exception(f"Error in process_new_usdt_rate: {e}")
        await message.answer(f"<b>Ошибка при обновлении курса: {e}</b>")
    finally:
      await state.clear()



@router.callback_query(lambda c: c.data.startswith('delete_offer_'))
async def delete_offer_callback(query: types.CallbackQuery):
    offer_id = int(query.data.split('_')[2])  # ИЗМЕНЕНО
    delete_offer(offer_id)
    await query.message.answer(f"<b>Направление {offer_id} и все его ссылки удалены</b>")
    await query.answer()


@router.callback_query(lambda c: c.data.startswith('toggle_offer_'))
async def toggle_offer_callback(query: types.CallbackQuery):
    offer_id = int(query.data.split('_')[2])  # ИЗМЕНЕНО
    new_status = toggle_offer_status(offer_id)
    if new_status == 1:
        await query.message.answer(f"<b>Направление {offer_id} разморожено</b>")
    elif new_status == 0:
        await query.message.answer(f"<b>Направление {offer_id} заморожено</b>")
    await query.answer()


@router.callback_query(lambda c: c.data.startswith('links_offer_'))
async def links_offer_callback(query: types.CallbackQuery):
    offer_id = int(query.data.split('_')[2])
    links = get_links_by_offer_id(offer_id) #Исправлено
    if links:
        text = f"<b>Ссылки для оффера {offer_id}:</b>\n"
        for link, link_id, user_id in links:
            if user_id:
                text += f'<b>Ссылка</b>: {link}\n<a href="tg://user?id={user_id}">Ссылка на профиль</a>\n\n'
            else:
                text += f'<b>Ссылка</b>: {link} \n<b>Статус</b>: Не выдана\n\n'
        await query.message.answer(text, reply_markup=add_money_btn)
    else:
        await query.message.answer(f"<b>В данный момент нет доступных ссылок для направления {offer_id}</b>")
    await query.answer()

@router.callback_query(lambda c: c.data == "add_money_pressed")
async def add_money_callback(query: types.CallbackQuery, state: FSMContext):
    await query.message.answer("<b>Введите уникальную ссылку пользователя:</b>")
    await state.set_state(AddMoneyState.waiting_for_user_link)

@router.message(AddMoneyState.waiting_for_user_link)
async def process_user_link(message: types.Message, state: FSMContext):
    user_link = message.text
    try:
        # Ищем пользователя по ссылке
        cursor = db_manager.conn.cursor()
        cursor.execute("SELECT user_id FROM links WHERE link = ?", (user_link,))
        user_data = cursor.fetchone()
        if not user_data:
            await message.answer("<b>Пользователь с такой ссылкой не найден.</b>")
            await state.clear()
            return
        user_id = user_data[0]
        await state.update_data(user_id=user_id, user_link=user_link)  # Сохраняем user_id и user_link
        await message.answer("<b>Введите сумму для начисления:</b>")
        await state.set_state(AddMoneyState.waiting_for_amount)
    except Exception as e:
        logger.error(f"Error in process_user_link: {e}")
        await message.answer(f"<b>Ошибка при поиске пользователя по ссылке: {e}</b>")
        await state.clear()


@router.message(AddMoneyState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        data = await state.get_data()
        user_id = data['user_id']

        # Получаем уникальную ссылку из состояния (предполагается, что она сохранена ранее)
        user_link = data.get('user_link')

        # Получаем offer_id по ссылке
        cursor.execute("SELECT offer_id FROM links WHERE link = ?", (user_link,))
        offer_data = cursor.fetchone()
        if not offer_data:
            await message.answer("<b>Не удалось определить оффер по данной ссылке.</b>")
            await state.clear()
            return
        offer_id = offer_data[0]

        # Получаем название оффера
        cursor.execute("SELECT name FROM offers WHERE id = ?", (offer_id,))
        offer_name_data = cursor.fetchone()
        offer_name = offer_name_data[0] if offer_name_data else "Неизвестный оффер"

        # Обновляем баланс и общую сумму заработанных средств
        update_user_balance(user_id, amount, update_total_earned=True)

        # Начисляем реферальные вознаграждения
        calculate_referral_rewards(user_id, amount)

        # Записываем выплату в базу данных
        add_payout(user_id, amount)  # Добавляем запись о выплате

        # Отправляем сообщение пользователю с названием оффера
        sticker_profit = 'CAACAgIAAxkBAAEMoSdnsj5lKqu2hSV-KommMRkAAVijGIAAAjVRAALsBEhLL_BaF7G5Chk2BA'
        await bot.send_sticker(user_id, sticker=sticker_profit)
        await bot.send_message(
            user_id,
            f"<b>🚀Успешный профит!</b>\n├ Направление: <b>{offer_name}</b>\n└ Сумма профита: <b>{amount}₽</b>",
            parse_mode="HTML"
        )

        # Отправляем сообщение в группы
        await send_profit_notification(user_id, amount, offer_name)

        await message.answer(f"<b>Успешно начислено {amount}₽ пользователю с ID {user_id} по офферу '{offer_name}'.</b>")
    except ValueError:
        await message.answer("<b>Неверный формат суммы. Пожалуйста, введите число.</b>")
    except Exception as e:
        logger.error(f"Error in process_amount: {e}")
        await message.answer(f"<b>Ошибка при обработке запроса на выплату: {e}</b>")
    finally:
        await state.clear()

@router.message(Command("daily_top"))
async def daily_top_command(message: types.Message):
    """Обработчик команды /daily_top."""
    try:
        # Получаем топ-10 пользователей за последние 24 часа
        daily_top = get_daily_top()

        if not daily_top:
            await message.answer("<b>За последние 24 часа выплат не было.</b>", parse_mode="HTML")
            return

        # Формируем сообщение с топом
        top_message = "<b>💎 Топ-10 за последние 24 часа:</b>\n\n"
        for i, (user_id, total_amount) in enumerate(daily_top, start=1):
            # Получаем статус пользователя
            user = get_user_db(user_id)
            if user:
                status = user[2]  # Статус пользователя
            else:
                status = "Неизвестно"

            # Добавляем эмодзи для первых трёх мест
            if i == 1:
                place = "👑"
            elif i == 2:
                place = "🥈"
            elif i == 3:
                place = "🥉"
            else:
                place = f"{i}."

            top_message += f"{place} <a href='tg://user?id={user_id}'>{status}</a>: <b>{total_amount}₽</b>\n"

        await message.answer(top_message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in daily_top_command: {e}")
        await message.answer("<b>Произошла ошибка при получении данных.</b>", parse_mode="HTML")

@router.message(Command("top"))
async def all_time_top_command(message: types.Message):
    """Обработчик команды /top."""
    try:
        # Получаем топ-10 пользователей за всё время
        all_time_top = get_all_time_top()

        if not all_time_top:
            await message.answer("<b>Нет данных о выплатах.</b>", parse_mode="HTML")
            return

        # Формируем сообщение с топом
        top_message = "<b>🏆 Топ-10 за всё время:</b>\n\n"
        for i, (user_id, total_amount) in enumerate(all_time_top, start=1):
            # Получаем статус пользователя
            user = get_user_db(user_id)
            if user:
                status = user[2]  # Статус пользователя
            else:
                status = "Неизвестно"

            # Добавляем эмодзи для первых трёх мест
            if i == 1:
                place = "👑"
            elif i == 2:
                place = "🥈"
            elif i == 3:
                place = "🥉"
            else:
                place = f"{i}."

            top_message += f"{place} <a href='tg://user?id={user_id}'>{status}</a>: <b>{total_amount}₽</b>\n"

        await message.answer(top_message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in all_time_top_command: {e}")
        await message.answer("<b>Произошла ошибка при получении данных.</b>", parse_mode="HTML")

@router.callback_query(lambda c: c.data == "admin_other_pressed")
async def admin_other_callback(query: types.CallbackQuery):
    await query.message.answer("Здесь будут другие опции")
    await query.answer()

@router.message(Command(commands=["me"]), F.chat.type == "private")
async def process_stats_command(message: types.Message):
    await message.answer('❌<b>Данная команда доступна только для чатов</b> <tg-spoiler>Наш чат @FluxTrafficChat</tg-spoiler>')

@router.message(Command(commands=["me"]))
async def process_stats_command(message: types.Message):
    user_id = message.from_user.id
    user = get_user_db(user_id)
    if user:
        user_id = user[0]
        date_entrance = user[1]
        level = user[2]
        earned = int(user[4])
        total_earned = int(user[8])
        earned_referrals = int(user[5])  # Заработанные реферальные вознаграждения
        referrals_1_count, referrals_2_count = get_referrals(user_id)
        referrals = referrals_1_count + referrals_2_count

        users_by_balance = get_users_sorted_by('balance')
        users_by_referrals = get_users_sorted_by('referrals')
        users_by_earned_referrals = get_users_sorted_by('earned_referrals')

        place_balance = get_user_rank(user_id, users_by_balance)
        place_referals = get_user_rank(user_id, users_by_referrals)
        place_earned_referrals = get_user_rank(user_id, users_by_earned_referrals)

        stats_text = (
                f'<b>🪪Ваш профиль:</b>\n\nРегистрация: <b>{date_entrance}</b>'
                f'\nСтатус: <b>{level}</b>\n'
                f'\nЗаработано всего: <b>{total_earned}₽</b>\n\n'
                f'👨‍👩‍👦‍👦Приглашено рефералов: <b>{referrals}</b>\nЗаработанно с рефералов: <b>{earned_referrals}₽</b>'
                f'\n\n<b>📊Место в топе:</b>\n├ по заработку: {place_balance}'
                f'\n└ по заработку с рефералов: {place_earned_referrals}')
        await message.reply(stats_text)
    else:
        await message.reply("❌Для того чтобы использовать эту команду, зарегестрируйстесь в боте @FluxTrafficBot")

@router.message(AddOfferState.waiting_for_price)
async def process_price_per_person(message: types.Message, state: FSMContext):
    try:
        price_per_person = float(message.text)
        await state.update_data(price_per_person=price_per_person)
    except ValueError:
        await message.answer(LEXICON_RU['invalid_price'])
        return

    await message.answer("<b>Введите уникальные ссылки для данного направления (каждую с новой строки):</b>")
    await state.set_state(AddOfferState.waiting_for_links)

@router.message(F.photo)
async def handle_photo(message: Message):
    # Получаем file_id самой большой версии фотографии
    file_id = message.photo[-1].file_id

    # Отправляем file_id обратно пользователю
    await message.reply(f"File ID этой фотографии: `{file_id}`", parse_mode="MarkdownV2")
    #parse_mode="MarkdownV2" нужен чтобы правильно отображать символы, которые могут быть в file_id

@router.message(F.chat.type == "private")
async def send_echo(message: Message):
    await message.answer(
        text='Я даже представить себе не могу, '
             'что ты имеешь в виду\n\nЧтобы обновить бота отправь команду /start'
    )