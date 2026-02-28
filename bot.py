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
ADMIN_IDS = [5276187604]  # ← ВАШ ID
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
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, 
              username TEXT,
              first_name TEXT,
              last_name TEXT,
              joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

# ========== ПИНГОВАЛКА (КАЖДЫЕ 4 МИНУТЫ) ==========
def keep_alive():
    """Пингование самого себя каждые 4 минуты"""
    url = os.environ.get('RENDER_URL', 'https://pro-tancy-bot.onrender.com')
    while True:
        try:
            requests.get(f"{url}/ping", timeout=10)
            print(f"✅ Self-ping успешен в {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"❌ Self-ping failed: {e}")
        time.sleep(240)  # 4 минуты

threading.Thread(target=keep_alive, daemon=True).start()

# ========== КОМАНДА /start ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # Сохраняем пользователя в базу
    try:
        c.execute('''INSERT OR IGNORE INTO users 
                     (user_id, username, first_name, last_name) 
                     VALUES (?, ?, ?, ?)''',
                  (user_id, username, first_name, last_name))
        conn.commit()
        print(f"✅ Новый пользователь: {first_name} (@{username})")
    except Exception as e:
        print(f"❌ Ошибка сохранения пользователя: {e}")
    
    welcome_text = (
        "💃 **Добро пожаловать в РИТМ!** 🕺\n\n"
        "📱 **Наше мобильное приложение:**\n"
        "• Просмотр расписания\n"
        "• Клипы с танцами\n"
        "• Профиль\n\n"
        "🤖 **Что умеет этот бот:**\n"
        "• Присылать уведомления о обновлениях приложения\n\n"
        "⬇️ **Нажмите кнопку ниже чтобы открыть приложение**"
    )
    
    markup = telebot.types.InlineKeyboardMarkup()
    app_button = telebot.types.InlineKeyboardButton(
        "📱 Войти в РИТМ", 
        url="https://niksiks23.github.io/pro-tancy-app/"  # ← ЗАМЕНИТЕ
    )
    markup.add(app_button)
    
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=markup
    )

# ========== КОМАНДА /broadcast (ТОЛЬКО ДЛЯ АДМИНА) ==========
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
        return
    
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
        f"❌ **Ошибок:** {failed}"
    )
    
    if failed_users:
        final_text += f"\n\n❌ **Не получили:** {len(failed_users)} пользователей"
    
    try:
        bot.edit_message_text(
            final_text,
            admin_id,
            status_msg.message_id,
            parse_mode='Markdown'
        )
    except:
        bot.send_message(admin_id, final_text, parse_mode='Markdown')

# ========== КОМАНДА /stats (ТОЛЬКО ДЛЯ АДМИНА) ==========
@bot.message_handler(commands=['stats'])
def show_stats(message):
    user_id = message.chat.id
    
    # Проверяем, админ ли
    if user_id not in ADMIN_IDS:
        bot.send_message(user_id, "⛔ У вас нет прав администратора")
        return
    
    # Общая статистика
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    # Статистика за сегодня
    today_start = datetime.now().strftime('%Y-%m-%d 00:00:00')
    c.execute("SELECT COUNT(*) FROM users WHERE joined_date >= ?", (today_start,))
    today_users = c.fetchone()[0]
    
    # Статистика за неделю
    week_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("SELECT COUNT(*) FROM users WHERE joined_date >= ?", (week_start,))
    week_users = c.fetchone()[0]
    
    # Последние 10 пользователей
    c.execute("SELECT username, first_name, joined_date FROM users ORDER BY joined_date DESC LIMIT 10")
    recent = c.fetchall()
    
    # Формируем текст статистики
    stats_text = (
        f"📊 **СТАТИСТИКА БОТА**\n\n"
        f"👥 **Всего пользователей:** {total_users}\n"
        f"📅 **За сегодня:** {today_users}\n"
        f"📆 **За неделю:** {week_users}\n\n"
        f"**Последние 10:**\n"
    )
    
    for username, first_name, joined_date in recent:
        name = first_name or "Без имени"
        user_tag = f"@{username}" if username else "нет юзернейма"
        date = joined_date.split()[0] if joined_date else "неизвестно"
        stats_text += f"• {name} ({user_tag}) - {date}\n"
    
    bot.send_message(user_id, stats_text, parse_mode='Markdown')

# ========== ЗАЩИТА ОТ ДВОЙНОГО ЗАПУСКА ==========
def cleanup():
    print("🔄 Останавливаю бота...")
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("=" * 50)
    print("🤖 РИТМ Бот запущен!")
    print("=" * 50)
    print(f"👤 Админ ID: {ADMIN_IDS[0]}")
    print("=" * 50)
    
    # Запускаем Flask в отдельном потоке
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Бесконечный цикл с автоперезапуском бота
    while True:
        try:
            print("✅ Бот слушает...")
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Перезапуск через 5 секунд...")
            time.sleep(5)
            continue
