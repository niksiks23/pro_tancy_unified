#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PRO ТАНЦЫ - Единое приложение
Один файл: и Telegram бот, и API для HTML
"""

import logging
import sqlite3
import asyncio
import threading
import time
import schedule
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# ================ КОНФИГУРАЦИЯ ================
BOT_TOKEN = "8548814750:AAFeFue2yX3BnYItewkjQi2kNaQGjhX65Uc"  # <--- ЗАМЕНИТЕ
ADMIN_IDS = [5276187604]  # <--- ЗАМЕНИТЕ НА СВОЙ TELEGRAM ID

# ================ РАСПИСАНИЕ ================
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
    7: []
}

WEEKDAYS = {
    1: 'Понедельник', 2: 'Вторник', 3: 'Среда', 4: 'Четверг',
    5: 'Пятница', 6: 'Суббота', 7: 'Воскресенье'
}

# ================ БАЗА ДАННЫХ ================
class Database:
    def __init__(self, db_path='pro_tancy.db'):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        conn = self.get_connection()
        c = conn.cursor()
        
        # Пользователи бота
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      telegram_id INTEGER UNIQUE,
                      name TEXT,
                      phone TEXT,
                      group_name TEXT,
                      notify_before INTEGER DEFAULT 30,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Отменённые тренировки (общие для HTML и бота)
        c.execute('''CREATE TABLE IF NOT EXISTS cancelled_trainings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      date TEXT,
                      training_key TEXT,
                      UNIQUE(date, training_key))''')
        
        # Логи уведомлений
        c.execute('''CREATE TABLE IF NOT EXISTS notification_log
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      training_date TEXT,
                      training_time TEXT,
                      training_name TEXT,
                      sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        conn.commit()
        conn.close()
        print("✅ База данных готова")
    
    # ===== Методы для работы с отменами =====
    def get_cancelled(self, date=None):
        conn = self.get_connection()
        c = conn.cursor()
        if date:
            c.execute("SELECT training_key FROM cancelled_trainings WHERE date = ?", (date,))
            return [row[0] for row in c.fetchall()]
        else:
            c.execute("SELECT date, training_key FROM cancelled_trainings")
            rows = c.fetchall()
            result = {}
            for date, key in rows:
                if date not in result:
                    result[date] = []
                result[date].append(key)
            conn.close()
            return result
    
    def toggle_cancelled(self, date, training_key, action):
        conn = self.get_connection()
        c = conn.cursor()
        if action == 'add':
            c.execute("INSERT OR IGNORE INTO cancelled_trainings (date, training_key) VALUES (?, ?)",
                     (date, training_key))
        else:
            c.execute("DELETE FROM cancelled_trainings WHERE date = ? AND training_key = ?",
                     (date, training_key))
        conn.commit()
        conn.close()
    
    # ===== Методы для пользователей =====
    def get_user(self, telegram_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = c.fetchone()
        conn.close()
        return user
    
    def save_user(self, telegram_id, name, phone, group_name, notify_before=30):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO users 
                     (telegram_id, name, phone, group_name, notify_before) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (telegram_id, name, phone, group_name, notify_before))
        conn.commit()
        conn.close()
    
    def get_users_by_group(self, group_name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE group_name = ?", (group_name,))
        users = c.fetchall()
        conn.close()
        return users
    
    def get_all_users(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        users = c.fetchall()
        conn.close()
        return users
    
    def get_group_stats(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT group_name, COUNT(*) as count 
            FROM users 
            WHERE group_name IS NOT NULL 
            GROUP BY group_name
        ''')
        stats = c.fetchall()
        conn.close()
        return stats
    
    def log_notification(self, user_id, training_date, training_time, training_name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO notification_log 
                     (user_id, training_date, training_time, training_name) 
                     VALUES (?, ?, ?, ?)''',
                  (user_id, training_date, training_time, training_name))
        conn.commit()
        conn.close()

# ================ FLASK API (для HTML) ================
app = Flask(__name__)
db = Database()  # ОДНА база данных для всего!

@app.route('/api/cancelled', methods=['GET'])
def api_get_cancelled():
    date = request.args.get('date')
    if date:
        return jsonify({'cancelled': db.get_cancelled(date)})
    else:
        return jsonify(db.get_cancelled())

@app.route('/api/cancelled', methods=['POST'])
def api_update_cancelled():
    data = request.json
    date = data.get('date')
    training_key = data.get('training_key')
    action = data.get('action')  # 'add' или 'remove'
    
    db.toggle_cancelled(date, training_key, action)
    return jsonify({'status': 'ok'})

@app.route('/api/sync/html', methods=['POST'])
def api_sync_from_html():
    """Полная синхронизация из HTML"""
    data = request.json
    cancelled = data.get('cancelled', {})
    
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM cancelled_trainings")
    for date, trainings in cancelled.items():
        for key in trainings:
            c.execute("INSERT INTO cancelled_trainings (date, training_key) VALUES (?, ?)",
                     (date, key))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'synced': sum(len(v) for v in cancelled.values())})

@app.route('/api/sync/bot', methods=['GET'])
def api_sync_to_html():
    """Отдать все отмены для HTML"""
    return jsonify(db.get_cancelled())

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Статистика для админки"""
    return jsonify({
        'users': len(db.get_all_users()),
        'by_group': [{'group': row[0], 'count': row[1]} for row in db.get_group_stats()]
    })

