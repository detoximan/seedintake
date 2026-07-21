# Test Case: Link Seed Input

## Название

Link Seed Input

## Проверяемый агент / компонент

Seed Intake Agent v0.1: обработка входа со ссылкой.

## Входные данные

- `telegram_message_id`: `tg-msg-1002`
- `telegram_user_id`: `tg-user-synthetic-pavel`
- `received_at`: `2026-04-27T10:05:00+04:00`
- Основной материал: `https://example.com/synthetic-clear-thinking-post`
- Комментарий Павла: `Нужно сохранить как пример крючка про эмоциональные качели.`
- `source_url`: `https://example.com/synthetic-clear-thinking-post`
- Предусловие: `tg-msg-1002` ранее не обрабатывался.

## Ожидаемый результат

- Создан новый Seed ID в формате `YYYY-MM-DD-NNN`, например `2026-04-27-002`.
- Seed получает статус `new`.
- Google Doc содержит ссылку на источник и нормализованный комментарий Павла.
- Google Sheet row содержит минимальные поля v0.1: ID-ссылку на Google Doc, статус `new`, комментарий Павла и транскрибацию / нормализованный текст.
- Markdown Seed содержит минимальный формат: `status: new`, Seed ID как ссылку на Google Doc, комментарий Павла и источник для обработки.
- Внутренний Seed plan / dedup layer содержит fingerprint.
- `source_url` во внутреннем fingerprint заполнен исходной ссылкой.
- Seed Intake не оценивает потенциал ссылки и не выбирает будущий формат контента.
- Firestore не используется.

## Файлы / артефакты

Создаются:
- Google Doc Seed dossier: синтетическая ссылка-заглушка.
- Google Sheet row в Seed registry.
- Ожидаемый Markdown path: `/Inbox/2026/full/2026-04-27-002-f.md`.

Изменяются:
- Google Sheet Seed registry.

Не изменяются:
- Существующие Markdown Seed-файлы.
- Publication queue.
- Firestore.

## Допустимые ошибки

- `SEED_SOURCE_FETCH_WARNING`, если внешняя ссылка временно недоступна, но исходный URL и комментарий Павла можно безопасно сохранить как сырьё.

## Провал теста

- Валидная ссылка не сохраняется как Seed.
- `source_url` отсутствует во внутреннем fingerprint.
- Агент пытается провести стратегическую оценку или выбрать формат публикации.
- Seed создаётся без Google Doc, без Google Sheet row или без Markdown.
- Использован Firestore как хранилище Seed.
