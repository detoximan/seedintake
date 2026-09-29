"""Создать лист 'Magic Mind' в Google Sheets и заполнить данными из файла MagicMind."""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE / "src"))

from seed_pipeline.integrations import LiveGoogleWorkspace
from seed_pipeline.integrations.google_workspace_live import _build_sheets_service, LiveGoogleWorkspaceConfig

# --- Config ---
TRANS_MARKER = "===================="
NEW_SHEET_NAME = "Magic Mind"
MAGICMIND_FILE = BASE.parent.parent / "MagicMind"

# --- Init ---
config = LiveGoogleWorkspaceConfig.from_env()
service = _build_sheets_service(config)
ws = LiveGoogleWorkspace(config=config, sheets_service=service)

# --- Step 1: Read MagicMind file ---
print("Читаю файл MagicMind...")
mm_text = MAGICMIND_FILE.read_text(encoding="utf-8")

# Parse entries: [ID](link) | annotation
entries = []
for line in mm_text.split("\n"):
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("=="):
        continue
    m = re.match(r'\[([^\]]+)\]\([^)]+\)\s*\|\s*(.*)', line)
    if m:
        entry_id = m.group(1).strip()
        annotation = m.group(2).strip()
        entries.append((entry_id, annotation))

print(f"Найдено записей в MagicMind: {len(entries)}")

# --- Step 2: Read main sheet with hyperlinks ---
print("Читаю основной лист с гиперссылками...")
result = service.spreadsheets().get(
    spreadsheetId=config.sheet_id,
    fields="sheets.properties,sheets.data.rowData.values.userEnteredValue,sheets.data.rowData.values.hyperlink"
).execute()

sheets = result.get("sheets", [])
main_sheet = sheets[0] if sheets else None
if not main_sheet:
    print("ОШИБКА: нет листов в таблице")
    sys.exit(1)

main_sheet_id = main_sheet["properties"]["sheetId"]
main_sheet_title = main_sheet["properties"].get("title", "Лист1")
print(f"ID основного листа: {main_sheet_id}, название: {main_sheet_title}")

id_col_idx = ws.get_column_index("ID", sheet_name=main_sheet_title)
trans_col_idx = ws.get_column_index("Транскрибация источника", sheet_name=main_sheet_title)

# Build map: seed_id -> github_url
row_data = main_sheet.get("data", [{}])[0].get("rowData", [])
id_to_github = {}
for i, row in enumerate(row_data):
    if i == 0:
        continue  # skip header
    cells = row.get("values", [])
    if len(cells) <= id_col_idx:
        continue
    cell_id = cells[id_col_idx]
    cell_value = cell_id.get("userEnteredValue", {}).get("stringValue", "")
    hyperlink = cell_id.get("hyperlink", "")
    if cell_value and hyperlink:
        id_to_github[cell_value.strip()] = hyperlink

print(f"Найдено ID с гиперссылками в основном листе: {len(id_to_github)}")

# --- Step 3: Read main sheet cell values (for Russian text) ---
print("Читаю содержимое ячеек основного листа...")
rows_values = ws.get_all_rows(sheet_name=main_sheet_title)
id_to_cell_trans = {}
for i, row in enumerate(rows_values):
    if i == 0:
        continue
    cell_id = row[id_col_idx].strip() if len(row) > id_col_idx else ""
    cell_trans = row[trans_col_idx] if len(row) > trans_col_idx else ""
    if cell_id:
        id_to_cell_trans[cell_id] = cell_trans

print(f"Найдено строк с контентом: {len(id_to_cell_trans)}")

# --- Step 4: Create new sheet ---
print(f"Создаю лист '{NEW_SHEET_NAME}'...")
try:
    add_sheet_response = service.spreadsheets().batchUpdate(
        spreadsheetId=config.sheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": NEW_SHEET_NAME
                        }
                    }
                }
            ]
        }
    ).execute()
    new_sheet_id = add_sheet_response["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"Лист создан, sheetId={new_sheet_id}")
except Exception as e:
    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
        print(f"Лист '{NEW_SHEET_NAME}' уже существует, используем его.")
        # Find existing sheet
        ss = service.spreadsheets().get(spreadsheetId=config.sheet_id).execute()
        for s in ss["sheets"]:
            if s["properties"]["title"] == NEW_SHEET_NAME:
                new_sheet_id = s["properties"]["sheetId"]
                break
    else:
        raise

# --- Step 5: Write headers ---
print("Проверяю заголовки...")
mm_headers = ws.get_header_row(sheet_name=NEW_SHEET_NAME)
if not mm_headers:
    print("Записываю заголовки...")
    service.spreadsheets().values().update(
        spreadsheetId=config.sheet_id,
        range=f"'{NEW_SHEET_NAME}'!A1:C1",
        valueInputOption="RAW",
        body={"values": [["ID", "Выдержка", "Полный русский текст"]]}
    ).execute()
else:
    print(f"Заголовки листа '{NEW_SHEET_NAME}' уже существуют: {mm_headers}. Служебные колонки не перезаписываются.")

# --- Step 6: Build rows ---
print("Формирую строки для записи...")
rows_to_write = []
links_to_write = []  # for batchUpdate with hyperlinks

for entry_id, annotation in entries:
    # Get GitHub link
    github_url = id_to_github.get(entry_id, "")
    
    # Get Russian text from source
    cell_trans = id_to_cell_trans.get(entry_id, "")
    russian_text = ""
    if cell_trans and TRANS_MARKER in cell_trans:
        parts = cell_trans.split(TRANS_MARKER, 1)
        russian_text = parts[1].strip() if len(parts) > 1 else ""
    elif cell_trans:
        russian_text = cell_trans.strip()
    
    rows_to_write.append([entry_id, annotation, russian_text])
    links_to_write.append((entry_id, github_url))

print(f"Подготовлено строк: {len(rows_to_write)}")

# --- Step 7: Write data (values first) ---
print("Записываю данные в колонки A:C (служебные колонки не затрагиваются)...")
service.spreadsheets().values().update(
    spreadsheetId=config.sheet_id,
    range=f"'{NEW_SHEET_NAME}'!A2:C",
    valueInputOption="RAW",
    body={"values": rows_to_write}
).execute()

# --- Step 8: Add hyperlinks to column A ---
print("Добавляю гиперссылки в колонку A...")
requests = []
for i, (entry_id, github_url) in enumerate(links_to_write):
    if github_url:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": new_sheet_id,
                    "startRowIndex": i + 1,
                    "endRowIndex": i + 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1
                },
                "cell": {
                    "userEnteredValue": {"stringValue": entry_id},
                    "userEnteredFormat": {
                        "textFormat": {
                            "link": {"uri": github_url}
                        }
                    }
                },
                "fields": "userEnteredValue,userEnteredFormat.textFormat.link"
            }
        })

# Batch in chunks of 100
for chunk_start in range(0, len(requests), 100):
    chunk = requests[chunk_start:chunk_start + 100]
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.sheet_id,
        body={"requests": chunk}
    ).execute()
    print(f"  Гиперссылки: обработано {chunk_start + len(chunk)} / {len(requests)}")

print(f"\nГОТОВО! Лист '{NEW_SHEET_NAME}' создан и заполнен {len(rows_to_write)} строками.")
