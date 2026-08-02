"""Ручной перевод следующей партии из 10 строк."""
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ws = LiveGoogleWorkspace.from_env()
rows = ws.get_all_rows()

target_rows = [336, 335, 334, 330, 329, 328, 327, 326, 325, 324]

for row_num in target_rows:
    idx = row_num - 1
    row = rows[idx]
    col_a = row[0] if len(row) > 0 else ""
    col_e = row[4] if len(row) > 4 else ""
    print(f"=== row={row_num} | id={col_a} ===")
    print(col_e)
    print("\n")