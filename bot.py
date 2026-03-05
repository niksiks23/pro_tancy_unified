import telebot
import sqlite3
from datetime import datetime, timedelta
import threading
import time
import schedule
import os
import requests
from flask import Flask
import signal
import sys

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = [615541596]  # ← ВАШ ID
bot = telebot.TeleBot(TOKEN)

# ========== FLASK ДЛЯ RENDER ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 РИТМ Бот работает!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/ping')
def ping():
    return "pong", 200

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()

# Таблица пользователей
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, 
              username TEXT,
              first_name TEXT,
              last_name TEXT,
              joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

# Таблица уведомлений
c.execute('''CREATE TABLE IF NOT EXISTS notifications
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER,
              group_name TEXT,
              notify_time INTEGER,
              notify_count INTEGER DEFAULT 1,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(user_id, group_name))''')
conn.commit()

# ========== РАСПИСАНИЕ ИЗ ПРИЛОЖЕНИЯ ==========
WEEKLY_SCHEDULE = {
    1: [  # Понедельник
        {'time': '17:15', 'name': 'Ритмика (3-5 лет)'},
        {'time': '18:00', 'name': 'Калланетика'},
        {'time': '19:00', 'name': 'Латина (старшая)'},
        {'time': '20:00', 'name': 'Латина (новички)'}
    ],
    2: [  # Вторник
        {'time': '18:00', 'name': 'Бальные танцы (5-6 лет)'},
        {'time': '19:00', 'name': 'Бальные танцы (7-9 лет)'}
    ],
    3: [  # Среда
        {'time': '18:00', 'name': 'Бальные танцы'},
        {'time': '19:00', 'name': 'Латина (старшая)'},
        {'time': '20:00', 'name': 'Индивидуальные'}
    ],
    4: [  # Четверг
        {'time': '18:00', 'name': 'Бальные танцы (5-6 лет)'},
        {'time': '19:00', 'name': 'Бальные танцы (9-12 лет)'},
        {'time': '20:00', 'name': 'Бачата (новички)'}
    ],
    5: [  # Пятница
        {'time': '17:15', 'name': 'Ритмика (3-5 лет)'},
        {'time': '18:00', 'name': 'Бальные танцы'},
        {'time': '19:00', 'name': 'Индивидуальные'}
    ],
    6: [  # Суббота
        {'time': '9:00', 'name': 'Калланетика'},
        {'time': '10:00', 'name': 'Бачата + Латина'},
        {'time': '11:00', 'name': 'Бальные танцы (9-12 лет)'},
        {'time': '12:00', 'name': 'Индивидуальные'}
    ],
    0: []  # Воскресенье
}

# Список всех групп
ALL_GROUPS = [
    'Ритмика (3-5 лет)',
    'Бальные танцы (5-6 лет)',
    'Бальные танцы (7-9 лет)',
    'Бальные танцы (9-12 лет)',
    'Латина (новички)',
    'Латина (старшая)',
    'Калланетика',
    'Бачата (новички)',
    'Индивидуальные'
]

# Дни недели на русском
DAYS_RU = {
    'Monday': 'Понедельник',
    'Tuesday': 'Вторник',
    'Wednesday': 'Среда',
    'Thursday': 'Четверг',
    'Friday': 'Пятница',
    'Saturday': 'Суббота',
    'Sunday': 'Воскресенье'
}

# ========== ПИНГОВАЛКА ==========
def keep_alive():
    url = os.environ.get('RENDER_URL', 'https://ritm-bot.onrender.com')
    while True:
        try:
            requests.get(f"{url}/ping", timeout=10)
            print(f"✅ Self-ping в {datetime.now().strftime('%H:%M:%S')}")
        except:
            pass
        time.sleep(240)

threading.Thread(target=keep_alive, daemon=True).start()

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    """Главное меню - только уведомления"""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = telebot.types.KeyboardButton("🔔 Настроить уведомления")
    btn2 = telebot.types.KeyboardButton("📋 Мои уведомления")
    markup.add(btn1, btn2)
    return markup

