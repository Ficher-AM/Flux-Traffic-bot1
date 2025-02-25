# db_manager.py
import sqlite3
import datetime
import logging

# Настраиваем логирование
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Создаем глобальное подключение к БД
conn = sqlite3.connect('bot_users.db')
cursor = conn.cursor()


cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        date_entrance TEXT,
        level TEXT,
        referrals INTEGER,
        balance REAL,
        earned_referrals INTEGER,
        referrer_id INTEGER,
        referrer_id_2 INTEGER,
        total_earned REAL DEFAULT 0  -- Новое поле для общей суммы заработанных средств
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,   
        name TEXT UNIQUE,
        is_active INTEGER DEFAULT 1,
        manual_link TEXT,
        price_per_person INTEGER
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT UNIQUE,
        is_used INTEGER DEFAULT 0,
        user_id INTEGER,
        type TEXT,
        offer_id INTEGER,
        FOREIGN KEY (offer_id) REFERENCES offers(id)
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS payouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        payout_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
""")
conn.commit()


def get_today_payouts():
    """Возвращает сумму выплат за последние 24 часа."""
    try:
        # Получаем текущее время и время 24 часа назад
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(hours=24)

        # Выполняем запрос к базе данных
        cursor.execute("SELECT SUM(amount) FROM payouts WHERE payout_date >= ?", (yesterday.isoformat(),))
        result = cursor.fetchone()
        return result[0] if result[0] else 0  # Возвращаем сумму выплат или 0, если выплат нет
    except sqlite3.Error as e:
        logger.error(f"Error getting today's payouts: {e}")
        return 0

def get_total_payouts():
    """Возвращает общую сумму всех выплат."""
    try:
        cursor.execute("SELECT SUM(amount) FROM payouts")
        result = cursor.fetchone()
        return result[0] if result[0] else 0  # Возвращаем сумму выплат или 0, если выплат нет
    except sqlite3.Error as e:
        logger.error(f"Error getting total payouts: {e}")
        return 0

def add_payout(user_id: int, amount: float):
    """Добавляет запись о выплате в базу данных."""
    try:
        cursor.execute("INSERT INTO payouts (user_id, amount, payout_date) VALUES (?, ?, ?)",
                       (user_id, amount, datetime.datetime.now().isoformat()))
        conn.commit()
        logger.info(f"Payout of {amount}₽ added for user {user_id}.")
    except sqlite3.Error as e:
        logger.error(f"Error adding payout: {e}")

def get_user_rank(user_id: int, sorted_users):
    """Возвращает место пользователя в топе."""
    for rank, user in enumerate(sorted_users, start=1):
        if user[0] == user_id:
            return rank
    return -1  # Если пользователя не нашли (не должно случиться)

async def create_user_db(user_id, referrer_id, referrer_id_2):
    """Создает нового пользователя в базе данных и обновляет счетчики рефералов."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (user_id, date_entrance, level, referrals, balance, earned_referrals, referrer_id, referrer_id_2) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, datetime.date.today().isoformat(), 'Новичек', 0, 0, 0, referrer_id, referrer_id_2))
        conn.commit()
        logger.info(f"User {user_id} created with referrer_id: {referrer_id}, referrer_id_2: {referrer_id_2}")

        # Обновляем счетчик рефералов для реферера 1-го уровня
        if referrer_id:
            cursor.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (referrer_id,))
            conn.commit()
            logger.info(f"Referral counter updated for user {referrer_id}")

        # Обновляем счетчик рефералов для реферера 2-го уровня
        if referrer_id_2:
            cursor.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (referrer_id_2,))
            conn.commit()
            logger.info(f"Referral counter updated for user {referrer_id_2}")

    except sqlite3.Error as e:
        logger.error(f"Error creating user {user_id}: {e}")

