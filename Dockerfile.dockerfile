FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Устанавливаем переменную для автоматического перезапуска
ENV PYTHONUNBUFFERED=1

# Запускаем бота с автоматическим перезапуском
CMD ["sh", "-c", "while true; do python bot.py; echo 'Бот упал, перезапуск через 5 секунд...'; sleep 5; done"]