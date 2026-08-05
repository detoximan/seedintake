# SeedIntake — AGENTS.md

Любой LLM-агент, зашедший в проект, начинает здесь. Технические данные деплоя и секреты — в `AGENTS.old.md`.

## Логика обработки (железная)

```
Ссылка → Router (по URL) → Скачивание с cookies → Извлечение контента → Проверка → Запись → Коммит
```

### Извлечение контента по типам:

| URL-паттерн | Тип | Обработчик | Что делает |
|---|---|---|---|
| `instagram.com/reel/...` | `instagram_reels` | `instagram.py.process_reels()` | Видео → аудио → транскрибация. **Если пусто** → покадровый OCR |
| `instagram.com/p/...` | `instagram_carousel` | `instagram.py.process_carousel()` | Instaloader → gallery-dl → yt-dlp. Фото → OCR. Видео → транскрибация → **если пусто** → OCR кадров |
| `tiktok.com/video/...` | `tiktok_video` | `tiktok.py.process()` | Видео → аудио → транскрибация. **Если пусто** → покадровый OCR |
| `tiktok.com/photo/...` | `tiktok_photo` | `tiktok.py.process()` | Фото → OCR |
| `youtube.com/shorts/...` | `youtube_shorts` | `youtube.py.process()` | Аудио → транскрибация. **Если пусто** → покадровый OCR |
| `facebook.com`, `threads.net`, прочие | `text_post` | `web.py.process()` | yt-dlp → Jina Reader (текст) |

**Покадровый OCR запускается ТОЛЬКО если транскрибация пустая.** Не делаем OCR кадров если есть речь — это лишняя работа.

---

## Шаг 1: Старт

```bash
cd SeedIntake && git pull
PYTHONPATH=services/seed_pipeline/src python3 -m seed_pipeline.cli link-worker list --status new --summary
```

Сообщи количество новых ссылок по платформам.

## Шаг 2: Автообновление утилит (без доклада пользователю)

Перед ЛЮБЫМ запуском обработки:
```bash
pip3 install -U yt-dlp gallery-dl
```

## Шаг 3: Обработка

**Боевой режим:** ВСЕГДА с флагом `--live-google`. Без него данные не запишутся в Google Sheet.

### Конкретная ссылка:
```bash
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file <путь_к_файлу> --live-google
```

### Все новые ссылки:
```bash
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --limit 100 --live-google
```

### Конкретная платформа:
```bash
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --platform <youtube_shorts|instagram_reels|tiktok_video|text_post> --live-google
```

### Fallback (только для ручного переобхода failed ссылок):
Если пользователь обновил cookies и хочет переобработать `failed` ссылки — поменяй им статус на `pending_cookies` и запусти:
```bash
cd services/seed_pipeline
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process-fallback --live-google
```

## Шаг 4: Верификация контента (ОБЯЗАТЕЛЬНО)

После обработки КАЖДОЙ ссылки:
1. Открой slim-файл по пути `processed_seed_path` из link-файла.
2. Проверь, есть ли реальный контент:
   - `Транскрибация аудио/видео: нет` → контент пустой
   - `Текст на фото: нет` + `Транскрибация: нет` + `Текст под медиа: нет` → контент пустой
   - Материал < 100 символов и только "нет" → контент пустой
3. Если контент пустой — статус уже `failed` (воркер ставит автоматически). Не переопределяй.
4. Только реальный осмысленный текст = `processed`.

## Шаг 5: Перевод (делает АГЕНТ, не скрипты)

Если текст на иностранном языке — **сам агент переводит на русский**. Формат:
```text
[Оригинальный текст]

====================

[Перевод на русский]
```

Правила:
- Заголовки секций (`1 – Текст на фото:`, `2 – Транскрибация:`, `3 – Текст под медиа:`) НЕ переводить
- Имена файлов `[photo.jpg]`, ссылки, хэштеги, `@аккаунты`, эмодзи НЕ переводить
- «нет» / «no» → «нет»

Обнови slim, full и Google Sheet.

## Шаг 6: Коммит и пуш

```bash
cd SeedIntake
git add -A
git commit -m "Обработка ссылок с переводом: <дата>"
git push
```

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `GOOGLE_CREDENTIALS_FILE` или `GOOGLE_APPLICATION_CREDENTIALS` | Путь к JSON сервисного аккаунта Google |
| `GOOGLE_SHEET_ID` | ID Google таблицы |
| `GROQ_API_KEY` | API ключ Groq для транскрибации |
| `GROQ_STT_MODEL` | Модель (например, `whisper-large-v3-turbo`) |
| `GROQ_STT_LANGUAGE` | (Опц.) Язык транскрибации |
| `YT_DLP_BIN` | (Опц.) Путь к yt-dlp |

Требуются: `yt-dlp`, `ffmpeg`, `ffprobe`, `tesseract`.

## Ошибки

- `LiveGoogleWorkspaceConfigError` → скажи: *"Настрой переменные окружения Google Sheets (GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID)"*
- Пустой контент → `status: failed` (автоматически)
- Сброс ошибки: поменяй `status: failed` на `status: new` в `.md` файле

## Диагностика

```bash
# Новые
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status new
# Ошибки
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status failed
# Обработанные
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status processed
```

## Принципы

- **Cookies сразу** — обработчик идёт с cookies с первого раза, без промежуточного `pending_cookies`
- **Покадровый OCR только при пустой транскрибации** — не делаем лишнюю работу
- **Перевод силами агента** — никаких сторонних API перевода
- **Двуязычный формат** — оригинал + `====================` + русский
- **Сквозная нумерация** — один номер для link, full и slim
- **Воркер сам ставит `failed`** при пустом контенте — агент не должен это делать вручную