def get_daily_top():
    """Возвращает топ-10 пользователей с наибольшими выплатами за последние 24 часа."""
    try:
        # Получаем текущее время и время 24 часа назад
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(hours=24)

        # Выполняем запрос к базе данных
        cursor.execute("""
            SELECT user_id, SUM(amount) as total_amount
            FROM payouts
            WHERE payout_date >= ?
            GROUP BY user_id
            ORDER BY total_amount DESC
            LIMIT 10
        """, (yesterday.isoformat(),))
        return cursor.fetchall()  # Возвращаем список кортежей (user_id, total_amount)
    except sqlite3.Error as e:
        logger.error(f"Error getting daily top: {e}")
        return []

def get_all_time_top():
    """Возвращает топ-10 пользователей с наибольшими выплатами за всё время."""
    try:
        # Выполняем запрос к базе данных
        cursor.execute("""
            SELECT user_id, SUM(amount) as total_amount
            FROM payouts
            GROUP BY user_id
            ORDER BY total_amount DESC
            LIMIT 10
        """)
        return cursor.fetchall()  # Возвращаем список кортежей (user_id, total_amount)
    except sqlite3.Error as e:
        logger.error(f"Error getting all-time top: {e}")
        return []

def get_user_status(total_earned: float) -> str:
    """Возвращает статус пользователя на основе общей суммы заработанных средств."""
    if total_earned < 100:
        return "Новичок"
    elif 100 <= total_earned < 200:
        return "Стражер"
    elif 200 <= total_earned < 400:
        return "Курсант"
    elif 400 <= total_earned < 700:
        return "Специалист"
    elif 700 <= total_earned < 900:
        return "Мастер"
    elif 900 <= total_earned < 1400:
        return "Эксперт"
    elif 1400 <= total_earned < 1700:
        return "Гуру"
    elif 1700 <= total_earned < 2000:
        return "Вождь"
    elif 2000 <= total_earned < 2100:
        return "Глава"
    elif 2100 <= total_earned < 2300:
        return "Аналитик"
    elif 2300 <= total_earned < 2800:
        return "Стратег"
    elif 2800 <= total_earned < 3100:
        return "Гений"
    elif 3100 <= total_earned < 3600:
        return "Лидогенератор"
    elif 3600 <= total_earned < 4100:
        return "Директор"
    elif 4100 <= total_earned < 4500:
        return "Султан"
    elif 4500 <= total_earned < 5900:
        return "Машина"
    elif 5900 <= total_earned < 6400:
        return "Лид-магнит"
    elif 6400 <= total_earned < 7000:
        return "Вице-президент"
    elif 7000 <= total_earned < 7400:
        return "Президент"
    elif 7400 <= total_earned < 7800:
        return "Король"
    elif 7800 <= total_earned < 8300:
        return "Император"
    elif 8300 <= total_earned < 8600:
        return "Повелитель"
    elif 8600 <= total_earned < 8900:
        return "Ведущий"
    elif 8900 <= total_earned < 9300:
        return "Магистр"
    elif 9300 <= total_earned < 9600:
        return "Верховный арбитражник"
    elif 9600 <= total_earned < 10100:
        return "Легенда"
    else:
        return "Всемогущий🪬"

def calculate_referral_rewards(user_id: int, amount: float, notify=True):
    """Начисляет реферальные вознаграждения и возвращает информацию о выплатах."""
    user = get_user_db(user_id)
    if user is None:
        logger.warning(f"User {user_id} not found in database.")
        return {}

    referrer_id_1 = user[6]  # Реферер 1-го уровня
    referrer_id_2 = user[7]  # Реферер 2-го уровня

    referral_rewards = {}  # Словарь для хранения выплат реферерам

    # Начисление реферальных 1-го уровня (5%)
    if referrer_id_1:
        referral_reward_1 = amount * 0.05
        update_user_balance(referrer_id_1, referral_reward_1, update_total_earned=True)  # Обновляем total_earned
        update_user_earned_referrals(referrer_id_1, referral_reward_1)
        referral_rewards[referrer_id_1] = referral_reward_1
        if notify:
            logger.info(f"Referral reward of {referral_reward_1}₽ was paid to user {referrer_id_1}")

    # Начисление реферальных 2-го уровня (3%)
    if referrer_id_2:
        referral_reward_2 = amount * 0.03
        update_user_balance(referrer_id_2, referral_reward_2, update_total_earned=True)  # Обновляем total_earned
        update_user_earned_referrals(referrer_id_2, referral_reward_2)
        referral_rewards[referrer_id_2] = referral_reward_2
        if notify:
            logger.info(f"Referral reward of {referral_reward_2}₽ was paid to user {referrer_id_2}")

    return referral_rewards

