import telebot
from telebot import types
import sqlite3

TOKEN = '8693222384:AAF-wSqI0ZnLLclZ_zzmYgvAO_0XM0-j0hY'
bot = telebot.TeleBot(TOKEN)

# Состояния пользователей оставляем в памяти (если бот перезапустится,
# пользователю просто придется заново нажать кнопку в меню - это нормально)
user_states = {}


# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def db_query(query, args=(), fetchone=False, fetchall=False):
    """Универсальная функция для выполнения запросов к БД"""
    with sqlite3.connect('ndfl_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute(query, args)
        if fetchone:
            return cursor.fetchone()
        if fetchall:
            return cursor.fetchall()
        conn.commit()


def init_db():
    """Создаем таблицы при первом запуске"""
    db_query('''CREATE TABLE IF NOT EXISTS users
                (
                    chat_id
                    INTEGER
                    PRIMARY
                    KEY,
                    active_company
                    TEXT
                )''')
    db_query('''CREATE TABLE IF NOT EXISTS companies
    (
        id
        INTEGER
        PRIMARY
        KEY
        AUTOINCREMENT,
        chat_id
        INTEGER,
        name
        TEXT,
        income
        REAL
        DEFAULT
        0.0,
        auto_deduct
        INTEGER
        DEFAULT
        0,
        FOREIGN
        KEY
                (
        chat_id
                ) REFERENCES users
                (
                    chat_id
                )
        )''')


def init_user(chat_id):
    """Добавляем пользователя в БД, если его там нет"""
    user = db_query('SELECT chat_id FROM users WHERE chat_id = ?', (chat_id,), fetchone=True)
    if not user:
        db_query('INSERT INTO users (chat_id) VALUES (?)', (chat_id,))


# Запускаем инициализацию базы при старте скрипта
init_db()

# --- ТЕКСТЫ ИНСТРУКЦИИ ---
HELP_TEXTS = {
    'main': "📖 **Инструкция по использованию бота**\n\nВыбери нужный раздел:",
    'company': "🏢 **Работа с компаниями**\n\n🔹 **Создать:** Задает новое имя.\n🔹 **Сменить:** Переключает активную.\n🔹 **Инфо:** Показывает баланс и статус вычета.",
    'income': "💰 **Добавление доходов**\n\n🔹 **Добавить:** Плюсует сумму к активной компании.\n🔹 **Итог:** Считает налог с накопленного.",
    'deduct': "⚙️ **Автовычет 20%**\n\nЕсли включен, бот сам отнимет 20% от накопленной суммы, и посчитает налог с 80% (заменяет сбор чеков).",
    'quick': "⚡ **Разовый расчет**\n\nМоментальный подсчет налога без сохранения в базу."
}


# --- МАТЕМАТИКА ---
def calculate_ndfl(base):
    tax = 0
    if base > 0: tax += min(base, 2400000) * 0.13
    if base > 2400000: tax += min(base - 2400000, 2600000) * 0.15
    if base > 5000000: tax += min(base - 5000000, 15000000) * 0.18
    if base > 20000000: tax += min(base - 20000000, 30000000) * 0.20
    if base > 50000000: tax += (base - 50000000) * 0.22
    return tax


# --- КЛАВИАТУРЫ ---
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🏢 Мои компании", "➕ Добавить доход")
    markup.add("📊 Итог по активной", "⚡ Разовый расчет")
    markup.add("📖 Инструкция")
    return markup


def get_company_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🆕 Создать компанию", "🔄 Сменить компанию")
    markup.add("👁 Инфо о компании", "⚙️ Вкл/Выкл вычет 20%")
    markup.add("🔙 Назад в меню")
    return markup


def get_help_index_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🏢 Работа с компаниями", callback_data="help_company"),
        types.InlineKeyboardButton("💰 Доходы и расчеты", callback_data="help_income"),
        types.InlineKeyboardButton("⚙️ Про Автовычет 20%", callback_data="help_deduct"),
        types.InlineKeyboardButton("⚡ Быстрый расчет", callback_data="help_quick")
    )
    return markup


def get_help_back_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Назад к оглавлению", callback_data="help_main"))
    return markup


# --- БАЗОВЫЕ КОМАНДЫ И ИНСТРУКЦИЯ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    init_user(message.chat.id)
    bot.send_message(message.chat.id, "Привет! Данные надежно сохраняются в базе. Пользуйся меню ниже.",
                     reply_markup=get_main_keyboard())


@bot.message_handler(func=lambda message: message.text == "📖 Инструкция")
def show_help_main(message):
    bot.send_message(message.chat.id, HELP_TEXTS['main'], parse_mode="Markdown", reply_markup=get_help_index_keyboard())


