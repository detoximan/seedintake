# Test Case: Duplicate Message Input

## Название

Duplicate Message Input

## Проверяемый агент / компонент

Seed Intake Agent v0.1: базовая дедупликация по `telegram_message_id`.

## Входные данные

Предусловие:
- `telegram_message_id`: `tg-msg-1001` уже был обработан.
- Для него уже существует Seed `2026-04-27-001`.

Повторный вход:
- `telegram_message_id`: `tg-msg-1001`
- `telegram_user_id`: `tg-user-synthetic-pavel`
- `received_at`: `2026-04-27T10:10:00+04:00`
- Основной материал: `Человек спорит не с фактом, а с собственной интерпретацией факта.`
- Комментарий Павла: `Повторная отправка того же сообщения.`

## Ожидаемый результат

- Второй Seed не создаётся.
- Существующий Markdown Seed не перезаписывается.
- Новая строка Google Sheet не создаётся.
- Новый Google Doc не создаётся.
- Система возвращает понятное предупреждение или error record с кодом `SEED_DUPLICATE_MESSAGE`.
- Severity для события: `warning`.
- `manual_action`: `none`, если повтор безопасно распознан.

## Файлы / артефакты

Создаются:
- Нет финальных Seed-артефактов.

Изменяются:
- Нет.

Не изменяются:
- `/Inbox/2026/full/2026-04-27-001-f.md`.
- Google Doc существующего Seed.
- Google Sheet row существующего Seed.
- Firestore.

## Допустимые ошибки

- `SEED_DUPLICATE_MESSAGE` с severity `warning`.

## Провал теста

- Создан второй Seed для того же `telegram_message_id`.
- Перезаписан существующий Markdown Seed.
- Создан новый Google Doc или новая строка Google Sheet.
- Дедупликация основана на смысловой похожести, а не на очевидном техническом повторе.
- Событие скрыто без понятного предупреждения или отчёта.
