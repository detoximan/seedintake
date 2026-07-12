FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/services/telegram_intake_bot/src:/app/services/seed_pipeline/src

WORKDIR /app

COPY services/seed_pipeline /app/services/seed_pipeline
COPY services/telegram_intake_bot /app/services/telegram_intake_bot

RUN pip install --no-cache-dir /app/services/seed_pipeline /app/services/telegram_intake_bot

CMD ["python", "-m", "telegram_intake_bot.cli", "webhook"]
