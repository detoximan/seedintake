"""Apply bilingual translation to slim, full, and Google Sheets."""
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root / "services" / "seed_pipeline" / "src"))

load_dotenv(repo_root / "services" / "seed_pipeline" / ".env")

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace

def apply_translation(seed_id: str, russian_translation: str):
    year = seed_id.split("-")[0]
    slim_path = repo_root / "Inbox" / year / "slim" / f"{seed_id}-s.md"
    full_path = repo_root / "Inbox" / year / "full" / f"{seed_id}-f.md"

    if not slim_path.exists() or not full_path.exists():
        raise FileNotFoundError(f"Files for {seed_id} not found")

    slim_content = slim_path.read_text(encoding="utf-8")
    full_content = full_path.read_text(encoding="utf-8")

    # Extract source content from slim
    # Source is after '# Источник\n\n'
    source_marker = "# Источник\n\n"
    if source_marker not in slim_content:
        raise ValueError(f"No '# Источник' in {slim_path}")

    header_part, original_source = slim_content.split(source_marker, 1)
    original_source = original_source.strip()

    # If already translated, get the original part before '===================='
    if "====================" in original_source:
        original_source = original_source.split("====================")[0].strip()

    bilingual_text = f"{original_source}\n\n====================\n\n{russian_translation.strip()}\n"

    # Update slim file
    # Ensure status: processed
    header_part = re.sub(r"^status:\s*\w+", "status: processed", header_part, flags=re.M)
    new_slim = f"{header_part}{source_marker}{bilingual_text}"
    slim_path.write_text(new_slim, encoding="utf-8")

    # Update full file
    full_marker = "# Транскрибация / текст источника\n\n"
    tech_marker = "\n# Технические сведения"
    if full_marker not in full_content or tech_marker not in full_content:
        raise ValueError(f"Markers not found in {full_path}")

    f_top, f_rest = full_content.split(full_marker, 1)
    _, f_bottom = f_rest.split(tech_marker, 1)
    f_top = re.sub(r"^status:\s*\w+", "status: processed", f_top, flags=re.M)
    new_full = f"{f_top}{full_marker}{bilingual_text}{tech_marker}{f_bottom}"
    full_path.write_text(new_full, encoding="utf-8")

    # Update Google Sheet
    ws = LiveGoogleWorkspace.from_env()
    rows = ws.get_all_rows()
    target_row_idx = None
    for idx, row in enumerate(rows):
        if row and seed_id in row[0]:
            target_row_idx = idx + 1
            break

    if target_row_idx:
        ws.update_range(f"E{target_row_idx}", [[bilingual_text.strip()]])
        print(f"Updated Google Sheet row {target_row_idx} for {seed_id}")
    else:
        print(f"WARNING: Row for {seed_id} not found in Google Sheet")

    print(f"Successfully applied translation for {seed_id}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 apply_translation.py <seed_id> <translation_file_or_text>")
        sys.exit(1)
    seed_id = sys.argv[1]
    trans_arg = sys.argv[2]
    if os.path.exists(trans_arg):
        trans_text = Path(trans_arg).read_text(encoding="utf-8")
    else:
        trans_text = trans_arg
    apply_translation(seed_id, trans_text)
