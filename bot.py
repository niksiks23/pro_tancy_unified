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
    return "🤖 РИТМ Бот работает!"

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

# ========== КОМАНДА /start ==========
@bot.message_handler(commands=['start'])
def start(message):
    welcome_text = (
        "💃 **Добро пожаловать в РИТМ!** 🕺\n\n"
        "📱 **Наше мобильное приложение:**\n"
        "• Просмотр расписания\n"
        "• Клипы с танцами\n"
        "• Профиль\n"
        "• Виды занятий\n\n"
        "🤖 **Что умеет этот бот:**\n"
        "• /group - выбрать группу\n"
        "• /notify - настроить уведомления\n"
        "• /mygroup - мои настройки\n\n"
        "⬇️ **Открыть приложение**"
    )
    
    markup = telebot.types.InlineKeyboardMarkup()
    app_button = telebot.types.InlineKeyboardButton(
        "📱 Открыть РИТМ", 
        url="https://niksiks23.github.io/pro-tancy-app/"  # ← ЗАМЕНИТЕ
    )
    markup.add(app_button)
    
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=markup
    )

# ========== КОМАНДА /group ==========
@bot.message_handler(commands=['group'])
def choose_group(message):
    user_id = message.chat.id
    
    # Получаем все группы
    groups = set()
    for day, classes in SCHEDULE.items():
        for cls in classes:
            groups.add(cls.split(' ', 1)[1])
    
    # Создаём клавиатуру
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    # Проверяем текущую группу
    c.execute("SELECT group_name FROM users WHERE user_id = ?", (user_id,))
    current = c.fetchone()
    
    if current and current[0]:
        reset_btn = telebot.types.InlineKeyboardButton(
            "❌ Отменить выбор", 
            callback_data="group_reset"
        )
        markup.add(reset_btn)
        markup.add(telebot.types.InlineKeyboardButton("─" * 20, callback_data="separator"))
    
    for group in sorted(groups):
        btn_text = f"✅ {group}" if (current and current[0] == group) else group
        markup.add(telebot.types.InlineKeyboardButton(
            btn_text, 
            callback_data=f"group_{group}"
        ))
    
    bot.send_message(
        user_id, 
        "👥 **Выберите вашу группу:**",
        parse_mode='Markdown',
        reply_markup=markup
    )

# ========== КОМАНДА /notify ==========
@bot.message_handler(commands=['notify'])
def notify_settings(message):
    user_id = message.chat.id
    
    c.execute("SELECT group_name FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if not result or not result[0]:
        bot.send_message(
            user_id,
            "❌ Сначала выберите группу с помощью /group"
        )
        return
    
    msg = bot.send_message(
        user_id,
        "⏰ **Настройка уведомлений**\n\n"
        "За сколько минут до тренировки напоминать?\n"
        "(Напишите число: 15, 30, 60, 120)"
    )
    bot.register_next_step_handler(msg, process_notify_time)

def process_notify_time(message):
    user_id = message.chat.id
    
    try:
        minutes = int(message.text.strip())
        if minutes < 5 or minutes > 1440:
            raise ValueError
        
        c.execute(
            "UPDATE users SET notify_time = ? WHERE user_id = ?",
            (minutes, user_id)
        )
        conn.commit()
        
        msg = bot.send_message(
            user_id,
            f"✅ Время: за {minutes} минут\n\n"
            "Сколько уведомлений прислать?\n"
            "(Напишите 1, 2 или 3)"
        )
        bot.register_next_step_handler(msg, process_notify_count)
        
    except ValueError:
        bot.send_message(
            user_id,
            "❌ Напишите число от 5 до 1440"
        )

def process_notify_count(message):
    user_id = message.chat.id
    
    try:
        count = int(message.text.strip())
        if count < 1 or count > 5:
            raise ValueError
        
        c.execute(
            "UPDATE users SET notify_count = ? WHERE user_id = ?",
            (count, user_id)
        )
        conn.commit()
        
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
            "❌ Напишите число от 1 до 5"
        )

# ========== КОМАНДА /mygroup ==========
@bot.message_handler(commands=['mygroup'])
def my_group(message):
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

# ========== КОМАНДА /help ==========
@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "📚 **Доступные команды:**\n\n"
        "/start - Главное меню\n"
        "/group - Выбрать группу\n"
        "/notify - Настроить уведомления\n"
        "/mygroup - Мои настройки\n"
        "/help - Эта справка"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

