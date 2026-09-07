# Индекс проекта SeedIntake (index.md)

> Предметный каталог, навигационный хаб и руководство по решению проблем проекта по методологии **LLM Wiki** ([3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md)).  
> Здесь собраны ссылки на все сервисы, рабочие скрипты, правила запуска, структура данных и инструкции по устранению неисправностей.

---

## 🧭 Ключевые документы системы

| Документ | Роль по Karpathy | Назначение |
|---|---|---|
| [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) | **The Schema** | **Главный регламент работы LLM-агента.** Пошаговый цикл обработки ссылок, правила по-слайдового перевода каруселей, работа с cookies, валидация контента и запреты. |
| [log.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/log.md) | **The Log** | **Хронологический append-only журнал сессий.** Все инжесты, чистки дублей, миграции и аудиты в формате Карпаты. |
| [3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md) | **Architecture** | Концептуальная основа: трехуровневая архитектура персональной базы знаний (Raw Sources → Wiki → Schema). |
| [services/telegram_intake_bot/DEPLOY.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/telegram_intake_bot/DEPLOY.md) | **Bot Operations** | Параметры Cloud Run, секреты Secret Manager, переменные окружения и команды управления Telegram Intake Bot. |

---

## ⚙️ Основной пайплайн: CLI link-worker

Базовые команды для управления очередью и боевой обработки входящих ссылок:

```bash
# 1. Обязательное обновление загрузчиков перед запуском
pip3 install -U yt-dlp gallery-dl

# 2. Просмотр сводки очереди новых ссылок
PYTHONPATH=services/seed_pipeline/src python3 -m seed_pipeline.cli link-worker list --status new --summary

# 3. Обработка одной конкретной ссылки (боевой режим с записью в Google Sheets)
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file ../../Inbox/2026/links/<seed_id>-link.md --live-google

# 4. Обработка пакета ссылок платформы
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --platform instagram_reels --limit 10 --live-google

# 5. Fallback-обработка (с cookies для ссылок со статусом pending_cookies)
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process-fallback --live-google
```

---

## 🛠️ Каталог рабочих скриптов (`services/seed_pipeline/`)

### 🟢 Боевые регулярные инструменты обслуживания базы

| Скрипт | Назначение | Команда запуска |
|---|---|---|
| [apply_bilingual_sync.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/apply_bilingual_sync.py) | **Атомарная синхронизация перевода.** Проверяет перевод на сохранность слайдов карусели и синхронно обновляет `slim`, `full` и Google Sheets (`E{row}`). | `python3 services/seed_pipeline/apply_bilingual_sync.py <seed_id> --translation-file <path>`<br>`python3 services/seed_pipeline/apply_bilingual_sync.py <seed_id> --sync-existing` |
| [audit_translations.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/audit_translations.py) | **Комплексный аудит переводов.** Сканирует Google Sheets и локальные файлы: находит непереведенные англоязычные посты (Группа А), обрезанные карусели (Группа Б) и рассинхрон (Группа В). | `python3 services/seed_pipeline/audit_translations.py` |
| [restore_sheet_links.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/restore_sheet_links.py) | **Восстановление ссылок в таблице.** Проверяет Колонку A в Google Sheets и восстанавливает формулы `=HYPERLINK(...)` на GitHub full-файлы при их слете. | `python3 services/seed_pipeline/restore_sheet_links.py` |
| [explore_sheet.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/explore_sheet.py) | **Разведка и статистика таблицы.** Анализирует язык контента (соотношение латиницы и кириллицы без служебных маркеров) и находит подозрительные строки. | `python3 services/seed_pipeline/explore_sheet.py` |
| [create_magicmind_sheet.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/create_magicmind_sheet.py) | **Импорт спец-коллекции MagicMind.** Создает отдельный лист "Magic Mind" в Google Sheets и заполняет его данными из файла `MagicMind`. | `python3 services/seed_pipeline/create_magicmind_sheet.py` |
| [deploy.sh](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/telegram_intake_bot/deploy.sh) | **Сборка и выкатка бота.** Собирает контейнер через Google Cloud Build и деплоит в Cloud Run (`seedintake-telegram-bot`, Amsterdam). | `./services/telegram_intake_bot/deploy.sh` |

---

## 🚑 Решение типовых проблем (Troubleshooting Guide)

### 1. Ошибка авторизации / блокировка скачивания (Instagram / TikTok / Facebook)
- **Симптом:** yt-dlp падает с ошибкой `login required`, `private account`, либо выдает пустой контент.
- **Причина:** Устарели сессионные cookies в папке `.cookies/`.
- **Решение:**
  1. Экспортировать свежие cookies из браузера с активной авторизацией в соответствующий файл:
     - Instagram → `.cookies/instagram.txt`
     - Facebook → `.cookies/facebook.txt`
     - TikTok → `.cookies/tiktok.txt`
  2. Запрещено ставить статус `processed` или маскировать под «видео без содержания», если видео не скачалось из-за куков.
  3. Перевести проблемную ссылку в статус `status: pending_cookies` и запустить:
     ```bash
     cd services/seed_pipeline && PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process-fallback --live-google
     ```

