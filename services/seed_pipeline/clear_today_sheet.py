"""Clear today's seed rows from Google Sheet (2026-07-12)."""
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace, LiveGoogleWorkspaceConfig

def main():
    config = LiveGoogleWorkspaceConfig.from_env()
    ws = LiveGoogleWorkspace(config=config)
    
    # Get all rows
    rows = ws.get_all_rows()
    print(f"Total rows in sheet: {len(rows)}")
    
    # Find rows to delete (header + today's seeds)
    today_prefix = "2026-07-12-"
    rows_to_delete = []
    
    for i, row in enumerate(rows):
        if row and row[0].startswith(today_prefix):
            rows_to_delete.append(i)
            print(f"  Found row {i+1}: {row[0]} -> {row[3][:50] if len(row) > 3 else 'no comment'}")
    
    if not rows_to_delete:
        print("No today's rows found in sheet.")
        return
    
    # Delete from bottom to top so indices stay valid
    # We need to use batchUpdate with deleteDimension requests
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    credentials = service_account.Credentials.from_service_account_file(
        config.credentials_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    
    # Get the sheet ID
    sheet_id = ws._target_sheet_gid()
    
    requests = []
    for idx in reversed(rows_to_delete):
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": idx,  # 0-based
                    "endIndex": idx + 1,
                }
            }
        })
    
    body = {"requests": requests}
    result = service.spreadsheets().batchUpdate(
        spreadsheetId=config.sheet_id,
        body=body,
    ).execute()
    
    print(f"Deleted {len(rows_to_delete)} rows from sheet.")

if __name__ == "__main__":
    main()