def groups_keyboard():
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    for group in ALL_GROUPS:
        markup.add(telebot.types.InlineKeyboardButton(group, callback_data=f"group_{group}"))
    markup.add(telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return markup

def notify_times_keyboard():
    markup = telebot.types.InlineKeyboardMarkup(row_width=3)
    times = [15, 30, 45, 60, 90, 120]
    buttons = []
    for t in times:
        buttons.append(telebot.types.InlineKeyboardButton(f"{t} мин", callback_data=f"time_{t}"))
    markup.add(*buttons)
    markup.add(telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return markup

def notify_count_keyboard():
    markup = telebot.types.InlineKeyboardMarkup(row_width=3)
    counts = [1, 2, 3]
    buttons = []
    for c in counts:
        buttons.append(telebot.types.InlineKeyboardButton(f"{c} раз", callback_data=f"count_{c}"))
    markup.add(*buttons)
    markup.add(telebot.types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return markup

def notification_actions_keyboard(group_name):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        telebot.types.InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{group_name}"),
        telebot.types.InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{group_name}")
    )
    markup.add(telebot.types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu"))
    return markup

# ========== КОМАНДА /start ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # Сохраняем пользователя
    try:
        c.execute('''INSERT OR IGNORE INTO users 
                     (user_id, username, first_name, last_name) 
                     VALUES (?, ?, ?, ?)''',
                  (user_id, username, first_name, last_name))
        conn.commit()
    except:
        pass
    
    welcome_text = (
        "🌸 **Добро пожаловать в РИТМ!** 🕺\n\n"
        "📱 **Наше мобильное приложение:**\n"
        "https://ваша-ссылка\n\n"
        "🤖 **Я буду присылать вам уведомления о тренировках!**\n\n"
        "👇 **Выберите действие:**"
    )
    
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown', reply_markup=main_menu())

# ========== ОБРАБОТКА КНОПОК МЕНЮ ==========
@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    user_id = message.chat.id
    text = message.text
    
    if text == "🔔 Настроить уведомления":
        start_notify_setup(user_id)
    
    elif text == "📋 Мои уведомления":
        show_my_notifications(user_id)

# ========== НАСТРОЙКА УВЕДОМЛЕНИЙ ==========
def start_notify_setup(user_id):
    msg = bot.send_message(
        user_id,
        "🔔 **Настройка уведомлений**\n\n"
        "Выберите группу:",
        parse_mode='Markdown',
        reply_markup=groups_keyboard()
    )
    bot.register_next_step_handler(msg, lambda m: None)

# ========== ОБРАБОТКА INLINE КНОПОК ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    
    if call.data == "cancel":
        bot.answer_callback_query(call.id, "❌ Отменено")
        bot.delete_message(user_id, call.message.message_id)
        bot.send_message(user_id, "Главное меню:", reply_markup=main_menu())
    
    elif call.data == "back_to_menu":
        bot.answer_callback_query(call.id)
        bot.delete_message(user_id, call.message.message_id)
        bot.send_message(user_id, "Главное меню:", reply_markup=main_menu())
    
    elif call.data.startswith('group_'):
        group = call.data.replace('group_', '')
        
        # Проверяем, есть ли уже уведомление для этой группы
        c.execute("SELECT id FROM notifications WHERE user_id = ? AND group_name = ?", 
                  (user_id, group))
        exists = c.fetchone()
        
        if exists:
            bot.answer_callback_query(call.id, "⚠️ Уже есть")
            bot.edit_message_text(
                f"⚠️ У вас уже настроены уведомления для группы:\n**{group}**\n\n"
                f"Что хотите сделать?",
                user_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=notification_actions_keyboard(group)
            )
            return
        
        # Сохраняем выбранную группу во временные данные
        if not hasattr(bot, 'temp_data'):
            bot.temp_data = {}
        bot.temp_data[user_id] = {'group': group}
        
        bot.answer_callback_query(call.id, f"✅ Группа: {group}")
        bot.edit_message_text(
            f"✅ Выбрана группа: **{group}**\n\n"
            f"⏰ За сколько минут напоминать?",
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=notify_times_keyboard()
        )
    
    elif call.data.startswith('time_'):
        minutes = int(call.data.replace('time_', ''))
        
        # Сохраняем время
        if not hasattr(bot, 'temp_data'):
            bot.temp_data = {}
        if user_id not in bot.temp_data:
            bot.temp_data[user_id] = {}
        bot.temp_data[user_id]['time'] = minutes
        
        bot.answer_callback_query(call.id, f"✅ Время: {minutes} мин")
        bot.edit_message_text(
            f"✅ Напоминания за **{minutes}** минут\n\n"
            f"📨 Сколько раз напомнить?",
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=notify_count_keyboard()
        )
    
    elif call.data.startswith('count_'):
        count = int(call.data.replace('count_', ''))
        
        # Получаем сохранённые данные
        if hasattr(bot, 'temp_data') and user_id in bot.temp_data:
            group = bot.temp_data[user_id].get('group')
            minutes = bot.temp_data[user_id].get('time')
            
            if group and minutes:
                # Сохраняем в базу
                c.execute('''INSERT OR REPLACE INTO notifications 
                             (user_id, group_name, notify_time, notify_count) 
                             VALUES (?, ?, ?, ?)''',
                          (user_id, group, minutes, count))
                conn.commit()
                
                bot.answer_callback_query(call.id, "✅ Уведомления настроены")
                bot.edit_message_text(
                    f"✅ **Уведомления настроены!**\n\n"
                    f"👥 Группа: **{group}**\n"
                    f"⏰ Напоминания: за **{minutes}** минут\n"
                    f"📨 Количество: **{count}** раз\n\n"
                    f"Теперь я буду напоминать о тренировках!",
                    user_id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                bot.send_message(user_id, "Главное меню:", reply_markup=main_menu())
                
                # Очищаем временные данные
                del bot.temp_data[user_id]
    
    elif call.data.startswith('edit_'):
        group = call.data.replace('edit_', '')
        
        # Удаляем старую запись
        c.execute("DELETE FROM notifications WHERE user_id = ? AND group_name = ?", 
                  (user_id, group))
        conn.commit()
        
        # Сохраняем группу во временные данные
        if not hasattr(bot, 'temp_data'):
            bot.temp_data = {}
        bot.temp_data[user_id] = {'group': group}
        
        bot.answer_callback_query(call.id, "✏️ Изменение")
        bot.edit_message_text(
            f"✏️ **Изменение уведомлений для {group}**\n\n"
            f"⏰ За сколько минут напоминать?",
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=notify_times_keyboard()
        )
    
    elif call.data.startswith('delete_'):
        group = call.data.replace('delete_', '')
        
        c.execute("DELETE FROM notifications WHERE user_id = ? AND group_name = ?", 
                  (user_id, group))
        conn.commit()
        
        bot.answer_callback_query(call.id, "✅ Удалено")
        bot.edit_message_text(
            f"✅ Уведомления для группы **{group}** удалены",
            user_id,
            call.message.message_id,
            parse_mode='Markdown'
        )
        bot.send_message(user_id, "Главное меню:", reply_markup=main_menu())

# ========== ПОКАЗАТЬ МОИ УВЕДОМЛЕНИЯ ==========
def show_my_notifications(user_id):
    c.execute('''SELECT group_name, notify_time, notify_count 
                 FROM notifications 
                 WHERE user_id = ? 
                 ORDER BY created_at DESC''', (user_id,))
    notifications = c.fetchall()
    
    if not notifications:
        bot.send_message(
            user_id,
            "📋 У вас пока нет настроенных уведомлений.\n"
            "Нажмите '🔔 Настроить уведомления' чтобы добавить.",
            reply_markup=main_menu()
        )
        return
    
    text = "📋 **Ваши уведомления:**\n\n"
    for group, notify_time, notify_count in notifications:
        text += f"👥 **{group}**\n"
        text += f"   ⏰ за {notify_time} мин\n"
        text += f"   📨 {notify_count} раз(а)\n\n"
    
    bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=main_menu())

# ========== КОМАНДА /broadcast ==========
@bot.message_handler(commands=['broadcast'])
def broadcast_start(message):
    user_id = message.chat.id
    
    if user_id not in ADMIN_IDS:
        bot.send_message(user_id, "⛔ У вас нет прав администратора")
        return
    
    msg = bot.send_message(
        user_id,
        "📢 **Отправьте сообщение для рассылки всем пользователям**",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    admin_id = message.chat.id
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    
    if not users:
        bot.send_message(admin_id, "❌ Нет пользователей")
        return
    
    status_msg = bot.send_message(admin_id, f"📤 Рассылка {len(users)} пользователям...")
    
    success = 0
    failed = 0
    
    for i, (user_id,) in enumerate(users):
        try:
            if message.content_type == 'text':
                bot.send_message(user_id, message.text)
            elif message.content_type == 'photo':
                bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption)
            elif message.content_type == 'video':
                bot.send_video(user_id, message.video.file_id, caption=message.caption)
            elif message.content_type == 'document':
                bot.send_document(user_id, message.document.file_id, caption=message.caption)
            success += 1
        except:
            failed += 1
    
    bot.edit_message_text(
        f"✅ Рассылка завершена!\n\n📊 Всего: {len(users)}\n✅ Успешно: {success}\n❌ Ошибок: {failed}",
        admin_id,
        status_msg.message_id
    )

# ========== КОМАНДА /stats ==========
@bot.message_handler(commands=['stats'])
def show_stats(message):
    user_id = message.chat.id
    
    if user_id not in ADMIN_IDS:
        bot.send_message(user_id, "⛔ У вас нет прав администратора")
        return
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM notifications")
    total_notifications = c.fetchone()[0]
    
    c.execute("SELECT COUNT(DISTINCT user_id) FROM notifications")
    users_with_notifications = c.fetchone()[0]
    
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT COUNT(*) FROM users WHERE joined_date LIKE ?", (f"{today}%",))
    today_users = c.fetchone()[0]
    
    stats_text = (
        f"📊 **СТАТИСТИКА БОТА**\n\n"
        f"👥 **Всего пользователей:** {total_users}\n"
        f"📅 **За сегодня:** {today_users}\n"
        f"🔔 **Всего уведомлений:** {total_notifications}\n"
        f"📋 **Пользователей с уведомлениями:** {users_with_notifications}"
    )
    
    bot.send_message(user_id, stats_text, parse_mode='Markdown')

# ========== ПЛАНИРОВЩИК УВЕДОМЛЕНИЙ ==========
def check_trainings():
    try:
        now = datetime.now()
        current_time = now.strftime('%H:%M')
        day_of_week = now.isoweekday()
        
        today_trainings = WEEKLY_SCHEDULE.get(day_of_week, [])
        
        # Получаем все уведомления
        c.execute('''SELECT user_id, group_name, notify_time, notify_count 
                     FROM notifications''')
        notifications = c.fetchall()
        
        for user_id, group, notify_time, notify_count in notifications:
            for training in today_trainings:
                if group in training['name']:
                    training_time = training['time']
                    t = datetime.strptime(training_time, '%H:%M')
                    
                    for i in range(notify_count):
                        minutes_before = notify_time - (i * 15)
                        
                        if minutes_before > 0:
                            notify_t = (t - timedelta(minutes=minutes_before)).strftime('%H:%M')
                            
                            if current_time == notify_t:
                                try:
                                    if notify_count == 1:
                                        msg = (
                                            f"🔔 **Напоминание о тренировке!**\n\n"
                                            f"Через {minutes_before} минут: **{group}**\n"
                                            f"🕐 Время: {training_time}\n\n"
                                            f"Ждём вас в РИТМ! 💃🕺"
                                        )
                                    else:
                                        msg = (
                                            f"🔔 **Напоминание {i+1}/{notify_count}**\n\n"
                                            f"Через {minutes_before} минут: **{group}**\n"
                                            f"🕐 Время: {training_time}\n\n"
                                            f"Ждём вас в РИТМ! 💃🕺"
                                        )
                                    
                                    bot.send_message(user_id, msg, parse_mode='Markdown')
                                    print(f"✅ Уведомление {user_id} для {group} в {training_time}")
                                except:
                                    pass
    except Exception as e:
        print(f"❌ Ошибка в планировщике: {e}")

# Запуск планировщика
def run_scheduler():
    schedule.every(1).minutes.do(check_trainings)
    while True:
        schedule.run_pending()
        time.sleep(30)

threading.Thread(target=run_scheduler, daemon=True).start()

# ========== ЗАЩИТА ОТ ДВОЙНОГО ЗАПУСКА ==========
def cleanup():
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("=" * 50)
    print("🌸 РИТМ Бот запущен!")
    print("=" * 50)
    
    # Запуск Flask
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Запуск бота с автоперезапуском
    while True:
        try:
            print("✅ Бот слушает...")
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Перезапуск через 5 секунд...")
            time.sleep(5)
            continue