@app.route('/api/schedule', methods=['GET'])
def api_schedule():
    """Расписание на неделю"""
    return jsonify(WEEKLY_SCHEDULE)

# ================ ПЛАНИРОВЩИК УВЕДОМЛЕНИЙ ================
class NotificationScheduler:
    def __init__(self, bot_app):
        self.bot_app = bot_app
        self.db = db  # Та же база!
        self.running = True
    
    def start(self):
        thread = threading.Thread(target=self._run_scheduler, daemon=True)
        thread.start()
        print("✅ Планировщик запущен")
    
    def _run_scheduler(self):
        schedule.every(1).minutes.do(self.check_upcoming_trainings)
        while self.running:
            schedule.run_pending()
            time.sleep(30)
    
    def check_upcoming_trainings(self):
        now = datetime.now()
        today = now.strftime('%Y-%m-%d')
        current_time = now.strftime('%H:%M')
        
        users = self.db.get_all_users()
        
        for user in users:
            if not user[4]:  # если нет группы
                continue
            
            # Проверяем тренировки на сегодня
            day_of_week = now.isoweekday()
            trainings = WEEKLY_SCHEDULE.get(day_of_week, [])
            
            for training in trainings:
                if training['name'] != user[4]:  # не его группа
                    continue
                
                # Проверяем, не отменена ли
                training_key = f"{training['time']} {training['name']}"
                if training_key in self.db.get_cancelled(today):
                    continue
                
                # Вычисляем время отправки
                training_time = datetime.strptime(training['time'], '%H:%M')
                notify_time = training_time - timedelta(minutes=user[5])
                current = datetime.strptime(current_time, '%H:%M')
                
                if current.hour == notify_time.hour and current.minute == notify_time.minute:
                    asyncio.run_coroutine_threadsafe(
                        self.send_notification(user[1], training, user[5]),
                        self.bot_app.loop
                    )
    
    async def send_notification(self, telegram_id, training, minutes):
        try:
            message = (
                f"⏰ **Напоминание!**\n\n"
                f"Через {minutes} минут: **{training['name']}**\n"
                f"🕐 Время: {training['time']}\n\n"
                f"Ждём вас! 💃🕺"
            )
            await self.bot_app.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown'
            )
            print(f"✅ Уведомление отправлено {telegram_id}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

# ================ TELEGRAM БОТ ================
# Состояния для ConversationHandler
NAME, PHONE, GROUP, NOTIFY_TIME = range(4)

class ProTancyBot:
    def __init__(self, token):
        self.token = token
        self.db = db  # Та же база!
        self.application = None
        self.scheduler = None
    
    def setup(self):
        self.application = Application.builder().token(self.token).build()
        
        # Команды
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))
        self.application.add_handler(CommandHandler("mygroup", self.cmd_mygroup))
        self.application.add_handler(CommandHandler("schedule", self.cmd_schedule))
        
        # Регистрация
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.reg_start, pattern='^register$')],
            states={
                NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.reg_name)],
                PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.reg_phone)],
                GROUP: [CallbackQueryHandler(self.reg_group)],
                NOTIFY_TIME: [CallbackQueryHandler(self.reg_notify_time)]
            },
            fallbacks=[CommandHandler("cancel", self.cmd_cancel)]
        )
        self.application.add_handler(conv_handler)
        
        # Callback handlers
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        print("✅ Бот настроен")
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        db_user = self.db.get_user(user_id)
        
        if db_user:
            await update.message.reply_text(
                f"👋 С возвращением, {db_user[2]}!",
                reply_markup=self.main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                "🕺 Добро пожаловать в PRO ТАНЦЫ!\n\n"
                "Я буду напоминать о тренировках.",
                reply_markup=self.register_keyboard()
            )
    
    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Меню:", reply_markup=self.main_menu_keyboard())
    
    async def cmd_mygroup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        db_user = self.db.get_user(user_id)
        
        if not db_user:
            await update.message.reply_text("❌ Сначала зарегистрируйтесь!")
            return
        
        await update.message.reply_text(
            f"📅 Ваша группа: **{db_user[4]}**\n"
            f"⏰ Напоминания: за {db_user[5]} минут",
            parse_mode='Markdown'
        )
    
    async def cmd_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = "📅 **Расписание на неделю**\n\n"
        for day in range(1, 8):
            classes = WEEKLY_SCHEDULE.get(day, [])
            if classes:
                text += f"**{WEEKDAYS[day]}:**\n"
                for cls in classes:
                    text += f"  • {cls['time']} — {cls['name']}\n"
                text += "\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Отменено")
        return ConversationHandler.END
    
    def main_menu_keyboard(self):
        keyboard = [
            [InlineKeyboardButton("📅 Моё расписание", callback_data='my_schedule')],
            [InlineKeyboardButton("⚙️ Настройки", callback_data='settings')],
            [InlineKeyboardButton("🔄 Сменить группу", callback_data='change_group')]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def register_keyboard(self):
        keyboard = [[InlineKeyboardButton("📝 Зарегистрироваться", callback_data='register')]]
        return InlineKeyboardMarkup(keyboard)
    
    def groups_keyboard(self):
        all_groups = list(set([cls['name'] for day in WEEKLY_SCHEDULE.values() for cls in day]))
        keyboard = []
        row = []
        for group in all_groups:
            row.append(InlineKeyboardButton(group, callback_data=f'group_{group}'))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        return InlineKeyboardMarkup(keyboard)
    
    def notify_times_keyboard(self):
        times = [15, 30, 45, 60, 90, 120]
        keyboard = []
        row = []
        for t in times:
            row.append(InlineKeyboardButton(f"{t} мин", callback_data=f'time_{t}'))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        return InlineKeyboardMarkup(keyboard)
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'my_schedule':
            user_id = query.from_user.id
            db_user = self.db.get_user(user_id)
            if db_user:
                await query.edit_message_text(
                    f"📅 Ваши тренировки:\n\n{self.get_user_schedule(db_user[4])}",
                    reply_markup=self.main_menu_keyboard()
                )
        elif data == 'settings':
            user_id = query.from_user.id
            db_user = self.db.get_user(user_id)
            if db_user:
                keyboard = [
                    [InlineKeyboardButton("⏰ Время напоминания", callback_data='change_notify')],
                    [InlineKeyboardButton("👥 Сменить группу", callback_data='change_group')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='back')]
                ]
                await query.edit_message_text(
                    f"⚙️ Настройки\n\n"
                    f"Группа: {db_user[4]}\n"
                    f"Напоминания: за {db_user[5]} мин",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        elif data == 'back':
            await query.edit_message_text("Меню:", reply_markup=self.main_menu_keyboard())
    
    def get_user_schedule(self, group_name):
        result = ""
        for day, classes in WEEKLY_SCHEDULE.items():
            for cls in classes:
                if cls['name'] == group_name:
                    result += f"• {WEEKDAYS[day]} в {cls['time']}\n"
        return result or "Нет тренировок"
    
    # Регистрация
    async def reg_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Как вас зовут?")
        return NAME
    
    async def reg_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['name'] = update.message.text
        await update.message.reply_text("📞 Ваш телефон:")
        return PHONE
    
    async def reg_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['phone'] = update.message.text
        await update.message.reply_text("Выберите группу:", reply_markup=self.groups_keyboard())
        return GROUP
    
    async def reg_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        group = query.data.replace('group_', '')
        context.user_data['group'] = group
        await query.edit_message_text(
            f"✅ Группа: {group}\n\nЗа сколько минут напоминать?",
            reply_markup=self.notify_times_keyboard()
        )
        return NOTIFY_TIME
    
    async def reg_notify_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        minutes = int(query.data.replace('time_', ''))
        user_id = query.from_user.id
        
        self.db.save_user(
            user_id,
            context.user_data['name'],
            context.user_data['phone'],
            context.user_data['group'],
            minutes
        )
        
        await query.edit_message_text(
            f"✅ Регистрация завершена!\n\n"
            f"👤 {context.user_data['name']}\n"
            f"👥 {context.user_data['group']}\n"
            f"⏰ за {minutes} мин",
            reply_markup=self.main_menu_keyboard()
        )
        return ConversationHandler.END
    
    def run(self):
        self.setup()
        self.scheduler = NotificationScheduler(self.application)
        self.scheduler.start()
        print("🚀 Бот запущен!")
        self.application.run_polling()

# ================ ЗАПУСК ВСЕГО В ОДНОМ ================
def run_flask():
    print("🌐 API сервер запущен на http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def run_bot():
    bot = ProTancyBot(BOT_TOKEN)
    bot.run()

if __name__ == '__main__':
    print("=" * 50)
    print("🔥 PRO ТАНЦЫ - ЕДИНОЕ ПРИЛОЖЕНИЕ")
    print("=" * 50)
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота (он блокирующий)
    run_bot()