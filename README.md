# SeedIntake

Входная точка для приёма и первичной обработки контент-семян (seeds).

## Что делает проект

1. **Telegram-бот** принимает текст, голос и ссылки
2. **Seed Pipeline** обрабатывает входящий материал:
   - Транскрибирует видео/аудио (YouTube Shorts, TikTok, Reels)
   - Создаёт Markdown-файлы (full и slim версии)
   - Записывает строку в Google Sheets реестр
3. Результат готов к дальнейшей обработке

## Структура

```
SeedIntake/
├── Inbox/              # Входящие сиды (по годам)
│   └── 2026/
│       ├── full/       # Полные версии сидов
│       ├── slim/       # Короткие версии (ссылки на full)
│       └── links/      # Очередь ссылок для обработки
├── services/
│   ├── telegram_intake_bot/   # Telegram-бот
│   └── seed_pipeline/         # Пайплайн обработки сидов
└── README.md
```

## Сервисы

### Telegram Intake Bot

Принимает сообщения из Telegram, маршрутизирует:
- `/seed` — записать сид
- Текст/голос — материал для сида
- Ссылка (YouTube, TikTok и т.д.) — в очередь links

### Seed Pipeline

- **Link Worker** — скачивает видео, транскрибирует через Groq (Whisper), создаёт сид
- **Intake** — создаёт full/slim Markdown, записывает в Google Sheets

## Переменные окружения

```
TELEGRAM_BOT_TOKEN=...         # Токен Telegram-бота
GROQ_API_KEY=...               # Ключ Groq для транскрибации
GITHUB_TOKEN=...               # Токен для записи в GitHub
GITHUB_REPOSITORY=...          # owner/repo
GOOGLE_APPLICATION_CREDENTIALS=...  # Путь к JSON сервисного аккаунта
GOOGLE_SHEET_ID=...            # ID Google Sheets реестра
```

## Локальный запуск

```bash
# Тесты seed_pipeline
cd services/seed_pipeline
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'

# Тесты telegram_intake_bot
cd services/telegram_intake_bot
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'

# Smoke-тест link worker
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli smoke --dry-run
```

## Деплой

Cloud Build → Docker → Cloud Run (webhook mode)

```bash
cd services/telegram_intake_bot
PYTHONPATH=src:../seed_pipeline/src python3 -m telegram_intake_bot.cli webhook
```
