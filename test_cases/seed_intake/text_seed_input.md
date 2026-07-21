# Test Case: Text Seed Input

## Название

Text Seed Input

## Проверяемый агент / компонент

Seed Intake Agent v0.1: обработка текстового входа из Telegram.

## Входные данные

- `telegram_message_id`: `tg-msg-1001`
- `telegram_user_id`: `tg-user-synthetic-pavel`
- `received_at`: `2026-04-27T10:00:00+04:00`
- Основной материал: `Человек спорит не с фактом, а с собственной интерпретацией факта.`
- Комментарий Павла: `Хочу сохранить как seed про отделение фактов от интерпретаций.`
- `source_url`: пусто
- Предусловие: `tg-msg-1001` ранее не обрабатывался.

## Ожидаемый результат

- Создан новый Seed ID в формате `YYYY-MM-DD-NNN`, например `2026-04-27-001`.
- Seed получает статус `new`.
- Создано полное досье Google Doc с основным материалом и комментарием Павла.
- Добавлена строка в Google Sheet Seed registry.
- Создан Markdown Seed в `/Inbox/2026/full/2026-04-27-001-f.md`.
- Markdown содержит минимальный формат: `status: new`, Seed ID как ссылку на Google Doc, комментарий Павла и источник для обработки.
- Внутренний Seed plan / dedup layer содержит `input_fingerprint` и поля `telegram_message_id`, `telegram_user_id`, `source_url`, `received_at`, `content_hash`.
- `source_url` во внутреннем fingerprint пустой или `null`.
- Firestore не используется.

## Файлы / артефакты

Создаются:
- Google Doc Seed dossier: синтетическая ссылка-заглушка.
- Google Sheet row в Seed registry.
- Ожидаемый Markdown path: `/Inbox/2026/full/2026-04-27-001-f.md`.

Изменяются:
- Google Sheet Seed registry.

Не изменяются:
- Существующие Markdown Seed-файлы.
- `/test_cases/**`.
- Firestore.

## Допустимые ошибки

Нет.

## Провал теста

- Seed не создан для валидного текстового входа.
- Markdown Seed не соответствует минимальному формату.
- Внутренний Seed plan не содержит обязательный fingerprint.
- Создан Seed без статуса `new`.
- Создан частичный артефакт без синхронизации Google Doc, Google Sheet и Markdown.
- Использован Firestore как хранилище Seed.
- Перезаписан существующий Markdown Seed.
