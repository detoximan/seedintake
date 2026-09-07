# Индекс проекта SeedIntake (index.md)

> Предметный каталог и навигационный хаб проекта по методологии **LLM Wiki** ([3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md)).  
> Здесь собраны ссылки на все сервисы, вспомогательные скрипты, правила запуска и структуру данных.

---

## 🧭 Ключевые документы системы

| Документ | Роль по Karpathy | Назначение |
|---|---|---|
| [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) | **The Schema** | **Единая точка входа для LLM-агента.** Все правила извлечения, по-слайдового перевода, cookies, циклы обработки и устранение ошибок. |
| [log.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/log.md) | **The Log** | **Хронологический append-only журнал.** История сессий, инжестов, миграций и аудитов. |
| [3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md) | **Architecture** | Концептуальная основа: трехуровневая архитектура персональной базы знаний (Raw Sources → Wiki → Schema). |

---

## ⚙️ Основной пайплайн: CLI link-worker

Базовые команды для управления очередью и процессами обработки:

```bash
# Обновление загрузчиков перед запуском
pip3 install -U yt-dlp gallery-dl

# Просмотр сводки очереди новых ссылок
PYTHONPATH=services/seed_pipeline/src python3 -m seed_pipeline.cli link-worker list --status new --summary

# Обработка одной конкретной ссылки (боевой режим с записью в Google Sheets)
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file ../../Inbox/2026/links/<seed_id>-link.md --live-google

# Обработка пакета ссылок платформы
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --platform instagram_reels --limit 10 --live-google

# Fallback-обработка (с cookies для ссылок в статусе pending_cookies)
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process-fallback --live-google
```

---

## 🛠️ Каталог вспомогательных скриптов (`services/seed_pipeline/`)

Все специализированные утилиты для обслуживания базы данных, Google Sheets и синхронизации:

| Скрипт | Назначение | Команда запуска |
|---|---|---|
| [apply_bilingual_sync.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/apply_bilingual_sync.py) | **Атомарная синхронизация перевода.** Применяет двуязычный перевод синхронно в `slim`, `full` и Google Sheets (`E{row}`). | `python3 services/seed_pipeline/apply_bilingual_sync.py <seed_id> --translation-file <путь_к_txt>` |
| [audit_translations.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/audit_translations.py) | **Комплексный аудит переводов.** Выявляет непереведенные посты, обрезанные слайды каруселей и рассинхрон с Google Sheets. | `python3 services/seed_pipeline/audit_translations.py [--fix] [--live-google]` |
| [restore_sheet_links.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/restore_sheet_links.py) | **Восстановление ссылок в Google Sheets.** Восстанавливает формулы `=HYPERLINK(...)` в Колонке A на GitHub full-файлы. | `python3 services/seed_pipeline/restore_sheet_links.py` |
| [explore_sheet.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/explore_sheet.py) | **Инспекция таблицы.** Анализирует язык контента (кириллица/латиница) и находит непереведенные строки. | `python3 services/seed_pipeline/explore_sheet.py` |
| [fix_translation_format.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/fix_translation_format.py) | **Исправление форматирования.** Удаляет мусорные разделители `---` и нормализует разделитель `====================`. | `python3 services/seed_pipeline/fix_translation_format.py` |
| [create_magicmind_sheet.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/create_magicmind_sheet.py) | **Импорт спец-коллекции.** Создает отдельный лист "Magic Mind" в Google Sheets и заполняет его данными из файла `MagicMind`. | `python3 services/seed_pipeline/create_magicmind_sheet.py` |
| [clear_today_sheet.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/clear_today_sheet.py) | **Аварийная очистка.** Удаляет строки за конкретную дату из Google Sheets при необходимости повторной обработки. | `python3 services/seed_pipeline/clear_today_sheet.py` |
| [verify_translation.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/verify_translation.py) | **Проверка строк таблицы.** Выборочно считывает указанные строки из Google Sheets и проверяет их валидность. | `python3 services/seed_pipeline/verify_translation.py` |
| [manual_translate_next10.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/manual_translate_next10.py) | **Просмотр пачек строк.** Выводит текст указанных строк таблицы для подготовки ручного перевода. | `python3 services/seed_pipeline/manual_translate_next10.py` |
| [apply_translation.py](file:///Users/pavelmalyk/pm_developer/SeedIntake/services/seed_pipeline/apply_translation.py) | *Legacy:* Базовый прототип скрипта синхронизации (используйте `apply_bilingual_sync.py`). | `python3 services/seed_pipeline/apply_translation.py` |

---

## 🗂️ Структура данных и уровни знаний (Wiki Architecture)

1. **Сырые источники (Raw Sources):**
   - `Inbox/2026/links/` — неизменяемые `.md` файлы очередей с метаданными поступления (`*-link.md`).
   - `.cookies/` — файлы авторизованных сессий (`instagram.txt`, `facebook.txt`, `tiktok.txt`).
2. **Слой Wiki / База знаний (The Compounding Wiki):**
   - `Inbox/2026/full/` (`*-f.md`) — полные исходные материалы (транскрипты, сырой OCR, описания, полный русский перевод).
   - `Inbox/2026/slim/` (`*-s.md`) — очищенный компактный слой для чтения и навигации в Obsidian.
   - [MagicMind](file:///Users/pavelmalyk/pm_developer/SeedIntake/MagicMind) — тематическая коллекция материалов.
   - Google Sheets — внешняя оперативная табличная проекция базы знаний для пользователя.
3. **Схема и правила (The Schema):**
   - [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md) — единые правила работы агента, стандарты и инструкции.

---

## 🚀 Сервисы репозитория

- **`services/seed_pipeline`**:
  Основной рабочий сервис: скачивание медиа, Whisper STT, Tesseract OCR, интеграция с Google Sheets и запись Markdown.
- **`services/telegram_intake_bot`**:
  Сервис на базе Google Cloud Run (Europe Amsterdam), принимающий ссылки и заметки из Telegram-бота и создающий записи в `Inbox/2026/links/`.
