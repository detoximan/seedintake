# Деплой Telegram Intake Bot

Сервис приёма входящих семян и ссылок из Telegram в очередь `Inbox/YYYY/links/`.

## Параметры инфраструктуры Cloud Run

| Параметр | Значение |
|---|---|
| Сервис Cloud Run | `seedintake-telegram-bot` |
| Регион | `europe-west4` (Amsterdam, Netherlands) |
| GCP Проект | `detoximan2026` |
| URL сервиса | `https://seedintake-telegram-bot-v7om675z7q-ez.a.run.app` |
| Telegram-бот | `@detoximan_intake_bot` |
| GitHub репозиторий | `detoximan/seedintake` (ветка `main`) |
| Деплой-скрипт | `./deploy.sh` в корне репозитория |
| Связанный сервис (НЕ трогать!) | `micro-razbor-bot` (в том же проекте `detoximan2026`, `europe-west4`) |

## Секреты (через GCP Secret Manager)

- `telegram-bot-token` → `TELEGRAM_BOT_TOKEN`
- `github-token` → `GITHUB_TOKEN`
- `telegram-webhook-secret` → `TELEGRAM_WEBHOOK_SECRET`
- `google-sheet-id` → `GOOGLE_SHEET_ID`
- `google-service-account-json` → `/secrets/google/service-account.json`

## Команды управления ботом

```bash
cd services/telegram_intake_bot

# Диагностика вебхука и токена
PYTHONPATH=src python3 -m telegram_intake_bot.cli diagnose

# Локальный polling (при тестировании)
PYTHONPATH=src python3 -m telegram_intake_bot.cli polling

# Webhook режим (для Cloud Run контейнера)
PYTHONPATH=src:../seed_pipeline/src python3 -m telegram_intake_bot.cli webhook
```

## Деплой в Cloud Run

```bash
# Из корня репозитория:
./deploy.sh
```
