import telebot
import sqlite3
from datetime import datetime, timedelta
import threading
import time
import schedule

# ========== НАСТРОЙКИ ==========
TOKEN = "8548814750:AAGaFDFTLGarzYMRUke0wtl6QPZpL-NGZy0"
bot = telebot.TeleBot(TOKEN)

# ========== РАСПИСАНИЕ ==========
SCHEDULE = {
    'Понедельник': ['17:15 Ритмика (3-5)', '18:00 Калланетика', '19:00 Латина (старшая)', '20:00 Латина (новички)'],
    'Вторник': ['18:00 Бальные (5-6)', '19:00 Бальные (7-9)'],
    'Среда': ['18:00 Бальные', '19:00 Латина (старшая)', '20:00 Индивидуальные'],
    'Четверг': ['18:00 Бальные (5-6)', '19:00 Бальные (9-12)', '20:00 Бачата'],
    'Пятница': ['17:15 Ритмика (3-5)', '18:00 Бальные', '19:00 Индивидуальные'],
    'Суббота': ['9:00 Калланетика', '10:00 Бачата+Латина', '11:00 Бальные (9-12)', '12:00 Индивидуальные'],
    'Воскресенье': []
}

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, 
              group_name TEXT, 
              notify_time INTEGER DEFAULT 30)''')
conn.commit()

# ========== КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📅 Выбрать группу', '⏰ Время уведомления')
    markup.row('📋 Моё расписание', 'ℹ️ Помощь')
    
    bot.send_message(message.chat.id, 
                     "👋 Добро пожаловать в PRO ТАНЦЫ!\n\n"
                     "Я буду напоминать о тренировках.\n"
                     "Выберите действие:", 
                     reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '📅 Выбрать группу')
def choose_group(message):
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    # Собираем все группы
    groups = set()
    for day, classes in SCHEDULE.items():
        for cls in classes:
            groups.add(cls.split(' ', 1)[1])
    
    for group in sorted(groups):
        markup.add(telebot.types.InlineKeyboardButton(group, callback_data=f'group_{group}'))
    
    bot.send_message(message.chat.id, "Выберите вашу группу:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '⏰ Время уведомления')
def choose_time(message):
    markup = telebot.types.InlineKeyboardMarkup(row_width=3)
    times = [15, 30, 45, 60, 90, 120]
    buttons = []
    for t in times:
        buttons.append(telebot.types.InlineKeyboardButton(f'{t} мин', callback_data=f'time_{t}'))
    markup.add(*buttons)
    
    bot.send_message(message.chat.id, "За сколько минут напоминать?", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '📋 Моё расписание')
def my_schedule(message):
    user_id = message.chat.id
    c.execute("SELECT group_name FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if not result:
        bot.send_message(user_id, "❌ Сначала выберите группу!")
        return
    
    group = result[0]
    text = f"📅 **Расписание для {group}**\n\n"
    
    for day, classes in SCHEDULE.items():
        for cls in classes:
            if group in cls:
                text += f"• {day}: {cls}\n"
    
    bot.send_message(user_id, text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    
    if call.data.startswith('group_'):
        group = call.data.replace('group_', '')
        c.execute("INSERT OR REPLACE INTO users (user_id, group_name) VALUES (?, ?)", 
                  (user_id, group))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ Группа сохранена!")
        bot.send_message(user_id, f"✅ Выбрана группа: {group}\nТеперь выберите время уведомления.")
        
    elif call.data.startswith('time_'):
        time = int(call.data.replace('time_', ''))
        c.execute("UPDATE users SET notify_time = ? WHERE user_id = ?", (time, user_id))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ Время сохранено!")
        bot.send_message(user_id, f"✅ Уведомления будут приходить за {time} минут до тренировки!")

# ========== ПЛАНИРОВЩИК УВЕДОМЛЕНИЙ ==========
def check_trainings():
    print(f"🕐 Проверка тренировок... {datetime.now()}")
    
    now = datetime.now()
    today = now.strftime('%A')
    current_time = now.strftime('%H:%M')
    
    # Конвертируем дни на русский
    days_map = {
        'Monday': 'Понедельник', 'Tuesday': 'Вторник', 'Wednesday': 'Среда',
        'Thursday': 'Четверг', 'Friday': 'Пятница', 'Saturday': 'Суббота',
        'Sunday': 'Воскресенье'
    }
    today_ru = days_map.get(today, '')
    
    # Получаем тренировки на сегодня
    today_trainings = SCHEDULE.get(today_ru, [])
    
    # Получаем всех пользователей
    c.execute("SELECT user_id, group_name, notify_time FROM users")
    users = c.fetchall()
    
    for user_id, group, notify_time in users:
        for training in today_trainings:
            if group in training:
                training_time = training.split(' ')[0]
                
                # Вычисляем время отправки
                t = datetime.strptime(training_time, '%H:%M')
                notify_t = (t - timedelta(minutes=notify_time)).strftime('%H:%M')
                
                if current_time == notify_t:
                    try:
                        bot.send_message(user_id, 
                            f"⏰ **Напоминание!**\n\n"
                            f"Через {notify_time} минут: **{group}**\n"
                            f"🕐 Время: {training_time}\n\n"
                            f"Ждём вас! 💃🕺",
                            parse_mode='Markdown')
                        print(f"✅ Уведомление отправлено {user_id}")
                    except:
                        print(f"❌ Ошибка отправки {user_id}")

# Запускаем планировщик в отдельном потоке
def run_scheduler():
    schedule.every(1).minutes.do(check_trainings)
    while True:
        schedule.run_pending()
        time.sleep(30)

threading.Thread(target=run_scheduler, daemon=True).start()

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🚀 Бот запущен!")
    bot.infinity_polling()