### 2. Ошибка подключения к Google Sheets (`LiveGoogleWorkspaceConfigError`)
- **Симптом:** Пайплайн падает с сообщением: `Missing Google Workspace env vars: GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_SHEET_ID`.
- **Решение:**
  1. Убедиться, что в `services/seed_pipeline/.env` указаны:
     ```env
     GOOGLE_APPLICATION_CREDENTIALS=/путь/к/service-account.json
     GOOGLE_SHEET_ID=1pXN9...
     ```
  2. Проверить, что сервисному аккаунту выдан доступ `Editor` к Google Таблице.

### 3. Ошибка транскрибации Whisper STT (`GROQ_API_KEY`)
- **Симптом:** Ошибка при вызове Groq API или превышение квоты (rate limit).
- **Решение:**
  1. Проверить валидность `GROQ_API_KEY` в `services/seed_pipeline/.env`.
  2. **Помнить:** Groq используется **исключительно** для аудио-транскрибации (модель `whisper-large-v3-turbo`). Перевод текстов на русский выполняется силами агента без внешних API!

### 4. Видео без речи / визуальный смысл («Видео без содержания»)
- **Симптом:** Аудио-транскрибация вернула «нет», покадровый OCR текста на видео не обнаружил, но само видео доступно и скачано.
- **Решение:**
  1. Если контент невербальный (действие, танец, визуал как идея) — **не удалять файл!**
  2. Оформить пометку в `full` и `slim`:
     ```text
     Все методы извлечения контента применены (транскрибация аудио, покадровый OCR). В аудио контента нет, в тексте на экране контента нет. Видео без содержания.
     ```
  3. Установить `status: processed` и синхронизировать с Google Sheets.

### 5. Слет гиперссылок в Колонке A Google Sheets
- **Симптом:** В колонке ID пропали кликабельные ссылки на GitHub `*-f.md`.
- **Решение:**
  ```bash
  python3 services/seed_pipeline/restore_sheet_links.py
  ```

### 6. Сбой или рассинхрон перевода
- **Симптом:** `audit_translations.py` обнаружил расхождения между файлами на диске и Google Sheets (Группа В) или пропущенные слайды (Группа Б).
- **Решение:**
  1. Для каруселей проверить, что каждый слайд переведён строго 1-в-1: `[photo.jpg]: оригинал` → `[photo.jpg]: перевод`.
  2. Применить синхронизацию через `apply_bilingual_sync.py`:
     ```bash
     python3 services/seed_pipeline/apply_bilingual_sync.py <seed_id> --sync-existing
     ```

### 7. Диагностика и статус Telegram Intake Bot
- **Симптом:** Бот в Telegram не отвечает или не сохраняет ссылки.
- **Решение:**
  ```bash
  cd services/telegram_intake_bot
  PYTHONPATH=src python3 -m telegram_intake_bot.cli diagnose
  ```
  - Проверить URL сервиса Cloud Run: `https://seedintake-telegram-bot-v7om675z7q-ez.a.run.app/health`
  - Проверить логи сервиса: `gcloud beta run services logs read seedintake-telegram-bot --region europe-west4 --project detoximan2026`

---

## 🗂️ Структура данных и уровни знаний (Wiki Architecture)

1. **Сырые источники (Raw Sources):**
   - `Inbox/2026/links/` — неизменяемые `.md` файлы очередей с метаданными поступления (`*-link.md`).
   - `.cookies/` — файлы авторизованных сессий (`instagram.txt`, `facebook.txt`, `tiktok.txt`).
2. **Слой Wiki / База знаний (The Compounding Wiki):**
   - `Inbox/2026/full/` (`*-f.md`) — полные исходные материалы (транскрипты, сырой OCR, описания, полный русский перевод, метаданные).
   - `Inbox/2026/slim/` (`*-s.md`) — очищенный компактный слой для быстрого чтения и навигации в Obsidian.
   - [MagicMind](file:///Users/pavelmalyk/pm_developer/SeedIntake/MagicMind) — тематическая коллекция отобранных материалов.
   - Google Sheets — внешняя оперативная табличная проекция базы знаний для пользователя.
3. **Схема и правила (The Schema):**
   - [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) — единые правила работы агента, стандарты и инструкции.
   - [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md) — навигатор, каталог скриптов и руководство по устранению сбоев.
