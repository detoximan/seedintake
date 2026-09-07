# Рабочий план для следующей сессии (PROMPT_NEXT_CHAT.md)

> Очередь ссылок полностью обработана. Все упавшие ссылки закрыты, переводы синхронизированы, скрипты сборки и деплоя изолированы внутри `services/telegram_intake_bot/`.

---

## 🏛️ Архитектурная парадигма: Две независимые вселенные

1. **Вселенная 1: Telegram Intake Bot (`services/telegram_intake_bot/`)**
   - Приём ссылок из Telegram и запись в `Inbox/YYYY/links/`.
   - Деплой: `./services/telegram_intake_bot/deploy.sh` (Cloud Build + Cloud Run).
   - Документация: [services/telegram_intake_bot/DEPLOY.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/telegram_intake_bot/DEPLOY.md).

2. **Вселенная 2: Seed Pipeline (`services/seed_pipeline/` + `Inbox/`)**
   - Скачивание, транскрибация, покадровый OCR при отсутствии аудио, перевод и синхронизация в Google Sheets.
   - Схема и регламент: [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md).

---

## 📋 Инструкция для следующей сессии при поступлении новых ссылок

1. **Подтянуть изменения:**
   ```bash
   git pull
   ```
2. **Проверить очередь:**
   ```bash
   PYTHONPATH=services/seed_pipeline/src python3 -m seed_pipeline.cli link-worker list --status new --summary
   ```
3. **Обработать новые ссылки строго по одной:**
   ```bash
   cd services/seed_pipeline
   PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file ../../Inbox/2026/links/<seed_id>-link.md --live-google
   ```
4. **Перевести силами агента и синхронизировать:**
   ```bash
   python3 services/seed_pipeline/apply_bilingual_sync.py <seed_id> --translation-file <path>
   ```
5. **Валидация:**
   ```bash
   python3 services/seed_pipeline/audit_translations.py
   ```
