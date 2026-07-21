# Лог сессии: Обработка Instagram Reels (2026-07-12, 001-007)

## Контекст

Было 7 ссылок Instagram Reels за 12 июля 2026 (001-007). После первого запуска `process-fallback` они получили статус `processed`, но slim/full файлы не создались — писали в несуществующую директорию `1inbox/seeds/`.

## Проблема 1: Неправильный путь в коде (жестко зашит `1inbox/seeds/`)

**Файлы проекта — `SeedIntake/`**, структура:
```
Inbox/2026/        ← реальная папка (с большой буквы)
  full/
  slim/
  links/
```

**Код писал в:** `repo_root / "1inbox" / "seeds"` — такой папки не существует.

**Исправлено в 3 файлах:**

1. **`services/seed_pipeline/src/seed_pipeline/intake/markdown_writer.py`** (строка ~40):
   - Было: `self.seed_root = seed_root or self.repo_root / "1inbox" / "seeds"`
   - Стало: `self.seed_root = seed_root or self.repo_root / "Inbox"`

2. **`services/seed_pipeline/src/seed_pipeline/intake/dry_run.py`** (строка 68):
   - Было: `seed_id = _next_seed_id(root / "1inbox" / "seeds", ...)`
   - Стало: `seed_id = _next_seed_id(root / "Inbox", ...)

3. **`services/seed_pipeline/src/seed_pipeline/link_worker/queue.py`** (строка ~35):
   - Было: `self.seed_root = seed_root or self.repo_root / "1inbox" / "seeds"`
   - Стало: `self.seed_root = seed_root or self.repo_root / "Inbox"`
   - Также добавлен `links/` в паттерн поиска для `include_fallback`, иначе `process-fallback` не видел файлы в `links/`.

## Проблема 2: Реестр дубликатов (processed_messages.json)

Даже после исправления путей slim/full не создавались. Причина:
- `SeedMarkdownWriter` перед записью проверяет `processed_messages.json` (`runtime/tmp/seed_pipeline/processed_messages.json`)
- При первом (ошибочном) запуске реестр запомнил ссылку `002-link.md` → `2026-07-12-001`
- При повторном запуске `orchestrator` находил дубликат и не создавал slim/full

**Решение:** Очистить реестр от записей за 12 июля:
```python
# код очистки
p = Path('runtime/tmp/seed_pipeline/processed_messages.json')
data = json.loads(p.read_text())
for k in list(data):
    if '2026-07-12' in k:
        del data[k]
p.write_text(json.dumps(data, indent=2) + '\n')
```

## Проблема 3: Instagram требует cookies

`process` (без cookies) падает с `Instagram sent an empty media response`. Нужен `process-fallback`, который использует `--cookies-from-browser`.

## Текущее состояние (на момент завершения сессии)

- [x] Пути исправлены (3 файла)
- [x] Очередь `links/` теперь видна для `process-fallback`
- [x] Транскрибация работает (текст есть в логах)
- [x] Google Sheet обновляется
- [ ] Slim/full НЕ созданы — реестр не дочищен до конца
- [ ] Фоновый `process-fallback` запущен и работает, но без slim/full

## Команды для нового чата

### Полный перезапуск (рекомендуется)

```bash
# 1. Убить фоновый процесс
ps aux | grep 'link-worker process-fallback' | grep -v grep | awk '{print $2}' | xargs -r kill

# 2. Очистить реестр от записей за 12 июля
python3 -c "
import json
p = 'runtime/tmp/seed_pipeline/processed_messages.json'
data = json.loads(open(p).read())
data = {k: v for k, v in data.items() if '2026-07-12' not in k}
open(p, 'w').write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
print('cleaned:', len(data), 'entries left')
"

# 3. Сбросить статусы 002-007 в pending_cookies
python3 -c "
import re, pathlib
for n in range(2, 8):
    p = pathlib.Path(f'Inbox/2026/links/2026-07-12-{n:03d}-link.md')
    content = p.read_text()
    content = re.sub(r'^status: processed\$', 'status: pending_cookies', content, flags=re.MULTILINE)
    p.write_text(content)
"

# 4. Удалить старые slim/full (если есть)
find . -path '*/Inbox/2026/*/2026-07-12-*' | xargs -r rm

# 5. Запустить обработку
cd services/seed_pipeline
set -a && source ./.env 2>/dev/null; set +a
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process-fallback --live-google 2>&1
```

### Проверка результатов

```bash
# Статусы link-файлов
python3 -c "
import pathlib, re
for n in range(1, 8):
    p = pathlib.Path(f'Inbox/2026/links/2026-07-12-{n:03d}-link.md')
    if p.exists():
        m = re.search(r'^status:\s*(\S+)', p.read_text(), re.M)
        print(f'{p.name}: {m.group(1) if m else \"no status\"}')
"

# Список slim/full
find Inbox/2026 -name '2026-07-12-*' -not -path '*/links/*'
```

## Технические детали

- **Транскрибация успешна:** для ссылки 002 (DaXKeeIsC73) лог показывает текст ~1047 символов
- **Google Sheet:** ID `1lc6Q1bzQ4AW40pPJhVYJAof8tH6oCAFtmSXQZwg4r98`, запись успешна
- **Cookie rate limit:** 65 секунд между запросами (env `COOKIE_REQUEST_INTERVAL`)
- **youtube-dl** с `--cookies-from-browser` работает, но Instagram может слать пустой ответ

## Миграция отдельного SeedIntake завершена — 2026-07-21

- Cloud Run: seedintake-telegram-bot, europe-west4 (Amsterdam).
- Ревизия: seedintake-telegram-bot-00002-zjx, 100% трафика.
- URL: https://seedintake-telegram-bot-v7om675z7q-ez.a.run.app.
- Health check: /health возвращает ok.
- Telegram webhook переключён на европейский сервис; pending updates: 0, ошибок нет.
- GitHub storage: detoximan/seedintake; очередь: Inbox/YYYY/links/; результаты: Inbox/YYYY/full/ и Inbox/YYYY/slim/.
- Секреты подключены через Secret Manager; значения в репозиторий не записываются.
- Тесты: seed_pipeline 34/34, telegram_intake_bot 52/52.
- Старый американский detoximan-telegram-intake-bot оставлен без активного webhook до отдельного решения об удалении.
