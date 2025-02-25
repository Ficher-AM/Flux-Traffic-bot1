from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from lexicon.lexicon_ru import LEXICON_RU

register_button = InlineKeyboardButton(
    text='✅Регистрация',
    callback_data='register_button_pressed'
)

register_btn = InlineKeyboardMarkup(
    inline_keyboard=[[register_button]]
)

channel_1_button = InlineKeyboardButton(
    text='➕1 КАНАЛ',
    url='https://t.me/FluxTraffic'
)

channel_2_button = InlineKeyboardButton(
    text='➕2 КАНАЛ',
    url='https://t.me/Rekvils'
)

check_sub_button = InlineKeyboardButton(
    text='✅Проверить',
    url='https://t.me/FluxTrafficBot?start=hello'
)

out_money_button = InlineKeyboardButton(
    text='🏦Вывести средства',
    callback_data='out_money_button_pressed'
)

out_money_btn = InlineKeyboardMarkup(
    inline_keyboard=[[out_money_button]]
)

tg_button = InlineKeyboardButton(
    text='✈Телеграм',
    callback_data='tg_button_pressed'
)

bloker_button = InlineKeyboardButton(
    text='💊Блокер',
    callback_data='bloker_button_pressed'
)

manuals_support_button = InlineKeyboardButton(
    text='📘Мануалы',
    callback_data='manuals_support_button_pressed'
)

chat_support_button = InlineKeyboardButton(
    text='💬Наш чат',
    url='https://t.me/FluxTrafficChat'
)

bot_support_button = InlineKeyboardButton(
    text='Тех.Поддержка',
    url='https://t.me/FeedbackTrafficBot'
)

support_btn = InlineKeyboardMarkup(
    inline_keyboard=[[manuals_support_button],
                     [chat_support_button],
                     [bot_support_button]]
)


confirm_registration = InlineKeyboardButton(
    text='✅Подтверждаю',
    callback_data='confirm_registration'
)

ok_rules_btn = InlineKeyboardMarkup(
    inline_keyboard=[[confirm_registration]]
)

create_out_button = InlineKeyboardButton(
    text='➕Создать заявку на вывод',
    callback_data='create_out_button_pressed'
)


channels_check: InlineKeyboardMarkup = InlineKeyboardMarkup(
    inline_keyboard=[[channel_1_button],
                     [channel_2_button],
                     [check_sub_button]]
)

# Создаем объект инлайн-клавиатуры
create_out = InlineKeyboardMarkup(
    inline_keyboard=[[create_out_button]]
)

profile_button = KeyboardButton(text=LEXICON_RU['profile_button'])
manuals_button = KeyboardButton(text=LEXICON_RU['manuals_button'])
referals_button = KeyboardButton(text=LEXICON_RU['referals_button'])
help_button = KeyboardButton(text=LEXICON_RU['help_button'])
traffic_button = KeyboardButton(text=LEXICON_RU['traffic_button'])

reply_menu_builder = ReplyKeyboardBuilder()

reply_menu_builder.add(profile_button, manuals_button, help_button, traffic_button, referals_button)
reply_menu_builder.adjust(3,2,3)

# Создаем клавиатуру
reply_kb: ReplyKeyboardMarkup = reply_menu_builder.as_markup(
    one_time_keyboard=True,
    resize_keyboard=True
)

admin_offer = InlineKeyboardButton(
    text='Офферы',
    callback_data='admin_offer_pressed'
)
admin_add_offer = InlineKeyboardButton(
    text='➕Добавить оффер',
    callback_data='add_offer_pressed'
)

admin_admins = InlineKeyboardButton(
    text='👑Админы',
    callback_data='admin_admins_pressed'
)

add_money = InlineKeyboardButton(
    text='💸Выплатить деньги',
    callback_data='add_money_pressed'
)

admin_add_admin = InlineKeyboardButton(
    text='➕Добавить админа',
    callback_data='add_admin_pressed'
)

del_admin = InlineKeyboardButton(
    text='❌Удалить Админа',
    callback_data='del_admin_pressed'
)

admins_btn = InlineKeyboardMarkup(
    inline_keyboard=[[admin_add_admin],
                     [del_admin]]
)

add_money_btn = InlineKeyboardMarkup(
    inline_keyboard=[[add_money]]
)

admin_change_usdt_rate = InlineKeyboardButton(
    text='Изменить курс USDT',
    callback_data='change_usdt_rate_pressed'
)

admin_broadcast = InlineKeyboardButton(
    text='📢Рассылка',
    callback_data='admin_broadcast_pressed'
)

delete_links_button = InlineKeyboardButton(
    text='🗑️ Удаление ссылок',
    callback_data='delete_links_pressed'
)

admin_cash_button = InlineKeyboardButton(
    text='💰Касса',
    callback_data='admin_cash_pressed'
)

admin_panel_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[[admin_offer],
                     [admin_add_offer],
                     [admin_broadcast],
                     [admin_admins],
                     [admin_change_usdt_rate],
                     [delete_links_button],
                     [admin_cash_button]]  # Добавляем кнопку "Касса"
)

delete_links_button = InlineKeyboardButton(
    text='⬅Назад',
    callback_data='delete_links_pressed'
)

out1_button = KeyboardButton(text=LEXICON_RU['out1_button'])

reply_out1_builder = ReplyKeyboardBuilder()
reply_out1_builder.add(out1_button)

out1_kb: ReplyKeyboardMarkup = reply_out1_builder.as_markup(
    one_time_keyboard=True,
    resize_keyboard=True
)