@bot.callback_query_handler(func=lambda call: call.data.startswith('help_'))
def handle_help_callbacks(call):
    bot.answer_callback_query(call.id)
    section = call.data.split('_')[1]
    if section == 'main':
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text=HELP_TEXTS['main'], parse_mode="Markdown", reply_markup=get_help_index_keyboard())
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text=HELP_TEXTS[section], parse_mode="Markdown", reply_markup=get_help_back_keyboard())


# --- МЕНЮ КОМПАНИЙ ---
@bot.message_handler(func=lambda message: message.text == "🏢 Мои компании")
def company_menu(message):
    init_user(message.chat.id)
    res = db_query('SELECT active_company FROM users WHERE chat_id = ?', (message.chat.id,), fetchone=True)
    active = res[0] if res else None
    status = f"Активная компания: **{active}**" if active else "Активная компания: **Не выбрана**"
    bot.send_message(message.chat.id, f"Управление компаниями.\n{status}", parse_mode="Markdown",
                     reply_markup=get_company_keyboard())


@bot.message_handler(func=lambda message: message.text == "🔙 Назад в меню")
def back_to_main(message):
    user_states[message.chat.id] = None
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=get_main_keyboard())


@bot.message_handler(func=lambda message: message.text == "🆕 Создать компанию")
def create_company_start(message):
    user_states[message.chat.id] = "CREATE_COMPANY"
    bot.send_message(message.chat.id, "Введи название новой компании:", reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda message: message.text == "🔄 Сменить компанию")
