# Промпт для следующей рабочей сессии

Привет! Мы продолжаем работу над проектом **SeedIntake**.
Перед началом обязательно изучи [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) и [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md). Все правила обработки (строго последовательно по 1 ссылке, запрет сторонних API перевода, работа с cookies) обязательны к исполнению.

---

## Задачи на текущую сессию

### Задача 1: Обработка 21 нераспознанной ссылки из `file.atlinks`
В файле `file.atlinks` собраны 21 подтверждённо живая ссылка (Reels, Instagram-посты, TikTok, Threads), которые ранее упали из-за устаревших cookies или сетевых таймаутов:
1. Убедись, что cookies в `.cookies/instagram.txt` и `.cookies/tiktok.txt` актуальны (если нет — сразу запроси у пользователя).
2. Последовательно по одной ссылке переведи их в статус `pending_cookies` и обработай через:
   ```bash
   PYTHONPATH=services/seed_pipeline/src python3 -m seed_pipeline.cli link-worker process-fallback --file Inbox/2026/links/<seed_id>-link.md --live-google
   ```
3. Для каждого успешного поста при необходимости выполни перевод силами агента и примени через `apply_bilingual_sync.py`.

### Задача 2: Проверка 7 упавших TikTok ссылок из `tiktok_failed.md`
В файле `tiktok_failed.md` находятся 7 ссылок TikTok:
1. Проверь доступность через `yt-dlp` / `gallery-dl` с куками из `.cookies/tiktok.txt`.
2. Если контент доступен — извлеки аудио/транскрибируй или примени OCR.
3. Если контент удалён авторами — зафиксируй удаление в `tiktok_failed.md` и `log.md`.

### Задача 3: Аудит осиротевших link-файлов
В истории зафиксированы link-файлы с битыми ссылками на slim/full:
- `2026-05-03-019`, `2026-05-03-021`, `2026-05-03-024`
- `2026-05-05-039` ... `2026-05-05-045`, `2026-05-05-053`
Проверь их: если они отсутствуют в Google Sheets и не имеют контента — удали дубли/битые ссылки согласно разделу «Дубли ссылок» в `AGENTS.md`.

---

## Фиксация результатов
1. Запусти `python3 services/seed_pipeline/audit_translations.py`.
2. Добавь запись в [log.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/log.md) в формате `## [YYYY-MM-DD] ...`.
3. Сделай `git add -A && git commit && git push`.
