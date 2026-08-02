"""Перевод англоязычных транскрибаций на русский партиями по 10.

Usage:
    python3 translate_batch.py --dry-run   # показать выбранные строки и их тексты
    python3 translate_batch.py --write     # перевести и записать в Google Sheets
"""
import argparse
import os
import re
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")
DEVANAGARI = re.compile(r"[\u0900-\u097F]")
CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\uac00-\ud7af]")

TRANS_MARKER = "===================="

SERVICE_MARKERS = [
    "1 – текст на фото:",
    "1 – Текст на фото:",
    "2 – транскрибация аудио/видео:",
    "2 – Транскрибация аудио/видео:",
    "3 – текст под медиа:",
    "3 – Текст под медиа:",
]

EMPTY_WORDS = {"нет", "no", "текста нет"}


def has_cyrillic(text: str) -> bool:
    return bool(CYRILLIC.search(text or ""))


def extract_main_text(cell: str) -> str:
    """Текст до черты перевода (оригинал)."""
    idx = (cell or "").find(TRANS_MARKER)
    return (cell or "")[:idx] if idx != -1 else (cell or "")


def is_already_translated(cell: str) -> bool:
    return TRANS_MARKER in (cell or "")


def get_real_content(main_text: str) -> str:
    """Контент без служебных заголовков и значений 'нет'."""
    result = main_text
    for marker in SERVICE_MARKERS:
        result = result.replace(marker, " ")
    lines = []
    for line in result.split("\n"):
        stripped = line.strip()
        if stripped.lower() in EMPTY_WORDS:
            continue
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def is_foreign(content: str) -> bool:
    """Контент не на русском и не пустой."""
    if not content:
        return False
    if has_cyrillic(content):
        return False
    return True


def select_rows(rows: list[list[str]], limit: int = 10) -> list[dict]:
    """Выбрать первые `limit` англоязычных непереведённых строк с конца."""
    candidates = []
    for i, row in enumerate(rows):
        if i == 0:
            continue  # заголовки
        row_num = i + 1
        col_a = row[0] if len(row) > 0 else ""
        col_e = row[4] if len(row) > 4 else ""

        if is_already_translated(col_e):
            continue

        main_text = extract_main_text(col_e).strip()
        content = get_real_content(main_text)
        if not content:
            continue
        if not is_foreign(content):
            continue

        candidates.append({
            "row_num": row_num,
            "seed_id": col_a,
            "cell": col_e,
            "main_text": main_text,
            "content": content,
        })

    candidates_desc = sorted(candidates, key=lambda d: d["row_num"], reverse=True)
    return candidates_desc[:limit]


def translate_to_ru(text: str, client) -> str:
    """Перевести текст на русский через Groq, сохранив структуру."""
    prompt = f"""Переведи следующий текст на русский язык. Требования:
- Сохрани структуру строк вида «1 – Текст на фото: ...», «2 – Транскрибация аудио/видео: ...», «3 – Текст под медиа: ...». Сами заголовки уже на русском — не меняй их, переводи только содержимое после двоеточия.
- Сохрани переносы строк и пустые строки.
- Имена файлов в квадратных скобках (например [photo.jpg]), ссылки, хэштеги, упоминания @аккаунтов и эмодзи — не переводи, сохрани как есть.
- Если содержимое секции — «нет» или «no», оставь русское «нет».
- Переведи ВЕСЬ контент: текст на фото, транскрибацию, текст под медиа.

Текст для перевода:
---
{text}
---

Верни ТОЛЬКО перевод, без пояснений."""

    chat = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=8192,
    )
    return chat.choices[0].message.content.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Показать выбранные строки без записи")
    parser.add_argument("--write", action="store_true", help="Перевести и записать в таблицу")
    parser.add_argument("--all-foreign", action="store_true", help="Включая не-английские языки (индийский и т.д.)")
    args = parser.parse_args()

    ws = LiveGoogleWorkspace.from_env()
    rows = ws.get_all_rows()

    limit = 10
    if args.all_foreign:
        limit = 10
    selected = select_rows(rows, limit=limit)
    print(f"Найдено англоязычных непереведённых строк снизу вверх: {len(selected)}")
    print()

    for d in selected:
        print(f"=== row={d['row_num']} | id={d['seed_id']} | len={len(d['cell'])} ===")
        print(d["main_text"])
        print()

    if not args.write:
        print("DRY RUN — запись не выполнялась. Для записи: python3 translate_batch.py --write")
        return

    # Запись
    client = None
    try:
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            print("ОШИБКА: GROQ_API_KEY не найден в .env")
            return
        client = Groq(api_key=api_key)
    except ImportError:
        print("ОШИБКА: groq не установлен")
        return

    report_lines = []
    for d in selected:
        print(f"\nПеревод row={d['row_num']} id={d['seed_id']}...")
        translated = translate_to_ru(d["main_text"], client)
        new_cell = d["main_text"].rstrip() + "\n\n" + TRANS_MARKER + "\n\n" + translated
        ws.update_range(f"E{d['row_num']}", [[new_cell]])
        print(f"  Записано: {len(new_cell)} символов")
        report_lines.append(f"=== row={d['row_num']} | id={d['seed_id']} ===\n{new_cell}\n")

    report_path = os.path.join(os.path.dirname(__file__), "translation_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(report_lines))
    print(f"\nОтчёт сохранён: {report_path}")
    print("Готово.")


if __name__ == "__main__":
    main()