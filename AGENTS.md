# SeedIntake — AGENTS.md

Главный файл-инструкция проекта. Любой LLM-агент или человек, зашедший в проект, начинает здесь.

## Что это за проект

SeedIntake — входная точка для приёма и первичной обработки контент-семян (seeds). Семя — это единица контента: идея, мысль, транскрипция ролика, заметка. Всё проходит через Telegram-бот → обрабатывается → сохраняется в структурированном виде.

## Архитектура (три слоя по Карпати)

1. **Raw Sources** — входящие материалы (ссылки, голос, текст из Telegram)
2. **Wiki (Seeds)** — обработанные, связанные markdown-файлы в `Inbox/`
3. **Schema** — этот файл (AGENTS.md) + README.md

## Структура проекта

```
SeedIntake/
├── AGENTS.md              ← ТЫ ЗДЕСЬ. Главный файл-инструкция
├── README.md              ← Техническое описание
├── 3_karpathy-idea.md     ← Идея LLM Wiki (паттерн организации знаний)
├── deploy.sh              ← Скрипт деплоя на Cloud Run
├── Dockerfile             ← Для деплоя через gcloud --source
├── .env.example           ← Шаблон переменных окружения
│
├── Inbox/                 ← Все сиды, по годам
│   └── 2026/
│       ├── full/          ← Полные версии (транскрипция + комментарий + метаданные)
│       ├── slim/          ← Короткие версии (ссылки на full + краткое содержание)
│       └── links/         ← Очередь ссылок для обработки (new → processed/failed)
│
└── services/
    ├── telegram_intake_bot/   ← Telegram-бот (приём сообщений)
    └── seed_pipeline/         ← Пайплайн обработки (ссылки → транскрипция → сид)
```

## Деплой

| Параметр | Значение |
|----------|----------|
| Сервис Cloud Run | `detoximan-telegram-intake-bot` |
| Регион | `us-central1` (Iowa) |
| GCP Проект | `detoximan2026` |
| URL | `https://detoximan-telegram-intake-bot-579627119014.us-central1.run.app` |
| Бот Telegram | `@detoximan_intake_bot` |
| GitHub репо | `detoximan/seedintake` |
| Google Sheet реестр | есть, ID в секртах |

**Секреты (через Secret Manager):**
- `TELEGRAM_BOT_TOKEN` — токен бота
- `GITHUB_TOKEN` — запись сидов в GitHub
- `GROQ_API_KEY` — транскрибация (Whisper)

**Не-секретные env:**
- `SEED_MARKDOWN_STORAGE=github`
- `SEED_GOOGLE_WORKSPACE=live`
- `GITHUB_REPOSITORY=detoximan/seedintake`
- `GITHUB_BRANCH=main`

**Как задеплоить:**
```bash
cd SeedIntake
./deploy.sh
```

**Связанный сервис (не трогать!):**
- `micro-razbor-bot` — живёт в `europe-west4` (Амстердам), тот же проект `detoximan2026`

## Жизненный цикл сида

```
Ссылка/текст/голос из Telegram
        ↓
  Telegram Intake Bot (router.py)
        ↓
  ┌─ Ссылка? → запись в Inbox/2026/links/ → Link Worker скачивает → транскрибация → сид
  ├─ Текст?  → сразу в Seed Pipeline → сид
  └─ Голос?  → Groq STT → текст → Seed Pipeline → сид
        ↓
  Создаются два файла:
  ├── Inbox/2026/full/2026-MM-DD-NNN-f.md  (полная версия)
  └── Inbox/2026/slim/2026-MM-DD-NNN-s.md  (короткая, ссылается на full)
        ↓
  Строка в Google Sheets реестре (ID, ссылка на full, комментарий)
```

## Навигация между сидами (для Obsidian)

- **Slim → Full:** в slim-файле в первой строке markdown-ссылка на full
- **Full → Slim:** в секции `# Оригинал` ссылка на slim
- **Full → Источник:** в секции `# Ссылка на исходный материал` прямая URL на ролик/пост
- **Google Sheets → Full:** в реестре HYPERLINK на full-файл в GitHub

