import telebot
import sqlite3
from datetime import datetime, timedelta
import threading
import time
import schedule
import os
import requests
from flask import Flask

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = [615541596]  # ← ВАШ ID
bot = telebot.TeleBot(TOKEN)

# ========== FLASK ДЛЯ RENDER ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 PRO ТАНЦЫ Бот работает!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/ping')
def ping():
    return "pong", 200

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, 
              group_name TEXT, 
              notify_time INTEGER DEFAULT 30,
              notify_count INTEGER DEFAULT 1)''')
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

DAYS_RU = {
    'Monday': 'Понедельник', 'Tuesday': 'Вторник', 'Wednesday': 'Среда',
    'Thursday': 'Четверг', 'Friday': 'Пятница', 'Saturday': 'Суббота',
    'Sunday': 'Воскресенье'
}

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = telebot.types.KeyboardButton("👥 Выбрать группу")
    btn2 = telebot.types.KeyboardButton("⏰ Настроить уведомления")
    btn3 = telebot.types.KeyboardButton("ℹ️ Мои настройки")
    btn4 = telebot.types.KeyboardButton("📱 Открыть приложение")
    markup.add(btn1, btn2, btn3, btn4)
    return markup

def groups_keyboard():
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    groups = set()
    for day, classes in SCHEDULE.items():
        for cls in classes:
            groups.add(cls.split(' ', 1)[1])
    for group in sorted(groups):
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

# ========== КОМАНДА /start ==========
@bot.message_handler(commands=['start'])
def start(message):
    welcome_text = "💃 **Добро пожаловать в PRO ТАНЦЫ!** 🕺\n\nЯ помогу вам не пропустить тренировки!\n\n👇 **Выберите действие:**"
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown', reply_markup=main_menu())

# ========== ОБРАБОТКА ТЕКСТОВЫХ КНОПОК ==========
@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    user_id = message.chat.id
    text = message.text
    
    if text == "👥 Выбрать группу":
        bot.send_message(user_id, "👥 **Выберите вашу группу:**", parse_mode='Markdown', reply_markup=groups_keyboard())
    
    elif text == "⏰ Настроить уведомления":
        c.execute("SELECT group_name FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        if not result or not result[0]:
            bot.send_message(user_id, "❌ Сначала выберите группу!", reply_markup=main_menu())
            return
        bot.send_message(user_id, "⏰ **За сколько минут напоминать?**", parse_mode='Markdown', reply_markup=notify_times_keyboard())
    
    elif text == "ℹ️ Мои настройки":
        c.execute("SELECT group_name, notify_time, notify_count FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        if result and result[0]:
            group, notify_time, notify_count = result
            bot.send_message(user_id, f"👥 **Группа:** {group}\n⏰ **Напоминания:** за {notify_time} минут\n📨 **Количество:** {notify_count} раз", parse_mode='Markdown', reply_markup=main_menu())
        else:
            bot.send_message(user_id, "❌ Группа не выбрана", reply_markup=main_menu())
    
    elif text == "📱 Открыть приложение":
        markup = telebot.types.InlineKeyboardMarkup()
        app_button = telebot.types.InlineKeyboardButton("📱 Открыть PRO ТАНЦЫ", url="https://ваша-ссылка")
        markup.add(app_button)
        bot.send_message(user_id, "Нажмите кнопку ниже чтобы открыть приложение:", reply_markup=markup)

# ========== ОБРАБОТКА INLINE КНОПОК ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    
    if call.data == "cancel":
        bot.answer_callback_query(call.id, "❌ Отменено")
        bot.delete_message(user_id, call.message.message_id)
        bot.send_message(user_id, "Главное меню:", reply_markup=main_menu())
    
    elif call.data.startswith('group_'):
        group = call.data.replace('group_', '')
        c.execute("""INSERT OR REPLACE INTO users (user_id, group_name, notify_time, notify_count) 
                     VALUES (?, ?, COALESCE((SELECT notify_time FROM users WHERE user_id = ?), 30),
                     COALESCE((SELECT notify_count FROM users WHERE user_id = ?), 1))""",
                  (user_id, group, user_id, user_id))
        conn.commit()
        bot.answer_callback_query(call.id, f"✅ Выбрана группа: {group}")
        bot.edit_message_text(f"✅ **Группа сохранена:** {group}", user_id, call.message.message_id, parse_mode='Markdown')
        bot.send_message(user_id, "Теперь настройте уведомления:", reply_markup=notify_times_keyboard())
    
    elif call.data.startswith('time_'):
        minutes = int(call.data.replace('time_', ''))
        c.execute("UPDATE users SET notify_time = ? WHERE user_id = ?", (minutes, user_id))
        conn.commit()
        bot.answer_callback_query(call.id, f"✅ Время: {minutes} минут")
        bot.edit_message_text(f"✅ Напоминания за {minutes} минут\n\nСколько раз напомнить?", user_id, call.message.message_id)
        bot.send_message(user_id, "Выберите количество:", reply_markup=notify_count_keyboard())
    
    elif call.data.startswith('count_'):
        count = int(call.data.replace('count_', ''))
        c.execute("UPDATE users SET notify_count = ? WHERE user_id = ?", (count, user_id))
        conn.commit()
        c.execute("SELECT group_name, notify_time FROM users WHERE user_id = ?", (user_id,))
        group, time = c.fetchone()
        bot.answer_callback_query(call.id, "✅ Настройки сохранены")
        bot.edit_message_text(f"✅ **Настройки сохранены!**\n\n👥 Группа: {group}\n⏰ Напоминания: за {time} минут\n📨 Количество: {count} раз", user_id, call.message.message_id, parse_mode='Markdown')
        bot.send_message(user_id, "Главное меню:", reply_markup=main_menu())

# ========== КОМАНДА /broadcast (ИСПРАВЛЕНА) ==========
@bot.message_handler(commands=['broadcast'])
def broadcast_start(message):
    user_id = message.chat.id
    
    # Проверяем, админ ли
    if user_id not in ADMIN_IDS:
        bot.send_message(user_id, "⛔ У вас нет прав администратора")
        return
    
    # Спрашиваем сообщение для рассылки
    msg = bot.send_message(
        user_id,
        "📢 **Отправьте сообщение для рассылки всем пользователям**\n\n"
        "Можно отправить:\n"
        "• Текст\n"
        "• Фото с подписью\n"
        "• Видео\n"
        "• Документ\n\n"
        "_После отправки я начну рассылку_",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    admin_id = message.chat.id
    
    # Получаем всех пользователей
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    
    if not users:
        bot.send_message(admin_id, "❌ Нет пользователей для рассылки")
        # Возвращаем в главное меню
        bot.send_message(admin_id, "Главное меню:", reply_markup=main_menu())
        return
    
    # Отправляем статус
    status_msg = bot.send_message(
        admin_id,
        f"📤 Начинаю рассылку **{len(users)}** пользователям...",
        parse_mode='Markdown'
    )
    
    success = 0
    failed = 0
    failed_users = []
    
    for i, (user_id,) in enumerate(users):
        try:
            if message.content_type == 'text':
                bot.send_message(user_id, message.text)
            elif message.content_type == 'photo':
                bot.send_photo(
                    user_id,
                    message.photo[-1].file_id,
                    caption=message.caption
                )
            elif message.content_type == 'video':
                bot.send_video(
                    user_id,
                    message.video.file_id,
                    caption=message.caption
                )
            elif message.content_type == 'document':
                bot.send_document(
                    user_id,
                    message.document.file_id,
                    caption=message.caption
                )
            
            success += 1
            
            # Обновляем статус каждые 10 пользователей
            if i % 10 == 0 and i > 0:
                try:
                    bot.edit_message_text(
                        f"📤 Рассылка: **{i}/{len(users)}** отправлено...\n"
                        f"✅ Успешно: {success}\n"
                        f"❌ Ошибок: {failed}",
                        admin_id,
                        status_msg.message_id,
                        parse_mode='Markdown'
                    )
                except:
                    pass
                    
        except Exception as e:
            failed += 1
            failed_users.append(user_id)
            print(f"❌ Ошибка отправки {user_id}: {e}")
    
    # Финальный отчёт
    final_text = (
        f"✅ **Рассылка завершена!**\n\n"
        f"📊 **Всего:** {len(users)}\n"
        f"✅ **Успешно:** {success}\n"
        f"❌ **Ошибок:** {failed}\n\n"
    )
    
    if failed_users:
        final_text += f"❌ **Не получили:** {len(failed_users)} пользователей"
    
    try:
        bot.edit_message_text(
            final_text,
            admin_id,
            status_msg.message_id,
            parse_mode='Markdown'
        )
    except:
        bot.send_message(admin_id, final_text, parse_mode='Markdown')
    
    # ВАЖНО: Возвращаем админа в главное меню
    bot.send_message(
        admin_id,
        "Главное меню:",
        reply_markup=main_menu()
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
    
    c.execute("""
        SELECT 
            COALESCE(group_name, 'Без группы') as group_name, 
            COUNT(*) as count 
        FROM users 
        GROUP BY group_name
        ORDER BY count DESC
    """)
    groups = c.fetchall()
    
    stats_text = f"📊 **СТАТИСТИКА БОТА**\n\n"
    stats_text += f"👥 **Всего пользователей:** {total_users}\n\n"
    stats_text += f"**По группам:**\n"
    
    for group, count in groups:
        stats_text += f"• {group}: {count}\n"
    
    bot.send_message(user_id, stats_text, parse_mode='Markdown')

# ========== ПЛАНИРОВЩИК УВЕДОМЛЕНИЙ ==========
def check_trainings():
    try:
        now = datetime.now()
        today_en = now.strftime('%A')
        today_ru = DAYS_RU.get(today_en, '')
        current_time = now.strftime('%H:%M')
        today_trainings = SCHEDULE.get(today_ru, [])
        c.execute("SELECT user_id, group_name, notify_time, notify_count FROM users WHERE group_name IS NOT NULL")
        users = c.fetchall()
        for user_id, group, notify_time, notify_count in users:
            for training in today_trainings:
                if group in training:
                    training_time = training.split(' ')[0]
                    t = datetime.strptime(training_time, '%H:%M')
                    for i in range(notify_count):
                        minutes_before = notify_time - (i * 15)
                        if minutes_before > 0:
                            notify_t = (t - timedelta(minutes=minutes_before)).strftime('%H:%M')
                            if current_time == notify_t:
                                try:
                                    if notify_count == 1:
                                        msg = f"⏰ **Напоминание о тренировке!**\n\nЧерез {minutes_before} минут: **{group}**\n🕐 Время: {training_time}\n\nЖдём вас в PRO ТАНЦЫ! 💃🕺"
                                    else:
                                        msg = f"⏰ **Напоминание {i+1}/{notify_count}**\n\nЧерез {minutes_before} минут: **{group}**\n🕐 Время: {training_time}\n\nЖдём вас в PRO ТАНЦЫ! 💃🕺"
                                    bot.send_message(user_id, msg, parse_mode='Markdown')
                                except:
                                    pass
    except Exception as e:
        print(f"❌ Ошибка в планировщике: {e}")

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("=" * 50)
    print("🤖 PRO ТАНЦЫ Бот запущен!")
    print("=" * 50)
    
    # Запускаем планировщик
    schedule.every(1).minutes.do(check_trainings)
    
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(30)
    
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    # Запускаем Flask в отдельном потоке
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Бесконечный цикл с автоперезапуском бота
    while True:
        try:
            print("✅ Бот запущен и слушает...")
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Перезапуск через 5 секунд...")
            time.sleep(5)
            continue