def switch_company_start(message):
    init_user(message.chat.id)
    comps = db_query('SELECT name FROM companies WHERE chat_id = ?', (message.chat.id,), fetchall=True)
    if not comps:
        bot.send_message(message.chat.id, "У тебя еще нет компаний.", reply_markup=get_company_keyboard())
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for c in comps: markup.add(c[0])
    markup.add("🔙 Отмена")
    user_states[message.chat.id] = "SWITCH_COMPANY"
    bot.send_message(message.chat.id, "Выбери компанию из списка:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "⚙️ Вкл/Выкл вычет 20%")
def toggle_deduction(message):
    init_user(message.chat.id)
    active = db_query('SELECT active_company FROM users WHERE chat_id = ?', (message.chat.id,), fetchone=True)[0]
    if not active:
        bot.send_message(message.chat.id, "Сначала выбери компанию!")
        return

    current_status = \
    db_query('SELECT auto_deduct FROM companies WHERE chat_id = ? AND name = ?', (message.chat.id, active),
             fetchone=True)[0]
    new_status = 1 if current_status == 0 else 0
    db_query('UPDATE companies SET auto_deduct = ? WHERE chat_id = ? AND name = ?',
             (new_status, message.chat.id, active))

    state_text = "✅ ВКЛЮЧЕН (налог считается с 80% суммы)" if new_status else "❌ ВЫКЛЮЧЕН (налог со всей суммы)"
    bot.send_message(message.chat.id, f"Автовычет 20% для **{active}**:\n{state_text}", parse_mode="Markdown")


@bot.message_handler(func=lambda message: message.text == "👁 Инфо о компании")
def company_info(message):
    init_user(message.chat.id)
    active = db_query('SELECT active_company FROM users WHERE chat_id = ?', (message.chat.id,), fetchone=True)[0]
    if not active:
        bot.send_message(message.chat.id, "Сначала выбери или создай компанию!")
        return

    comp_data = db_query('SELECT income, auto_deduct FROM companies WHERE chat_id = ? AND name = ?',
                         (message.chat.id, active), fetchone=True)
    deduct_text = "Включен" if comp_data[1] else "Выключен"
    text = (
        f"🏢 **Компания:** {active}\n💰 **Накопленный доход:** {comp_data[0]:,.2f} руб.\n⚙️ **Автовычет 20%:** {deduct_text}").replace(
        ',', ' ')
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


# --- ДОХОДЫ И РАСЧЕТЫ ---
@bot.message_handler(func=lambda message: message.text == "➕ Добавить доход")
def add_profit_start(message):
    init_user(message.chat.id)
    active = db_query('SELECT active_company FROM users WHERE chat_id = ?', (message.chat.id,), fetchone=True)[0]
    if not active:
        bot.send_message(message.chat.id, "Сначала выбери активную компанию в '🏢 Мои компании'.")
        return
    user_states[message.chat.id] = "ADD_PROFIT"
    bot.send_message(message.chat.id, f"Введи сумму дохода для **{active}**:", parse_mode="Markdown",
                     reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda message: message.text == "📊 Итог по активной")
def calculate_total(message):
    init_user(message.chat.id)
    active = db_query('SELECT active_company FROM users WHERE chat_id = ?', (message.chat.id,), fetchone=True)[0]
    if not active:
        bot.send_message(message.chat.id, "Сначала выбери компанию!")
        return

    comp_data = db_query('SELECT income, auto_deduct FROM companies WHERE chat_id = ? AND name = ?',
                         (message.chat.id, active), fetchone=True)
    total_income = comp_data[0]

    if comp_data[1] == 1:
        tax_base = total_income * 0.8
        deduction_sum = total_income * 0.2
        deduct_msg = f"📉 **Применен вычет 20%:** -{deduction_sum:,.2f} руб.\n⚖️ **Налоговая база:** {tax_base:,.2f} руб.\n"
    else:
        tax_base = total_income
        deduct_msg = "⚖️ **Налоговая база:** равна общей сумме (вычет отключен).\n"

    tax = calculate_ndfl(tax_base)
    text = (f"🏢 **Отчет по: {active}**\n💰 **Общая выручка:** {total_income:,.2f} руб.\n{deduct_msg}"
            f"🔴 **НДФЛ к уплате:** {tax:,.2f} руб.\n💸 **Чистыми на руках:** {(total_income - tax):,.2f} руб.")
    bot.send_message(message.chat.id, text.replace(',', ' '), parse_mode="Markdown", reply_markup=get_main_keyboard())


@bot.message_handler(func=lambda message: message.text == "⚡ Разовый расчет")
def quick_calc_start(message):
    user_states[message.chat.id] = "QUICK_CALC"
    bot.send_message(message.chat.id, "Введи готовую налоговую базу:", reply_markup=types.ReplyKeyboardRemove())


# --- ОБРАБОТЧИК ВВОДА С КЛАВИАТУРЫ ---
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) is not None)
def process_states(message):
    state = user_states.get(message.chat.id)

    if message.text == "🔙 Отмена":
        user_states[message.chat.id] = None
        bot.send_message(message.chat.id, "Отменено.", reply_markup=get_company_keyboard())
        return

    if state == "CREATE_COMPANY":
        comp_name = message.text.strip()
        # Проверяем, есть ли уже такая
        exists = db_query('SELECT id FROM companies WHERE chat_id = ? AND name = ?', (message.chat.id, comp_name),
                          fetchone=True)
        if not exists:
            db_query('INSERT INTO companies (chat_id, name) VALUES (?, ?)', (message.chat.id, comp_name))
        db_query('UPDATE users SET active_company = ? WHERE chat_id = ?', (comp_name, message.chat.id))
        user_states[message.chat.id] = None
        bot.send_message(message.chat.id, f"Компания **{comp_name}** готова и выбрана!", parse_mode="Markdown",
                         reply_markup=get_company_keyboard())

    elif state == "SWITCH_COMPANY":
        comp_name = message.text.strip()
        exists = db_query('SELECT id FROM companies WHERE chat_id = ? AND name = ?', (message.chat.id, comp_name),
                          fetchone=True)
        if exists:
            db_query('UPDATE users SET active_company = ? WHERE chat_id = ?', (comp_name, message.chat.id))
            user_states[message.chat.id] = None
            bot.send_message(message.chat.id, f"Переключено на: **{comp_name}**", parse_mode="Markdown",
                             reply_markup=get_company_keyboard())
        else:
            bot.send_message(message.chat.id, "Нет такой компании. Нажми '🔙 Отмена'.")

    elif state == "ADD_PROFIT":
        try:
            amount = float(message.text.replace(',', '.'))
            if amount < 0: raise ValueError
            active = db_query('SELECT active_company FROM users WHERE chat_id = ?', (message.chat.id,), fetchone=True)[
                0]
            db_query('UPDATE companies SET income = income + ? WHERE chat_id = ? AND name = ?',
                     (amount, message.chat.id, active))
            user_states[message.chat.id] = None
            bot.send_message(message.chat.id, "Добавлено!", reply_markup=get_main_keyboard())
        except ValueError:
            bot.send_message(message.chat.id, "Введи число.")

    elif state == "QUICK_CALC":
        try:
            amount = float(message.text.replace(',', '.'))
            if amount < 0: raise ValueError
            tax = calculate_ndfl(amount)
            user_states[message.chat.id] = None
            bot.send_message(message.chat.id, f"НДФЛ: **{tax:,.2f} руб.**".replace(',', ' '), parse_mode="Markdown",
                             reply_markup=get_main_keyboard())
        except ValueError:
            bot.send_message(message.chat.id, "Введи число.")


if __name__ == '__main__':
    bot.infinity_polling()
