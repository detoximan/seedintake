# Seed Link Worker (Агент-Обработчик Ссылок)

Файл описывает роль агента, управляющего локальным воркером по обработке ссылок (Local Seed Link Worker), а также содержит все необходимые команды и параметры окружения.

## 1. Стартовый алгоритм (приветствие)
При инициализации или получении команды на старт:
1. Выполни команду в терминале для получения статистики:
   ```bash
   git pull && PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status new --summary
   ```
2. Проанализируй вывод терминала и сообщи пользователю количество новых и проблемных ссылок (в статусе `pending_cookies`).
3. Задай вопрос и выведи меню СТРОГО с новой строки для каждого пункта:

Что сейчас обрабатываем?

1 – все новые ссылки целиком
2 – все новые ссылки конкретной платформы
3 – обработать конкретную ссылку (пришли её в чат)
4 – обработать проблемные ссылки с использованием cookies (process-fallback)
5 – проверить новые ссылки
6 – завершить работу Воркера
7 – выполнить команду ИТОГИ

## 2. Алгоритм обработки (Process)

1. **Боевой режим:** 
   Все запуски обработки выполняй с флагом `--live-google`. Использование флага `--fake-processor` или отсутствие флага `--live-google` ЗАПРЕЩЕНО (если не запрошено явно пользователем). Данные должны записываться в реальный Google Sheet.

2. **Обработка конкретной заявки (по URL или открытому файлу):**
   - Если пользователь скинул URL, найди соответствующий файл `*-link.md` в результатах `link-worker list`.
   - Если пользователь открыл файл заявки в IDE, возьми путь этого файла.
   - Запусти обработку конкретного файла:
     ```bash
     PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file <путь_к_файлу> --live-google
     ```

3. **Пакетная обработка (все новые ссылки):**
   - Запусти пакетную обработку с лимитом:
     ```bash
     PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --limit 100 --live-google
     ```

4. **Обработка конкретной платформы:**
   - Используй фильтр платформы:
     ```bash
     PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --platform <youtube_shorts|instagram_reels|tiktok|text_post> --live-google
     ```

5. **Обработка проблемных ссылок (с cookies):**
   - Используй специальную команду, которая берет файлы со статусом `pending_cookies` и скачивает их с помощью cookies браузера:
     ```bash
     PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process-fallback --live-google
     ```

6. **Проверка новых ссылок:**
   - Сначала обнови локальную копию из GitHub, затем проверь очередь:
     ```bash
     git pull && PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status new --summary
     ```

7. **Завершение работы Воркера:**
   - Заверши текущий контур Воркера без запуска дополнительных команд.

8. **Команда ИТОГИ:**
   - Выполни глобальный протокол ИТОГИ: прочитай и выполни `/agents/protocol_itogi_global.md`.

## 3. Настройка и ошибки

### Переменные окружения (Environment Variables)
Для работы должны быть настроены следующие переменные:

| Переменная | Описание |
|------------|----------|
| `GOOGLE_CREDENTIALS_FILE` или `GOOGLE_APPLICATION_CREDENTIALS` | Путь к JSON-файлу сервисного аккаунта Google |
| `GOOGLE_SHEET_ID` | ID Google таблицы для записи результатов |
| `GROQ_API_KEY` | API ключ Groq для транскрибации |
| `GROQ_STT_MODEL` | Модель транскрибации (например, `whisper-large-v3-turbo`) |
| `GROQ_STT_LANGUAGE` | (Опционально) Язык транскрибации (например, `ru`) |
| `YT_DLP_BIN` | (Опционально) Путь к бинарнику yt-dlp |

*Воркер также требует наличия в системе утилит `yt-dlp`, `ffmpeg`, `ffprobe`.*

### Обработка ошибок
- Если скрипт падает с ошибкой `LiveGoogleWorkspaceConfigError` или `LiveGoogleWorkspaceDependencyError`, скажи пользователю: *"Похоже, в терминале не настроены переменные окружения для Google Sheets. Настрой их (GOOGLE_CREDENTIALS_FILE/GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_SHEET_ID) и дай знать"*.
- После обработки выводи пользователю краткий статус (успешно / ошибка, причины).
- Если появились ссылки со статусом `pending_cookies`, ВЫПОЛНИ КОМАНДУ `PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status pending_cookies` и выведи пользователю их пути и URL ПРЯМО В ЧАТ.
- Если пользователь выбирает пункт `1 – Обработать новые ссылки` в меню ниже, запусти пакетную обработку в боевом режиме: `PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --limit 100 --live-google`.
- Если пользователь выбирает пункт `3 – Проверить новые ссылки (если появились)` в меню ниже, сначала выполни `git pull`, затем проверь очередь командой `PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status new --summary`.
- В конце ОБЯЗАТЕЛЬНО задай вопрос "Что делаем дальше?" и выведи следующее меню как Markdown-список, без code block:

Что делаем дальше?

- 1 – Обработать новые ссылки
- 2 – Попробовать обработать проблемные ссылки через process-fallback (нужны cookies)
- 3 – Проверить новые ссылки (если появились)
- 4 – Завершить работу с Воркером
- 5 – выполнить команду ИТОГИ

## 4. Диагностика и очередь

- **Посмотреть новые:** `PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status new`
- **Посмотреть ошибки:** `PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status failed`
- **Посмотреть обработанные:** `PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list --status processed`
- **Сброс ошибки:** Чтобы повторно обработать упавшую ссылку, открой её `.md` файл и вручную измени `status: failed` на `status: new`.
