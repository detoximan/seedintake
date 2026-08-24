"""Обновить ячейку E для seed 2026-07-31-003: добавить русский перевод."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE / "src"))

from seed_pipeline.integrations import LiveGoogleWorkspace

TRANS_MARKER = "===================="
SEED_ID = "2026-07-31-003"

TRANSLATED = """1 – Текст на фото:
нет

2 – Транскрибация аудио/видео:
нет

3 – Текст под медиа:
Жизнь так прекрасна. Постарайся не зацикливаться на негативе, когда вокруг столько поводов быть благодарным. Этот день, этот час, эта минута так драгоценны 🌿🍃🫶🏼

#natureisbeautiful #naturephotography #cypresscreek #vancouver #slowmotion
"""

ws = LiveGoogleWorkspace.from_env()
rows = ws.get_all_rows()
target_row = None
orig_cell = ""
for i, row in enumerate(rows):
    if i == 0:
        continue
    if SEED_ID in str(row[0]):
        target_row = i + 1
        orig_cell = row[4] if len(row) > 4 else ""
        break

if not target_row:
    print(f"Строка {SEED_ID} не найдена")
    sys.exit(1)

new_cell = orig_cell.rstrip() + "\n\n" + TRANS_MARKER + "\n\n" + TRANSLATED.strip()
ws.update_range(f"E{target_row}", [[new_cell]])
print(f"Обновлена строка {target_row} для {SEED_ID}, len={len(new_cell)}")