# Рабочий план и промпт для следующей сессии (PROMPT_NEXT_CHAT.md)

> **КРИТИЧЕСКАЯ ИНСТРУКЦИЯ ДЛЯ НОВОГО ЧАТА (ЧИТАТЬ В ПЕРВУЮ ОЧЕРЕДЬ):**  
> При входе в новый чат с чистым контекстом **ЗАПРЕЩЕНО слепо и механически приступать к выполнению пунктов ниже**.  
> Сначала:
> 1. Полностью прочитай [3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md), [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) и [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md).
> 2. Критически перепроверь этот план на свежую голову: выяви неточности, лишние действия или скрытые противоречия.
> 3. Переработай и сформируй для себя актуализированный, выверенный план действий.
> 4. Только после этого последовательно приступай к реализации.

---

## 🏛️ Архитектурная парадигма: Две независимые вселенные (Проект в проекте)

В проекте сосуществуют две логически связанные, но функционально изолированные части:

1. **Вселенная 1: Telegram Intake Bot (`services/telegram_intake_bot/`)**
   - **Единственная задача:** получить сообщение/ссылку из Telegram от пользователя и записать входящий `.md` файл в очередь `Inbox/YYYY/links/`. Всё.
   - **Изоляция:** Сервис деплоится в Google Cloud Run. Всё, что касается Cloud Run, Docker, деплоя, секретов GCP Secret Manager, тестов вебхука — живёт **исключительно** внутри `services/telegram_intake_bot/`.
   - Корневой `AGENTS.md` **не должен** содержать деталей деплоя бота в Cloud Run.

2. **Вселенная 2: Seed Pipeline (`services/seed_pipeline/` + `Inbox/`)**
   - **Задача:** взять ссылку из `Inbox/YYYY/links/`, скачать медиа с cookies, извлечь контент (Whisper STT / покадровый OCR при отсутствии голоса), верифицировать, перевести на русский силами агента и синхронно записать в `full`, `slim` и Google Sheets.
   - Корневой **`AGENTS.md` (The Schema)** всецело посвящён именно этой вселенной.

---

## 📋 План задач для новой сессии

### Задача 1: Завершить изоляцию деплоя Telegram Intake Bot
- Проверить наличие в корне репозитория файлов деплоя (`deploy.sh`, `Dockerfile`).
- Перенести логику сборки и деплоя внутрь `services/telegram_intake_bot/` (или адаптировать корневые скрипты так, чтобы корень не загромождался спецификой бота).
- Убедиться, что [services/telegram_intake_bot/DEPLOY.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/telegram_intake_bot/DEPLOY.md) содержит полную инструкцию по выкатке бота.

### Задача 2: Обработка 21 живой упавшей ссылки из `file.atlinks`
- В файле `file.atlinks` собраны 21 подтверждённо живые ссылки (11 Reels, 5 постов Instagram, 3 TikTok, 1 Threads, 1 web-ссылка).
- **Проверка cookies:** Убедиться в актуальности `.cookies/instagram.txt` и `.cookies/tiktok.txt` перед запуском. При ошибке авторизации — сразу запросить cookies у пользователя.
- **Последовательная обработка:** строго по 1 ссылке (без параллелизма и пакетов):
  ```bash
  PYTHONPATH=services/seed_pipeline/src python3 -m seed_pipeline.cli link-worker process-fallback --file Inbox/2026/links/<seed_id>-link.md --live-google
  ```
- **По-слайдовый перевод каруселей:** Для каруселей делать перевод 1-в-1 по слайдам `[photo.jpg]: ...` силами агента (без сторонних API) и применять через:
  ```bash
  python3 services/seed_pipeline/apply_bilingual_sync.py <seed_id> --translation-file <path>
  ```

### Задача 3: Проверка 7 упавших ссылок TikTok из `tiktok_failed.md`
- Проверить ссылки из `tiktok_failed.md` через yt-dlp / gallery-dl с cookies.
- Если контент живой — обработать и перевести.
- Если контент удалён авторами — актуализировать `tiktok_failed.md`.

### Задача 4: Аудит и устранение осиротевших link-файлов
- Проверить исторические битые ссылки из логов: `2026-05-03-019/021/024` и `2026-05-05-039..045/053`.
- Если это пустые дубли без записей в Google Sheets — удалить согласно разделу «Дубли ссылок» в `AGENTS.md`.

### Задача 5: Финальная валидация и коммит
1. Запустить скрипт аудита:
   ```bash
   python3 services/seed_pipeline/audit_translations.py
   ```
2. Зафиксировать результат в [log.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/log.md) в формате `## [YYYY-MM-DD] ...`.
3. Закоммитить и запушить в GitHub.
