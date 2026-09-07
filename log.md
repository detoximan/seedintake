# Журнал событий (log.md)

> Хронологический append-only журнал проекта по спецификации **LLM Wiki** ([3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md)).  
> Каждая запись начинается с префикса: `## [YYYY-MM-DD] <категория> | <Заголовок>`  
> Просмотр последних записей: `grep "^## \[" log.md | tail -10`

## [2026-09-07] cleanup | Удаление 7 архивных/разовых утилит и очистка index.md

- **Контекст:** Очистка кодовой базы от мёртвого кода и опасных архивных утилит с зашитыми номерами строк.
- **Что сделано:**
  1. Удалены 7 архивных скриптов:
     - `services/seed_pipeline/fix_translation_format.py` (зашитые строки таблицы)
     - `services/seed_pipeline/verify_translation.py` (зашитые строки таблицы)
     - `services/seed_pipeline/manual_translate_next10.py` (зашитые строки таблицы)
     - `services/seed_pipeline/clear_today_sheet.py` (зашитая дата 2026-07-12)
     - `services/seed_pipeline/apply_translation.py` (устаревший прототип)
     - `services/seed_pipeline/src/seed_pipeline/link_worker/sync_google_sheet.py` (старый черновик)
     - `services/seed_pipeline/src/seed_pipeline/link_worker/test_gsheet.py` (старый черновик)
  2. Обновлён [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md): каталог содержит исключительно актуальные боевые скрипты и расширенное руководство по устранению неполадок.
  3. Проведены тесты: 34/34 в `seed_pipeline`, 52/52 в `telegram_intake_bot` (все 86 тестов успешно пройдены).

---

## [2026-09-07] cleanup | Удаление дубликатов строк Google Sheets и чистка временных черновиков

- **Контекст:** Окончательная очистка репозитория и Google Sheets от дубликатов и временных списков по согласованию с пользователем.
- **Что сделано:**
  1. В Google Sheets удалены 5 строк-дубликатов (`2026-07-12-001`, `2026-07-12-002`, `2026-07-12-005`, `2026-08-06-001`, `2026-08-23-007`). Каждая запись сохранена ровно в одном актуальном экземпляре с полным текстом. В таблице 0 дубликатов (740 уникальных строк).
  2. Все файлы на диске (743 ссылки, включая визуальные материалы без речи с пометкой «Видео без содержания») сохранены в полной целостности.
  3. Удалены временные текстовые файлы-черновики: `file.atlinks`, `tiktok_failed.md`, `PROMPT_NEXT_CHAT.md`, `.new_queue.txt`.
  4. Обновлён [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md) (убрано упоминание удалённого промпта).

---

## [2026-09-07] maintenance | Изоляция деплоя Telegram-бота, закрытие бэклога и 100% готовность очереди

- **Контекст:** Реализация рабочего плана из PROMPT_NEXT_CHAT.md. Критическая ревизия очередей и изоляция сборки/деплоя бота.
- **Что сделано:**
  1. Полная изоляция сборки и деплоя Telegram Intake Bot: удалены корневые `Dockerfile` и `deploy.sh`, деплой перенесён в `services/telegram_intake_bot/deploy.sh` с интеграцией Cloud Build (`cloudbuild.yaml`). Обновлены `DEPLOY.md` и `README.md`.
  2. Проведён сквозной аудит очередей и бэклога:
     - 21 ссылка из `file.atlinks`: все 21 закрыты (20 успешно обработаны, 1 удалена как дубль).
     - 7 ссылок из `tiktok_failed.md`: все 7 успешно транскрибированы на русском языке.
     - Единственный сбойный сид `2026-08-19-005` переведён, синхронизирован с Google Sheets (`LiveGoogleWorkspace`), статус переведён в `processed`.
  3. Финальный аудит: `audit_translations.py` подтвердил 0 дефектов. Очередь `link-worker`: 743 из 743 ссылок обработаны, 0 `failed`, 0 `new`.

---

## [2026-09-07] architecture | Разделение вселенных Telegram Intake Bot и Seed Pipeline

- **Контекст:** Изоляция сервиса Telegram Intake Bot (приём входящих ссылок) от ядра обработки ссылок Seed Pipeline. Корневой `AGENTS.md` сфокусирован исключительно на пайплайне обработки контента.
- **Что сделано:**
  1. Из [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) полностью удалены специфичные для Cloud Run и Telegram-бота данные деплоя и секреты.
  2. Создан [services/telegram_intake_bot/DEPLOY.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/telegram_intake_bot/DEPLOY.md), инкапсулирующий все параметры инфраструктуры, секретов и деплоя бота.
  3. Сформирован подробный рабочий план в [PROMPT_NEXT_CHAT.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/PROMPT_NEXT_CHAT.md) с обязательным правилом ревизии на свежий контекст перед выполнением.

---

## [2026-09-07] cleanup | Консолидация AGENTS.md, удаление AGENTS.old.md и устаревших ворклогов

- **Контекст:** Анализ исторических файлов `worklog`/`workplan` и устаревшего `AGENTS.old.md`.
- **Что сделано:**
  1. Вся ценная техническая информация по деплою в Cloud Run, секретам и командам Telegram Intake Bot перенесена из `AGENTS.old.md` напрямую в [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md). Файл `AGENTS.old.md` удалён.
  2. Проанализированы выполненные планы и логи: `2026-07-25-worklog.md`, `2026-07-25-workplan.md`, `2026-08-14-worklog.md`, `2026-08-14-workplan.md`, `2026-09-07-workplan.md`. Все реализованные задачи удалены из корня репозитория.
  3. Все оставшиеся нереализованные задачи (21 ссылка из `file.atlinks`, 7 ссылок из `tiktok_failed.md`, осиротевшие link-файлы) упакованы в готовый рабочий промпт [PROMPT_NEXT_CHAT.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/PROMPT_NEXT_CHAT.md).

---

## [2026-09-07] architecture | Внедрение чистой LLM Wiki: создание index.md и стандартизация log.md

- **Контекст:** Приведение структуры проекта к канонической модели LLM Wiki Андрея Карпаты (`3_karpathy-idea.md`): Schema (`AGENTS.md`) + Catalog (`index.md`) + Timeline (`log.md`) + Data (`Inbox/`) + Code (`services/`). Устранена избыточная папка `agents/`.
- **Что сделано:**
  1. Создан корневой предметный каталог [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md), описывающий все вспомогательные скрипты `services/seed_pipeline/` (`apply_bilingual_sync.py`, `audit_translations.py`, `restore_sheet_links.py` и др.), команды запуска CLI и уровни данных.
  2. Удалена промежуточная папка `agents/` с дублирующими файлами; все правила работы, регламенты и инструкции консолидированы в едином документе-схеме [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md).
  3. `log.md` переведен в строгий хронологический append-only формат Карпаты с поддержкой быстрого парсинга заголовков через `grep "^## \[" log.md`.

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