def get_links_by_offer_id(offer_id):
    try:
        cursor.execute("SELECT link, id, user_id FROM links WHERE offer_id = ?", (offer_id,))
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting links by offer id {offer_id}: {e}")
        return None

async def create_user_db(user_id, referrer_id, referrer_id_2):
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (user_id, date_entrance, level, referrals, balance, earned_referrals, referrer_id, referrer_id_2) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, datetime.date.today().isoformat(), 'Новичек', 0, 0, 0, referrer_id, referrer_id_2))
        conn.commit()
        logger.info(f"User {user_id} created with referrer_id: {referrer_id}, referrer_id_2: {referrer_id_2}")
    except sqlite3.Error as e:
        logger.error(f"Error creating user {user_id}: {e}")

def get_user_db(user_id):
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if user:
            logger.info(f"User {user_id} found in database. Referrer 1: {user[6]}, Referrer 2: {user[7]}")
            return user
        else:
            logger.warning(f"User {user_id} not found in database.")
            return None
    except sqlite3.Error as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None

def get_all_users_ids():
    try:
        cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Error getting all users ids: {e}")
        return []



def get_referrals(user_id):
    """Возвращает количество рефералов 1-го и 2-го уровня."""
    try:
        cursor = conn.cursor()

        # Запрос для рефералов 1-го уровня
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        referrals_1 = cursor.fetchone()[0]

        # Запрос для рефералов 2-го уровня
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id_2 = ?", (user_id,))
        referrals_2 = cursor.fetchone()[0]

        logger.info(f"get_referrals for user {user_id}. Referrals 1: {referrals_1}, Referrals 2: {referrals_2}")

        # Возвращаем количество рефералов 1-го и 2-го уровня
        return referrals_1, referrals_2
    except sqlite3.Error as e:
        logger.error(f"Error getting referrals for user {user_id}: {e}")
        return 0, 0

def get_users_sorted_by(field: str):
    """Возвращает список пользователей, отсортированных по указанному полю."""
    try:
        cursor.execute(f"SELECT user_id FROM users ORDER BY {field} DESC")
        return [(row[0],) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Error getting users sorted by {field}: {e}")
        return []

def add_offer(offer_name, manual_link, price_per_person):
    try:
        cursor.execute("INSERT INTO offers (name, manual_link, price_per_person) VALUES (?, ?, ?)", (offer_name, manual_link, price_per_person))
        conn.commit()
        logger.info(f"Offer {offer_name} created.")
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error adding offer {offer_name}: {e}", exc_info=True)
        return None


def get_offer_by_name(offer_type):
    try:
       cursor.execute("SELECT id FROM offers WHERE name = ?", (offer_type,))
       row = cursor.fetchone()
       if row:
          logger.info(f"get_offer_by_name: Found offer_id = {row[0]} for offer_type = {offer_type}")
          return row[0],
       else:
          logger.info(f"get_offer_by_name: Offer not found for offer_type = {offer_type}")
          return None
    except Exception as e:
       logger.exception(f"get_offer_by_name error: {e}")
       return None

def get_all_offers():
    try:
        cursor.execute("SELECT id, name, is_active, manual_link, price_per_person FROM offers")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting all offers: {e}")
        return []


def add_links(links, link_type, offer_id):
    try:
        cursor.executemany("INSERT INTO links (link, type, offer_id) VALUES (?, ?, ?)",
                           [(link, link_type, offer_id) for link in links])
        conn.commit()
        logger.info(f"{len(links)} new links of type {link_type} added for offer {offer_id}.")
    except sqlite3.Error as e:
        logger.error(f"Error adding links: {e}")


def update_user_balance(user_id: int, amount: float, update_total_earned=False):
    """Обновляет баланс пользователя, добавляя сумму сверху. Если update_total_earned=True, обновляет и общую сумму заработанных средств."""
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        if update_total_earned and amount > 0:
            cursor.execute("UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?", (amount, user_id))

        # Получаем общую сумму заработанных средств
        cursor.execute("SELECT total_earned FROM users WHERE user_id = ?", (user_id,))
        total_earned = cursor.fetchone()[0]

        # Обновляем статус пользователя
        new_status = get_user_status(total_earned)
        cursor.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_status, user_id))

        conn.commit()
        logger.info(f"User {user_id} balance updated by {amount}. New balance: {get_user_db(user_id)[4]}")
    except sqlite3.Error as e:
        logger.error(f"Error updating user balance: {e}")

