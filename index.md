# Индекс проекта SeedIntake (index.md)

> Навигационный хаб и каталог знаний проекта по методологии **LLM Wiki** ([3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md)).  
> Здесь собраны ссылки на все вспомогательные скрипты, правила запуска, базу знаний агента и структуру данных.

---

## 🧭 Навигация по ключевым документам

| Документ | Назначение |
|---|---|
| [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) | **Главная точка входа для LLM-агентов.** Железные правила обработки, единые циклы и регламент. |
| [log.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/log.md) | **Хронологический журнал сессий (append-only).** Лог инжестов, миграций, аудитов и изменений. |
| [3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md) | Концептуальная основа: трехуровневая архитектура персональной базы знаний (Raw Sources → Wiki → Schema). |
| [agents/README.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/README.md) | **База знаний агента:** промпты, инструкции по видео-OCR, регламенты каруселей и cookies. |

---

## ⚙️ Основной пайплайн: CLI link-worker

Базовые команды для управления очередью и процессом извлечения.

```bash
# Обновление зависимостей перед запуском
pip3 install -U yt-dlp gallery-dl

# Просмотр сводки по новым ссылкам в очереди
PYTHONPATH=services/seed_pipeline/src python3 -m seed_pipeline.cli link-worker list --status new --summary

# Обработка одной конкретной ссылки (боевой режим с записью в Google Sheets)
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file ../../Inbox/2026/links/<seed_id>-link.md --live-google

# Обработка пакета ссылок определенной платформы
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --platform instagram_reels --limit 10 --live-google

# Fallback-обработка (с cookies для ссылок в статусе pending_cookies)
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process-fallback --live-google
```

---

## 🛠️ Каталог вспомогательных скриптов (`services/seed_pipeline/`)

В папке `services/seed_pipeline/` находится набор специализированных утилит для обслуживания таблицы, аудита переводов, синхронизации и исправления данных.

| Скрипт | Назначение | Команда запуска |
|---|---|---|
| [apply_bilingual_sync.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/apply_bilingual_sync.py) | **Атомарная синхронизация перевода.** Применяет перевод сразу в `slim`, `full` и Google Sheets (`E{row}`). | `python3 services/seed_pipeline/apply_bilingual_sync.py <seed_id> --translation-file <путь_к_txt>` |
| [audit_translations.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/audit_translations.py) | **Комплексный аудит переводов.** Выявляет непереведенные посты, обрезанные слайды каруселей и рассинхрон с Google Sheets. | `python3 services/seed_pipeline/audit_translations.py [--fix] [--live-google]` |
| [restore_sheet_links.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/restore_sheet_links.py) | **Восстановление гиперссылок в Google Sheets.** Восстанавливает формулы `=HYPERLINK(...)` в Колонке A на GitHub full-файлы. | `python3 services/seed_pipeline/restore_sheet_links.py` |
| [explore_sheet.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/explore_sheet.py) | **Инспекция таблицы.** Анализирует язык контента (кириллица/латиница) и находит непереведенные строки. | `python3 services/seed_pipeline/explore_sheet.py` |
| [fix_translation_format.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/fix_translation_format.py) | **Исправление форматирования.** Удаляет мусорные разделители `---` и нормализует разделитель `====================`. | `python3 services/seed_pipeline/fix_translation_format.py` |
| [create_magicmind_sheet.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/create_magicmind_sheet.py) | **Импорт спец-коллекции.** Создает отдельный лист "Magic Mind" в Google Sheets и заполняет его данными из файла `MagicMind`. | `python3 services/seed_pipeline/create_magicmind_sheet.py` |
| [clear_today_sheet.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/clear_today_sheet.py) | **Аварийная очистка.** Удаляет строки за конкретную дату из Google Sheets при необходимости полного перепрогона. | `python3 services/seed_pipeline/clear_today_sheet.py` |
| [verify_translation.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/verify_translation.py) | **Проверка переведенных строк.** Выборочно считывает указанные строки из Google Sheets и проверяет их валидность. | `python3 services/seed_pipeline/verify_translation.py` |
| [apply_translation.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/apply_translation.py) | *Legacy:* Базовый прототип скрипта синхронизации (используйте `apply_bilingual_sync.py`). | `python3 services/seed_pipeline/apply_translation.py` |

---

## 🧠 База знаний агента (`agents/`)

Папка `agents/` накапливает регламенты и системные промпты для работы автономного агента:

- [agents/README.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/README.md) — Обзор базы знаний и правил взаимодействия.
- [agents/prompt_video_ocr_hybrid.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/prompt_video_ocr_hybrid.md) — Спецификация и промпт гибридного пайплайна: видео → аудио → Whisper, если пустой → покадровый Tesseract/Vision OCR.
- [agents/carousel_translation_guideline.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/carousel_translation_guideline.md) — Строгий регламент по-слайдового перевода каруселей 1-в-1 без потерь.
- [agents/cookies_management.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/cookies_management.md) — Правила работы с cookies (`.cookies/`), предотвращение блокировок и инструкция при истечении сессии.
- [agents/troubleshooting.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/troubleshooting.md) — Инструкция по разрешению частых проблем (дубли ссылок, сброс `processed_messages.json`, восстановление доступа).

---

## 🗂️ Структура данных и слои знаний (Wiki Architecture)

Следуя трехуровневой архитектуре Karpathy:

1. **Сырые источники (Raw Sources):**
   - `Inbox/2026/links/` — входящие `.md` файлы очередей со ссылками (`*-link.md`). Неизменяемые метаданные поступления.
   - `.cookies/` — файлы сессий для скачивания медиа.
2. **Слой Wiki / База знаний (The Compounding Wiki):**
   - `Inbox/2026/full/` (`*-f.md`) — полные исходные материалы (транскрипты, сырой OCR, описания, полный русский перевод).
   - `Inbox/2026/slim/` (`*-s.md`) — очищенный компактный слой для Obsidian / быстрого поиска и чтения человеком.
   - [MagicMind](file:///Users/pavelmalyk/pm_developer/SeedIntake/MagicMind) — тематическая коллекция материалов.
   - Google Sheets — оперативная внешняя реляционная проекция базы знаний для пользователя.
3. **Схема и правила (The Schema):**
   - [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) — системные правила и ограничения LLM.
   - [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md) — предметный каталог и карта репозитория.
   - [log.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/log.md) — хроника всех изменений и инжестов.

---

## 🚀 Сервисы репозитория

- **`services/seed_pipeline`**:
  Основной рабочий движок: загрузка медиа, Whisper STT, Tesseract OCR, интеграция с Google Sheets и генерация Markdown-файлов.
- **`services/telegram_intake_bot`**:
  Сервис на базе Google Cloud Run (Europe Amsterdam), принимающий ссылки и заметки из Telegram-бота и создающий записи в `Inbox/2026/links/`.
