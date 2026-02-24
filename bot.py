import telebot
import sqlite3
from datetime import datetime, timedelta
import threading
import time
import schedule
import os
import re
from flask import Flask

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# ========== FLASK ДЛЯ RENDER ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 PRO ТАНЦЫ Бот работает!"

@app.route('/health')
def health():
    return "OK", 200

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, 
              group_name TEXT, 
              notify_time INTEGER DEFAULT 30,
              notify_count INTEGER DEFAULT 1)''')  # Добавили количество уведомлений
conn.commit()

# ========== РАСПИСАНИЕ ==========
SCHEDULE = {
    'Понедельник': [
        '17:15 Ритмика (3-5 лет)',
        '18:00 Калланетика',
        '19:00 Латина (старшая)',
        '20:00 Латина (новички)'
    ],
    'Вторник': [
        '18:00 Бальные танцы (5-6 лет)',
        '19:00 Бальные танцы (7-9 лет)'
    ],
    'Среда': [
        '18:00 Бальные танцы',
        '19:00 Латина (старшая)',
        '20:00 Индивидуальные'
    ],
    'Четверг': [
        '18:00 Бальные танцы (5-6 лет)',
        '19:00 Бальные танцы (9-12 лет)',
        '20:00 Бачата (новички)'
    ],
    'Пятница': [
        '17:15 Ритмика (3-5 лет)',
        '18:00 Бальные танцы',
        '19:00 Индивидуальные'
    ],
    'Суббота': [
        '9:00 Калланетика',
        '10:00 Бачата + Латина',
        '11:00 Бальные танцы (9-12 лет)',
        '12:00 Индивидуальные'
    ],
    'Воскресенье': []
}

# Словарь для временных данных пользователей
user_data = {}

# ========== КОМАНДА /start ==========
@bot.message_handler(commands=['start'])
def start(message):
    """Приветствие с информацией о приложении и боте"""
    welcome_text = (
        "💃 **Добро пожаловать в РИТМ!** 🕺\n\n"
        "📱 **Наше мобильное приложение:**\n"
        "• Просмотр расписания\n"
        "• Клипы с танцами\n"
        "• Правила клуба\n"
        "• Занятия\n\n"
        "🤖 **Что умеет этот бот:**\n"
        "• Команда /group - выбрать группу\n"
        "• Команда /notify - настроить уведомления\n"
        "• Автоматические напоминания о тренировках\n"
        "• Уведомления об отменах\n\n"
        "⬇️ **Нажмите кнопку ниже чтобы открыть приложение**"
    )
    
    # Клавиатура с кнопкой на приложение
    markup = telebot.types.InlineKeyboardMarkup()
    app_button = telebot.types.InlineKeyboardButton(
        "📱 Открыть РИТМ", 
        url="https://niksiks23.github.io/pro-tancy-app/"  # ЗАМЕНИТЕ НА ССЫЛКУ ВАШЕГО ПРИЛОЖЕНИЯ
    )
    markup.add(app_button)
    
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=markup
    )

# ========== КОМАНДА /group - ВЫБОР ГРУППЫ ==========
@bot.message_handler(commands=['group'])
def choose_group(message):
    """Выбор группы с возможностью изменить"""
    user_id = message.chat.id
    
    # Получаем все группы
    groups = set()
    for day, classes in SCHEDULE.items():
        for cls in classes:
            groups.add(cls.split(' ', 1)[1])
    
    # Создаём клавиатуру
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    # Добавляем кнопку "Сбросить выбор" если уже есть группа
    c.execute("SELECT group_name FROM users WHERE user_id = ?", (user_id,))
    current = c.fetchone()
    if current and current[0]:
        reset_btn = telebot.types.InlineKeyboardButton(
            "❌ Отменить выбор", 
            callback_data="group_reset"
        )
        markup.add(reset_btn)
        markup.add(telebot.types.InlineKeyboardButton("─" * 20, callback_data="separator"))
    
    # Добавляем все группы
    for group in sorted(groups):
        btn_text = f"✅ {group}" if (current and current[0] == group) else group
        markup.add(telebot.types.InlineKeyboardButton(
            btn_text, 
            callback_data=f"group_{group}"
        ))
    
    bot.send_message(
        user_id, 
        "👥 **Выберите вашу группу:**\n"
        "(можно изменить в любой момент)",
        parse_mode='Markdown',
        reply_markup=markup
    )

# ========== КОМАНДА /notify - НАСТРОЙКА УВЕДОМЛЕНИЙ ==========
@bot.message_handler(commands=['notify'])
def notify_settings(message):
    """Настройка уведомлений"""
    user_id = message.chat.id
    
    # Проверяем, выбрана ли группа
    c.execute("SELECT group_name FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if not result or not result[0]:
        bot.send_message(
            user_id,
            "❌ Сначала выберите группу с помощью команды /group"
        )
        return
    
    # Спрашиваем сколько уведомлений
    msg = bot.send_message(
        user_id,
        "⏰ **Настройка уведомлений**\n\n"
        "За сколько минут до тренировки напоминать?\n"
        "Напишите число (например: 30, 60, 120)"
    )
    bot.register_next_step_handler(msg, process_notify_time)

def process_notify_time(message):
    """Обработка введённого времени"""
    user_id = message.chat.id
    
    try:
        minutes = int(message.text.strip())
        if minutes < 5 or minutes > 1440:
            raise ValueError
        
        # Сохраняем время в базу
        c.execute(
            "UPDATE users SET notify_time = ? WHERE user_id = ?",
            (minutes, user_id)
        )
        conn.commit()
        
        # Теперь спрашиваем количество уведомлений
        msg = bot.send_message(
            user_id,
            f"✅ Время: за {minutes} минут\n\n"
            "Сколько уведомлений прислать?\n"
            "(Напишите число: 1, 2 или 3)"
        )
        bot.register_next_step_handler(msg, process_notify_count)
        
    except ValueError:
        bot.send_message(
            user_id,
            "❌ Пожалуйста, напишите число от 5 до 1440"
        )

def process_notify_count(message):
    """Обработка количества уведомлений"""
    user_id = message.chat.id
    
    try:
        count = int(message.text.strip())
        if count < 1 or count > 5:
            raise ValueError
        
        # Сохраняем количество
        c.execute(
            "UPDATE users SET notify_count = ? WHERE user_id = ?",
            (count, user_id)
        )
        conn.commit()
        
        # Получаем текущие настройки
        c.execute(
            "SELECT group_name, notify_time FROM users WHERE user_id = ?",
            (user_id,)
        )
        group, time = c.fetchone()
        
        bot.send_message(
            user_id,
            f"✅ **Настройки сохранены!**\n\n"
            f"👥 Группа: {group}\n"
            f"⏰ Напоминания: за {time} минут\n"
            f"📨 Количество: {count} раз\n\n"
            f"Теперь я буду напоминать о тренировках!"
        )
        
    except ValueError:
        bot.send_message(
            user_id,
            "❌ Пожалуйста, напишите число от 1 до 5"
        )

# ========== КОМАНДА /help ==========
@bot.message_handler(commands=['help'])
def help_command(message):
    """Справка по командам"""
    help_text = (
        "📚 **Доступные команды:**\n\n"
        "/start - Главное меню\n"
        "/group - Выбрать группу\n"
        "/notify - Настроить уведомления\n"
        "/mygroup - Моя группа и настройки\n"
        "/schedule - Расписание на неделю\n"
        "/help - Эта справка\n\n"
        "📱 **Наше приложение:** https://pro-tancy.ru"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

# ========== КОМАНДА /mygroup ==========
@bot.message_handler(commands=['mygroup'])
def my_group(message):
    """Информация о текущей группе"""
    user_id = message.chat.id
    c.execute(
        "SELECT group_name, notify_time, notify_count FROM users WHERE user_id = ?",
        (user_id,)
    )
    result = c.fetchone()
    
    if result and result[0]:
        group, notify_time, notify_count = result
        bot.send_message(
            user_id,
            f"👥 **Ваша группа:** {group}\n"
            f"⏰ **Напоминания:** за {notify_time} минут\n"
            f"📨 **Количество:** {notify_count} раз",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            user_id,
            "❌ Группа не выбрана. Используйте /group"
        )

# ========== КОМАНДА /schedule ==========
@bot.message_handler(commands=['schedule'])
def full_schedule(message):
    """Полное расписание на неделю"""
    text = "📅 **Расписание на неделю**\n\n"
    
    for day, classes in SCHEDULE.items():
        if classes:
            text += f"**{day}:**\n"
            for cls in classes:
                text += f"  • {cls}\n"
            text += "\n"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# ========== ОБРАБОТКА НАЖАТИЙ НА КНОПКИ ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    
    if call.data == "group_reset":
        # Сброс группы
        c.execute("UPDATE users SET group_name = NULL WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ Выбор отменён")
        bot.edit_message_text(
            "✅ Выбор группы отменён. Используйте /group чтобы выбрать новую",
            user_id,
            call.message.message_id
        )
        
    elif call.data.startswith('group_'):
        group = call.data.replace('group_', '')
        
        # Сохраняем группу
        c.execute(
            "INSERT OR REPLACE INTO users (user_id, group_name, notify_time, notify_count) VALUES (?, ?, COALESCE((SELECT notify_time FROM users WHERE user_id = ?), 30), COALESCE((SELECT notify_count FROM users WHERE user_id = ?), 1))",
            (user_id, group, user_id, user_id)
        )
        conn.commit()
        
        bot.answer_callback_query(call.id, f"✅ Выбрана группа: {group}")
        
        # Обновляем сообщение
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(telebot.types.InlineKeyboardButton(
            "⏰ Настроить уведомления",
            callback_data="go_to_notify"
        ))
        
        bot.edit_message_text(
            f"✅ **Группа сохранена:** {group}\n\n"
            f"Теперь настройте уведомления с помощью команды /notify",
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    
    elif call.data == "go_to_notify":
        bot.answer_callback_query(call.id)
        bot.send_message(
            user_id,
            "Используйте команду /notify для настройки уведомлений"
        )

# ========== ПЛАНИРОВЩИК УВЕДОМЛЕНИЙ ==========
def check_trainings():
    """Проверка тренировок и отправка уведомлений"""
    print(f"🕐 Проверка тренировок... {datetime.now().strftime('%H:%M')}")
    
    now = datetime.now()
    today = now.strftime('%A')
    current_time = now.strftime('%H:%M')
    
    days_map = {
        'Monday': 'Понедельник', 'Tuesday': 'Вторник', 'Wednesday': 'Среда',
        'Thursday': 'Четверг', 'Friday': 'Пятница', 'Saturday': 'Суббота',
        'Sunday': 'Воскресенье'
    }
    today_ru = days_map.get(today, '')
    
    today_trainings = SCHEDULE.get(today_ru, [])
    
    # Получаем всех пользователей с группами
    c.execute("SELECT user_id, group_name, notify_time, notify_count FROM users WHERE group_name IS NOT NULL")
    users = c.fetchall()
    
    for user_id, group, notify_time, notify_count in users:
        for training in today_trainings:
            if group in training:
                training_time = training.split(' ')[0]
                
                t = datetime.strptime(training_time, '%H:%M')
                
                # Отправляем несколько уведомлений если нужно
                for i in range(notify_count):
                    minutes_before = notify_time + (i * 15)  # С интервалом 15 минут
                    notify_t = (t - timedelta(minutes=minutes_before)).strftime('%H:%M')
                    
                    if current_time == notify_t:
                        try:
                            msg = (
                                f"⏰ **Напоминание {i+1}/{notify_count}!**\n\n"
                                f"Через {minutes_before} минут: **{group}**\n"
                                f"🕐 Время: {training_time}\n\n"
                                f"Ждём вас в PRO ТАНЦЫ! 💃🕺"
                            )
                            bot.send_message(user_id, msg, parse_mode='Markdown')
                            print(f"✅ Уведомление {i+1} отправлено {user_id}")
                        except Exception as e:
                            print(f"❌ Ошибка отправки {user_id}: {e}")

# Запускаем планировщик
def run_scheduler():
    schedule.every(1).minutes.do(check_trainings)
    while True:
        schedule.run_pending()
        time.sleep(30)

threading.Thread(target=run_scheduler, daemon=True).start()

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("=" * 50)
    print("🤖 PRO ТАНЦЫ Бот запущен!")
    print("=" * 50)
    print("Команды:")
    print("  /start  - Главное меню")
    print("  /group  - Выбор группы")
    print("  /notify - Настройка уведомлений")
    print("  /mygroup - Моя группа")
    print("  /schedule - Расписание")
    print("  /help   - Справка")
    print("=" * 50)
    
    # Запускаем бота в отдельном потоке
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    
    # Запускаем Flask сервер для Render
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