# ========== ОБРАБОТКА КНОПОК ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    
    if call.data == "group_reset":
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
        
        c.execute(
            """INSERT OR REPLACE INTO users 
               (user_id, group_name, notify_time, notify_count) 
               VALUES (?, ?, 
               COALESCE((SELECT notify_time FROM users WHERE user_id = ?), 30),
               COALESCE((SELECT notify_count FROM users WHERE user_id = ?), 1))""",
            (user_id, group, user_id, user_id)
        )
        conn.commit()
        
        bot.answer_callback_query(call.id, f"✅ Выбрана группа: {group}")
        bot.edit_message_text(
            f"✅ **Группа сохранена:** {group}\n\n"
            f"Теперь настройте уведомления с помощью /notify",
            user_id,
            call.message.message_id,
            parse_mode='Markdown'
        )

# ========== КОМАНДА /broadcast (ТОЛЬКО ДЛЯ АДМИНА) ==========
@bot.message_handler(commands=['broadcast'])
def broadcast_start(message):
    user_id = message.chat.id
    
    if user_id not in ADMIN_IDS:
        bot.send_message(user_id, "⛔ У вас нет прав администратора")
        return
    
    msg = bot.send_message(
        user_id,
        "📢 **Отправьте сообщение для рассылки всем пользователям**\n\n"
        "Можно отправить:\n"
        "• Текст\n"
        "• Фото с подписью\n"
        "• Видео\n"
        "• Документ\n\n"
        "_Все пользователи получат это сообщение_",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    admin_id = message.chat.id
    
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    
    if not users:
        bot.send_message(admin_id, "❌ Нет пользователей для рассылки")
        return
    
    status_msg = bot.send_message(
        admin_id,
        f"📤 Начинаю рассылку **{len(users)}** пользователям...",
        parse_mode='Markdown'
    )
    
    success = 0
    failed = 0
    
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
            print(f"❌ Ошибка отправки {user_id}: {e}")
    
    final_text = (
        f"✅ **Рассылка завершена!**\n\n"
        f"📊 **Всего:** {len(users)}\n"
        f"✅ **Успешно:** {success}\n"
        f"❌ **Ошибок:** {failed}"
    )
    
    try:
        bot.edit_message_text(
            final_text,
            admin_id,
            status_msg.message_id,
            parse_mode='Markdown'
        )
    except:
        bot.send_message(admin_id, final_text, parse_mode='Markdown')

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

# ========== ПЛАНИРОВЩИК УВЕДОМЛЕНИЙ (ИСПРАВЛЕННЫЙ) ==========
def check_trainings():
    """Проверка тренировок и отправка уведомлений"""
    print(f"🕐 Проверка тренировок... {datetime.now().strftime('%H:%M')}")
    
    now = datetime.now()
    today_en = now.strftime('%A')
    today_ru = DAYS_RU.get(today_en, '')
    current_time = now.strftime('%H:%M')
    
    today_trainings = SCHEDULE.get(today_ru, [])
    
    # Получаем всех пользователей с группами
    c.execute("SELECT user_id, group_name, notify_time, notify_count FROM users WHERE group_name IS NOT NULL")
    users = c.fetchall()
    
    for user_id, group, notify_time, notify_count in users:
        for training in today_trainings:
            if group in training:
                training_time = training.split(' ')[0]
                
                # Конвертируем время тренировки в datetime
                t = datetime.strptime(training_time, '%H:%M')
                
                # Для каждого уведомления (1, 2 или 3)
                for i in range(notify_count):
                    # Первое уведомление за notify_time минут
                    # Второе за notify_time - 15 минут (если есть)
                    # Третье за notify_time - 30 минут (если есть)
                    minutes_before = notify_time - (i * 15)
                    
                    if minutes_before > 0:
                        notify_t = (t - timedelta(minutes=minutes_before)).strftime('%H:%M')
                        
                        # Если время совпадает с текущим
                        if current_time == notify_t:
                            try:
                                if notify_count == 1:
                                    msg = (
                                        f"⏰ **Напоминание о тренировке!**\n\n"
                                        f"Через {minutes_before} минут: **{group}**\n"
                                        f"🕐 Время: {training_time}\n\n"
                                        f"Ждём вас в PRO ТАНЦЫ! 💃🕺"
                                    )
                                else:
                                    msg = (
                                        f"⏰ **Напоминание {i+1}/{notify_count}**\n\n"
                                        f"Через {minutes_before} минут: **{group}**\n"
                                        f"🕐 Время: {training_time}\n\n"
                                        f"Ждём вас в PRO ТАНЦЫ! 💃🕺"
                                    )
                                
                                bot.send_message(user_id, msg, parse_mode='Markdown')
                                print(f"✅ Уведомление {i+1} отправлено {user_id} для {group} в {training_time}")
                                
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
    print("🤖 РИТМ Бот запущен!")
    print("=" * 50)
    print(f"👤 Админ ID: {ADMIN_IDS[0]}")
    print("=" * 50)
    
    # Запускаем бота
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    
    # Запускаем Flask для Render
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)