## Команды для LLM-агента

### Link Worker (обработка ссылок)

```bash
cd SeedIntake/services/seed_pipeline

# Статистика
git pull && PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status new --summary

# Обработка всех новых
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --limit 100 --live-google

# Обработка конкретной ссылки
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file <путь> --live-google

# Проблемные (с cookies)
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process-fallback --live-google

# Ошибки
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status failed

# Сброс ошибки: в файле сменить status: failed → status: new
```

### Telegram Intake Bot

```bash
cd SeedIntake/services/telegram_intake_bot

# Локальный polling
set -a && source .env && set +a
PYTHONPATH=src python3 -m telegram_intake_bot.cli polling

# Webhook (Cloud Run)
PYTHONPATH=src:../seed_pipeline/src python3 -m telegram_intake_bot.cli webhook
```

### Диагностика

```bash
cd SeedIntake/services/telegram_intake_bot
PYTHONPATH=src python3 -m telegram_intake_bot.cli diagnose
```

## Важные файлы seed_pipeline

| Файл | Что делает |
|------|------------|
| `link_worker/processors.py` | Главный процессор: скачивание + транскрибация |
| `link_worker/worker.py` | Оркестратор воркера |
| `link_worker/ytdlp.py` | Скачивание через yt-dlp |
| `link_worker/jina.py` | Извлечение текста через Jina |
| `link_worker/queue.py` | Работа с очередью ссылок |
| `intake/markdown_writer.py` | Создание full/slim markdown |
| `intake/github_storage.py` | Запись в GitHub через API |
| `integrations/google_workspace_live.py` | Запись в Google Sheets |
| `schemas/models.py` | Все датаклассы проекта |

## Важные файлы telegram_intake_bot

| Файл | Что делает |
|------|------------|
| `router.py` | Маршрутизация сообщений (текст/голос/ссылка) |
| `link_queue_writer.py` | Запись ссылок в очередь |
| `transcription.py` | Транскрибация голоса/видео |
| `webhook.py` | HTTP webhook для Cloud Run |
| `runtime.py` | Рантайм бота |
| `flows/seed_intake.py` | Флоу приёма сидов |

## Переменные окружения

| Переменная | Описание | Секрет? |
|------------|----------|--------|
| `TELEGRAM_BOT_TOKEN` | Токен бота | Да |
| `GITHUB_TOKEN` | Токен для записи в GitHub | Да |
| `GROQ_API_KEY` | Ключ Groq STT | Да |
| `GOOGLE_APPLICATION_CREDENTIALS` | Путь к JSON сервисного аккаунта | Да |
| `GOOGLE_SHEET_ID` | ID таблицы реестра | Да |
| `GROQ_STT_MODEL` | Модель транскрибации | Нет |
| `GROQ_STT_LANGUAGE` | Язык (ru) | Нет |
| `SEED_MARKDOWN_STORAGE` | github/local | Нет |
| `SEED_GOOGLE_WORKSPACE` | live/mock | Нет |
| `GITHUB_REPOSITORY` | detoximan/seedintake | Нет |
| `GITHUB_BRANCH` | main | Нет |

## TODO (что предстоит)

- [ ] Обновить `GITHUB_REPOSITORY` в Cloud Run на `detoximan/seedintake`
- [ ] Удалить task-зависимости из telegram_intake_bot (task_intake_writer, flows/task_intake.py)
- [ ] Нормализовать `processors.py` (36KB, разбить на модули)
- [ ] Добавить логирование/link-back из slim в full (Obsidian совместимость)
- [ ] Настроить Secret Manager для нового репо
- [ ] Удалить сиды и сервисы из detoximan (после проверки)

## Принципы

- **Не трогать микроразбор** — это отдельный сервис, отдельный бот
- **Секреты только через Secret Manager** — не в .env, не в коде
- **Dry-run по умолчанию** — `--live-google` только когда явно нужно
- **Один бот** — `@detoximan_intake_bot`, не создаём второго
- **Markdown-first** — всё хранится в .md, связывается через ссылки
