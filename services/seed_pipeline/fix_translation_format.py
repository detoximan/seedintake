"""Исправление: убираем '---' из начала и конца перевода в обновлённых ячейках."""
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ws = LiveGoogleWorkspace.from_env()
rows = ws.get_all_rows()

target_rows = [408, 397, 396, 395, 394, 393, 392, 389, 388, 385]
TRANS_MARKER = "===================="

for row_num in target_rows:
    idx = row_num - 1
    if idx >= len(rows):
        print(f"row={row_num}: НЕТ В ТАБЛИЦЕ")
        continue
    row = rows[idx]
    col_e = row[4] if len(row) > 4 else ""

    if TRANS_MARKER not in (col_e or ""):
        print(f"row={row_num}: нет маркера, пропуск")
        continue

    parts = (col_e or "").split(TRANS_MARKER)
    original = parts[0].rstrip()
    translation = parts[1].strip() if len(parts) > 1 else ""

    # Убираем '---' из начала и конца перевода
    if translation.startswith("---"):
        translation = translation[3:].lstrip()
    if translation.endswith("---"):
        translation = translation[:-3].rstrip()

    new_cell = original + "\n\n" + TRANS_MARKER + "\n\n" + translation
    ws.update_range(f"E{row_num}", [[new_cell]])
    print(f"row={row_num}: исправлено, len={len(new_cell)}")

print("Готово.")