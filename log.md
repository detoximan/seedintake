# Журнал событий (log.md)

> Хронологический append-only журнал проекта по спецификации **LLM Wiki** ([3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md)).  
> Каждая запись начинается с префикса: `## [YYYY-MM-DD] <категория> | <Заголовок>`  
> Просмотр последних записей: `grep "^## \[" log.md | tail -10`

---

## [2026-09-07] architecture | Внедрение LLM Wiki: index.md, agents/ knowledge base и стандартизация log.md

- **Контекст:** Приведение проекта в соответствие с концепцией Andrej Karpathy LLM Wiki (`3_karpathy-idea.md`). Систематизация вспомогательных скриптов, базы знаний агента и структуры документации.
- **Что сделано:**
  1. Создан корневой навигационный хаб [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md), каталогизирующий все вспомогательные скрипты `services/seed_pipeline/` (`apply_bilingual_sync.py`, `audit_translations.py`, `restore_sheet_links.py` и др.), команды CLI и уровни данных.
  2. Систематизирована папка [agents/](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents):
     - Добавлен [agents/README.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/README.md) — обзор базы знаний.
     - Оформлен [agents/carousel_translation_guideline.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/carousel_translation_guideline.md) — регламент по-слайдового перевода 1-в-1 без внешних API.
     - Оформлен [agents/cookies_management.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/cookies_management.md) — руководство по cookies для Instagram, TikTok, Facebook.
     - Оформлен [agents/troubleshooting.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/troubleshooting.md) — решение типовых проблем (дубли, кэш, Google Workspace).
     - Сохранен и связан [agents/prompt_video_ocr_hybrid.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/prompt_video_ocr_hybrid.md) — ТЗ гибридного OCR + Whisper.
  3. `log.md` приведен к стандарту Karpathy с поддержкой парсинга через `grep "^## \["`. Включена история ключевых сессий репозитория.
  4. Обновлен [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) со ссылками на `index.md`, `log.md` и базу знаний.

---

## [2026-09-07] audit & repair | Аудит переводов каруселей, по-слайдовый перевод 15 постов и синхронизация

- **Контекст:** Выявлена проблема потери слайдов и обрезки переводов в многостраничных Instagram-каруселях после вызова сторонних API перевода.
- **Что сделано:**
  1. Разработан скрипт аудита [services/seed_pipeline/audit_translations.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/audit_translations.py).
  2. Разработан скрипт атомарной синхронизации [services/seed_pipeline/apply_bilingual_sync.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/apply_bilingual_sync.py), синхронизирующий `full`, `slim` и Google Sheets.
  3. Проведен ручной по-слайдовый перевод 15 поврежденных англоязычных каруселей силами LLM (без внешних API), соблюдая соответствие `[photo.jpg]: текст` 1-в-1.
  4. Полный повторный аудит подтвердил 0 дефектов и 0 рассинхронов.
  5. Внесены жесткие запреты в [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) на использование Groq/внешних API для перевода текстов.

---

## [2026-08-14] maintenance | Массовая транскрибация, актуализация очереди и восстановление ссылок

- **Контекст:** Аудит репозитория, подтяжка 78 новых ссылок, устранение сбоев гиперссылок в Google Sheets.
- **Что сделано:**
  1. Создан и применен [services/seed_pipeline/restore_sheet_links.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/restore_sheet_links.py) для восстановления формул `=HYPERLINK(...)` в колонке A.
  2. Запущена последовательная обработка очереди через `link-worker process --limit 5 --live-google`.
  3. Проведен аудит контента и синхронизация статусов очереди. Подробности зафиксированы в [2026-08-14-worklog.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/2026-08-14-worklog.md).

---

## [2026-07-25] maintenance | Рефакторинг Link Worker: переход на модульную архитектуру роутера

- **Контекст:** Перевод `link_worker` с монолитного `UniversalMediaProcessor` на модульную архитектуру `URL Router + Specialized Workers`.
- **Что сделано:**
  1. Разделены процессоры по платформам (`instagram.py`, `tiktok.py`, `youtube.py`, `web.py`).
  2. Устранены блокировки Instagram через обязательное использование cookies и rate limiting.
  3. Подробный план и логи зафиксированы в [2026-07-25-workplan.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/2026-07-25-workplan.md) и [2026-07-25-worklog.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/2026-07-25-worklog.md).

---

## [2026-07-21] deploy | Миграция Telegram-бота SeedIntake в Cloud Run (europe-west4 Amsterdam)

- **Контекст:** Перенос продакшн-сервиса бота из региона US в Европу (Amsterdam) для минимизации задержек и стабильного вебхука.
- **Что сделано:**
  1. Cloud Run сервис: `seedintake-telegram-bot` развернут в регионе `europe-west4`.
  2. Ревизия `seedintake-telegram-bot-00002-zjx` получила 100% трафика.
  3. URL: `https://seedintake-telegram-bot-v7om675z7q-ez.a.run.app`.
  4. Telegram webhook успешно переключен, `pending_updates: 0`.
  5. Секреты перенесены в Secret Manager. Тесты: seed_pipeline 34/34, telegram_intake_bot 52/52.

---

## [2026-07-12] session | Отладка Instagram Reels (001-007) и исправление путей очереди Inbox

- **Контекст:** 7 ссылок Instagram Reels за 12 июля 2026 получили статус `processed`, но файлы `slim`/`full` не создались из-за зашитого старого пути `1inbox/seeds/`.
- **Что сделано:**
  1. Исправлены пути в коде:
     - `services/seed_pipeline/src/seed_pipeline/intake/markdown_writer.py`
     - `services/seed_pipeline/src/seed_pipeline/intake/dry_run.py`
     - `services/seed_pipeline/src/seed_pipeline/link_worker/queue.py`
  2. Очищен реестр дубликатов `runtime/tmp/seed_pipeline/processed_messages.json` за 12 июля.
  3. Настроена поддержка `process-fallback` с браузерными cookies для преодоления пустых ответов Instagram.
