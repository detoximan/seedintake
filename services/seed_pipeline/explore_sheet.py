"""Разведка: определяем язык ОСНОВНОГО контента (без служебных слов) и находим непереведённые англоязычные строки."""
import os
import re
import sys
from collections import Counter

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ws = LiveGoogleWorkspace.from_env()
rows = ws.get_all_rows()

print(f"Всего строк: {len(rows)}")

CYRILLIC_PATTERN = re.compile(r"[а-яА-ЯёЁ]")


def is_cyrillic(text: str) -> bool:
    return bool(CYRILLIC_PATTERN.search(text or ""))


def extract_main_text(cell: str) -> str:
    """Текст до черты перевода."""
    marker = "===================="
    idx = (cell or "").find(marker)
    if idx != -1:
        return (cell or "")[:idx]
    return cell or ""


SERVICE_MARKERS = [
    "1 – текст на фото:",
    "1 – Текст на фото:",
    "2 – транскрибация аудио/видео:",
    "2 – Транскрибация аудио/видео:",
    "3 – текст под медиа:",
    "3 – Текст под медиа:",
]


def strip_service_words(text: str) -> str:
    """Удаляем служебные префиксы и значения 'нет'."""
    result = text
    for marker in SERVICE_MARKERS:
        result = result.replace(marker, " ")
    # Убираем строки, состоящие только из 'нет', и пустые строки
    lines = []
    for line in result.split("\n"):
        stripped = line.strip()
        if stripped.lower() in ("нет", "no", "текста нет"):
            continue
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


data = []
for i, row in enumerate(rows):
    if i == 0:
        continue  # заголовки
    row_num = i + 1
    col_a = row[0] if len(row) > 0 else ""
    col_e = row[4] if len(row) > 4 else ""

    main_text = extract_main_text(col_e).strip()
    has_translation = "====================" in (col_e or "")

    # Основной контент без служебных слов
    content = strip_service_words(main_text).strip()

    if not content:
        lang = "empty"
    elif is_cyrillic(content):
        lang = "ru"
    else:
        lang = "en"  # англ., испан., др.

    data.append({
        "row_num": row_num,
        "col_a": col_a,
        "content": content,
        "has_translation": has_translation,
        "lang": lang,
        "cell_len": len(col_e or ""),
    })

lang_counts = Counter(d["lang"] for d in data)
print("Статистика языков основного контента:", dict(lang_counts))
print(f"Уже переведено: {sum(1 for d in data if d['has_translation'])}")
print()

# Непереведённые строки с контентом не на русском, снизу вверх
non_ru = [d for d in data if d["lang"] != "ru" and d["lang"] != "empty" and not d["has_translation"]]
non_ru_desc = sorted(non_ru, key=lambda d: d["row_num"], reverse=True)

print(f"=== НЕПЕРЕВЕДЁННЫЕ НЕ-РУССКИЕ СТРОКИ СНИЗУ ВВЕРХ: {len(non_ru_desc)} ===")
for d in non_ru_desc:
    preview = re.sub(r"\s+", " ", d["content"])[:200]
    print(f"row={d['row_num']} | id={d['col_a']} | cell_len={d['cell_len']}")
    print(f"    content-preview: {preview}")
    print()