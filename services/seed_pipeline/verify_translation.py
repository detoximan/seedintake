"""Проверка: перечитываем обновлённые ячейки и проверяем формат."""
import os
import re
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ws = LiveGoogleWorkspace.from_env()
rows = ws.get_all_rows()

# Строки, которые мы обновили
target_rows = [384, 383, 382, 379, 377, 375, 374, 372, 369, 367]

TRANS_MARKER = "===================="

for row_num in target_rows:
    idx = row_num - 1
    if idx >= len(rows):
        print(f"row={row_num}: НЕТ В ТАБЛИЦЕ")
        continue
    row = rows[idx]
    col_a = row[0] if len(row) > 0 else ""
    col_e = row[4] if len(row) > 4 else ""

    has_marker = TRANS_MARKER in (col_e or "")
    if has_marker:
        parts = (col_e or "").split(TRANS_MARKER)
        original = parts[0].strip()
        translation = parts[1].strip() if len(parts) > 1 else ""
        cyr = re.findall(r"[а-яА-ЯёЁ]", translation)
        is_ru = len(cyr) > 20
    else:
        original = (col_e or "").strip()
        translation = ""
        is_ru = False

    print(f"=== row={row_num} | id={col_a} | marker={has_marker} | len={len(col_e or '')} | ru_translation={is_ru} ===")
    print(f"  Оригинал (первые 100): {original[:100]!r}")
    print(f"  Перевод (первые 100): {translation[:100]!r}")
    print()