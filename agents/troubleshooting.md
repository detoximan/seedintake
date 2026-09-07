# Справочник устранения неполадок (Troubleshooting)

## 1. Дубликаты ссылок в очереди `Inbox/2026/links/`
Иногда бот-сборщик записывает одну и ту же ссылку дважды.
**Решение:**
- Найти дубликаты по одинаковому URL в `*-link.md`.
- Оставить файл с наименьшим ID, удалить файлы с большими ID (link, full, slim).
- Номера не сдвигать (пропуски номеров допустимы).

Скрипт проверки дублей:
```python
import re
from pathlib import Path
from collections import defaultdict

links_dir = Path('Inbox/2026/links')
url_to_ids = defaultdict(list)
for lf in sorted(links_dir.glob('*-link.md')):
    text = lf.read_text(encoding='utf-8')
    url_m = re.search(r'url:\s*(.+)', text)
    if url_m:
        url = url_m.group(1).strip()
        stem = lf.stem.replace('-link', '')
        url_to_ids[url].append(stem)

for url, ids in url_to_ids.items():
    if len(ids) > 1:
        print(f'ДУБЛЬ: {url}')
        print(f'  Оставить: {ids[0]}, Удалить: {ids[1:]}')
```

---

## 2. Сброс локального реестра дубликатов (`processed_messages.json`)
Если ссылка была обработана с ошибкой или нужно принудительно пересоздать full/slim:
Реестр находится в `runtime/tmp/seed_pipeline/processed_messages.json`.
Очистить конкретный день или ID:
```python
import json
from pathlib import Path

p = Path('runtime/tmp/seed_pipeline/processed_messages.json')
if p.exists():
    data = json.loads(p.read_text(encoding='utf-8'))
    # удалить нужный ключ, например:
    data = {k: v for k, v in data.items() if 'ИД_ИЛИ_ДАТА' not in k}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
```

---

## 3. Ошибка `LiveGoogleWorkspaceConfigError`
- **Причина:** Не заданы переменные `GOOGLE_CREDENTIALS_FILE` (или `GOOGLE_APPLICATION_CREDENTIALS`) или `GOOGLE_SHEET_ID`.
- **Решение:** Проверить наличие `services/seed_pipeline/.env` и актуальность сервисного JSON Google.

---

## 4. Сбой ссылок в Колонке A Google Sheets
Если гиперссылки в колонке A таблицы слетели или отображаются как обычный текст:
- Запустить восстановитель:
  ```bash
  python3 services/seed_pipeline/restore_sheet_links.py
  ```

---

## 5. Аудит рассинхрона и неполных переводов
Перед закрытием рабочей сессии всегда запускайте аудит:
```bash
python3 services/seed_pipeline/audit_translations.py
```
Скрипт проверяет совпадение переводов между файлами и таблицей и выявляет обрезанные карусели.
