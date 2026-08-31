import re
from pathlib import Path
from dotenv import load_dotenv

# Load env from current directory or relative path
load_dotenv(Path(__file__).parent / ".env")

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace

GITHUB_BASE_URL = "https://github.com/detoximan/seedintake/blob/main/Inbox/2026/full"

def restore_column_a_links():
    ws = LiveGoogleWorkspace.from_env()
    spreadsheet_id = ws.config.sheet_id
    
    # 1. Fetch current rows
    res = ws.sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=["Лист1!A:A"],
        fields="sheets(data(rowData(values(userEnteredValue,userEnteredFormat,formattedValue,hyperlink))))"
    ).execute()
    
    rows = res["sheets"][0]["data"][0].get("rowData", [])
    print(f"Total rows found in sheet: {len(rows)}")
    
    updates = []
    
    for idx, r in enumerate(rows):
        if idx == 0:
            continue  # Header row
        vals = r.get("values", [])
        if not vals:
            continue
        text = (vals[0].get("formattedValue") or vals[0].get("userEnteredValue", {}).get("stringValue") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}-\d{3}$", text):
            continue
            
        full_url = f"{GITHUB_BASE_URL}/{text}-f.md"
        current_link = vals[0].get("hyperlink") or vals[0].get("userEnteredFormat", {}).get("textFormat", {}).get("link", {}).get("uri")
        
        # Prepare cell structure
        cell_data = {
            "userEnteredValue": {"stringValue": text},
            "userEnteredFormat": {
                "wrapStrategy": "WRAP",
                "textFormat": {
                    "fontSize": 8,
                    "link": {"uri": full_url}
                }
            }
        }
        
        updates.append({
            "rowIndex": idx,
            "seed_id": text,
            "url": full_url,
            "cell": cell_data,
            "was_missing": not bool(current_link)
        })
        
    print(f"Total valid seed rows to update/verify: {len(updates)}")
    missing_count = sum(1 for u in updates if u["was_missing"])
    print(f"Rows needing link restoration: {missing_count}")
    
    if not updates:
        print("No rows to update.")
        return
        
    # 2. Batch update in chunks of 200
    chunk_size = 200
    for chunk_start in range(0, len(updates), chunk_size):
        chunk = updates[chunk_start:chunk_start + chunk_size]
        start_row_idx = chunk[0]["rowIndex"]
        end_row_idx = chunk[-1]["rowIndex"] + 1
        
        # Build contiguous row list for range [start_row_idx, end_row_idx]
        row_map = {u["rowIndex"]: u["cell"] for u in chunk}
        chunk_rows = []
        for r_idx in range(start_row_idx, end_row_idx):
            if r_idx in row_map:
                chunk_rows.append({"values": [row_map[r_idx]]})
            else:
                chunk_rows.append({"values": [{}]})
                
        request_body = {
            "requests": [
                {
                    "updateCells": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": start_row_idx,
                            "endRowIndex": end_row_idx,
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                        },
                        "rows": chunk_rows,
                        "fields": "userEnteredValue,userEnteredFormat.textFormat.link,userEnteredFormat.wrapStrategy,userEnteredFormat.textFormat.fontSize"
                    }
                }
            ]
        }
        
        ws.sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=request_body
        ).execute()
        print(f"Updated rows {start_row_idx + 1} to {end_row_idx}")

    print("Restoration batchUpdate finished. Verifying...")
    verify_links()

def verify_links():
    ws = LiveGoogleWorkspace.from_env()
    spreadsheet_id = ws.config.sheet_id
    
    res = ws.sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=["Лист1!A:A"],
        fields="sheets(data(rowData(values(userEnteredValue,userEnteredFormat,formattedValue,hyperlink))))"
    ).execute()
    
    rows = res["sheets"][0]["data"][0].get("rowData", [])
    
    total_valid = 0
    correct_links = 0
    errors = []
    
    for idx, r in enumerate(rows):
        if idx == 0:
            continue
        vals = r.get("values", [])
        if not vals:
            continue
        text = (vals[0].get("formattedValue") or vals[0].get("userEnteredValue", {}).get("stringValue") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}-\d{3}$", text):
            continue
            
        total_valid += 1
        expected_url = f"{GITHUB_BASE_URL}/{text}-f.md"
        actual_link = vals[0].get("hyperlink") or vals[0].get("userEnteredFormat", {}).get("textFormat", {}).get("link", {}).get("uri")
        
        if actual_link == expected_url:
            correct_links += 1
        else:
            errors.append((idx + 1, text, actual_link, expected_url))
            
    print("\n=== VERIFICATION RESULTS ===")
    print(f"Total valid seed rows: {total_valid}")
    print(f"Correctly linked rows: {correct_links}")
    print(f"Errors: {len(errors)}")
    if errors:
        print("Sample errors:")
        for err in errors[:5]:
            print(f"  Row {err[0]}: ID={err[1]}, actual={err[2]}, expected={err[3]}")
    else:
        print("All rows in column A are 100% correctly linked to their GitHub full markdown files!")

if __name__ == "__main__":
    restore_column_a_links()