def update_user_earned_referrals(user_id: int, amount: float):
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET earned_referrals = earned_referrals + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        logger.info(f"User {user_id} earned_referrals updated by {amount}. New earned_referrals: {get_user_db(user_id)[5]}")
    except sqlite3.Error as e:
        logger.error(f"Error updating user earned_referrals: {e}")

def get_unused_link(link_type, offer_id):
    try:
        cursor.execute("SELECT id, link FROM links WHERE is_used = 0 AND type = ? AND offer_id = ? LIMIT 1",
                       (link_type, offer_id))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Error getting unused link: {e}")
        return None


def mark_link_as_used(link_id, user_id):
    try:
        cursor.execute("UPDATE links SET is_used = 1, user_id = ? WHERE id = ?", (user_id, link_id))
        conn.commit()
        logger.info(f"Link {link_id} marked as used by user {user_id}.")
    except sqlite3.Error as e:
        logger.error(f"Error marking link {link_id} as used: {e}")


def get_link_by_user_and_type(user_id, link_type, offer_id):
    try:
        cursor.execute("SELECT link, offer_id FROM links WHERE user_id = ? AND type = ? AND offer_id = ?",
                       (user_id, link_type, offer_id))
        result = cursor.fetchone()
        return result if result else None
    except sqlite3.Error as e:
        logger.error(f"Error getting link by user and type: {e}")
        return None


def get_offer_manual_link(offer_id):
    try:
        cursor.execute("SELECT manual_link FROM offers WHERE id = ?", (offer_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"Error getting offer manual link: {e}")
        return None


def delete_offer(offer_id):
    try:
        cursor.execute("DELETE FROM links WHERE offer_id = ?", (offer_id,))
        cursor.execute("DELETE FROM offers WHERE id = ?", (offer_id,))
        conn.commit()
        logger.info(f"Offer {offer_id} and its links deleted.")
    except sqlite3.Error as e:
        logger.error(f"Error deleting offer {offer_id}: {e}")


def toggle_offer_status(offer_id):
    try:
        cursor.execute("SELECT is_active FROM offers WHERE id = ?", (offer_id,))
        current_status = cursor.fetchone()[0]
        new_status = 1 - current_status  # Toggle status
        cursor.execute("UPDATE offers SET is_active = ? WHERE id = ?", (new_status, offer_id))
        conn.commit()
        logger.info(f"Offer {offer_id} status toggled to {new_status}.")
        return new_status
    except sqlite3.Error as e:
        logger.error(f"Error toggling offer status {offer_id}: {e}")
        return None


def get_offer_links(offer_id):
    try:
        cursor.execute("SELECT price_per_person FROM offers WHERE id = ?", (offer_id,))
        row = cursor.fetchone() # Получаем одну строку, а не все
        if row:
           price = row[0] # Получаем первое значение из кортежа
           return price
        return None
    except Exception as e:
        logger.error(f"get_offer_links error: {e}")
        return None