"""Загрузка результатов анализа СИЛАЧ в отдельный лист Google Таблицы."""
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE / "src"))

from seed_pipeline.integrations.google_workspace_live import _build_sheets_service, LiveGoogleWorkspaceConfig

SHEET_TITLE = "Silach Analysis"
JSON_FILE = BASE.parent.parent / "runtime" / "silach_analysis.json"

config = LiveGoogleWorkspaceConfig.from_env()
service = _build_sheets_service(config)

print(f"Читаю данные из {JSON_FILE}...")
items = json.loads(JSON_FILE.read_text(encoding="utf-8"))

# Проверяем или создаем лист
ss = service.spreadsheets().get(spreadsheetId=config.sheet_id).execute()
sheet_id = None
for s in ss.get("sheets", []):
    if s["properties"]["title"] == SHEET_TITLE:
        sheet_id = s["properties"]["sheetId"]
        break

if sheet_id is None:
    print(f"Создаю новый лист '{SHEET_TITLE}'...")
    res = service.spreadsheets().batchUpdate(
        spreadsheetId=config.sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": SHEET_TITLE}}}]}
    ).execute()
    sheet_id = res["replies"][0]["addSheet"]["properties"]["sheetId"]
else:
    print(f"Лист '{SHEET_TITLE}' уже существует (id={sheet_id}). Очищаю...")
    service.spreadsheets().values().clear(
        spreadsheetId=config.sheet_id,
        range=f"'{SHEET_TITLE}'!A:Z"
    ).execute()

# Формируем строки данных
headers = ["ID", "Зона", "Стратегия", "Аудитория", "Суть ролика", "Разбор СИЛАЧ / Стоицизм"]
rows = [headers]

for item in items:
    rows.append([
        item["id"],
        item["zone"],
        item["strategic_type"],
        item["audience_fit"],
        item["summary"],
        item["silach_reframe"]
    ])

# Записываем значения
print("Записываю значения...")
service.spreadsheets().values().update(
    spreadsheetId=config.sheet_id,
    range=f"'{SHEET_TITLE}'!A1",
    valueInputOption="USER_ENTERED",
    body={"values": rows}
).execute()

# Форматирование и гиперссылки
print("Применяю стили и гиперссылки...")
requests = [
    # Замораживаем первую строку
    {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1}
            },
            "fields": "gridProperties.frozenRowCount"
        }
    },
    # Стиль заголовка: темно-серый фон, белый жирный текст, центрирование
    {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": 6
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.2, "green": 0.25, "blue": 0.3},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "fontSize": 10},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "WRAP"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)"
        }
    },
    # Выравнивание и перенос текста для строк данных
    {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": len(rows),
                "startColumnIndex": 0,
                "endColumnIndex": 6
            },
            "cell": {
                "userEnteredFormat": {
                    "verticalAlignment": "TOP",
                    "wrapStrategy": "WRAP"
                }
            },
            "fields": "userEnteredFormat(verticalAlignment,wrapStrategy)"
        }
    },
    # Центрирование для колонок B, C, D (Зона, Стратегия, Аудитория)
    {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": len(rows),
                "startColumnIndex": 1,
                "endColumnIndex": 4
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "CENTER"
                }
            },
            "fields": "userEnteredFormat.horizontalAlignment"
        }
    }
]

# Настройка ширины колонок
column_widths = [
    (0, 1, 130),  # ID
    (1, 2, 90),   # Зона
    (2, 3, 160),  # Стратегия
    (3, 4, 100),  # Аудитория
    (4, 5, 320),  # Суть
    (5, 6, 600),  # Разбор СИЛАЧ
]

for start_col, end_col, width in column_widths:
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": start_col,
                "endIndex": end_col
            },
            "properties": {"pixelSize": width},
            "fields": "pixelSize"
        }
    })

# Цвета для зон и ссылки на GitHub
zone_colors = {
    "GREEN": {"red": 0.85, "green": 0.93, "blue": 0.83},   # пастельный зеленый
    "YELLOW": {"red": 1.0, "green": 0.95, "blue": 0.80},    # пастельный желтый
    "RED": {"red": 0.97, "green": 0.84, "blue": 0.84}       # пастельный красный
}

for i, item in enumerate(items):
    row_idx = i + 1
    zone = item["zone"]
    github_link = f"https://github.com/detoximan/seedintake/blob/main/Inbox/2026/full/{item['id']}-f.md"
    
    # Гиперссылка в ID
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_idx,
                "endRowIndex": row_idx + 1,
                "startColumnIndex": 0,
                "endColumnIndex": 1
            },
            "cell": {
                "userEnteredValue": {"stringValue": item["id"]},
                "userEnteredFormat": {
                    "textFormat": {
                        "link": {"uri": github_link},
                        "underline": True,
                        "foregroundColor": {"red": 0.1, "green": 0.35, "blue": 0.75}
                    }
                }
            },
            "fields": "userEnteredValue,userEnteredFormat.textFormat"
        }
    })
    
    # Цветная подсветка зоны
    if zone in zone_colors:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_idx,
                    "endRowIndex": row_idx + 1,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": zone_colors[zone],
                        "textFormat": {"bold": True}
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat.bold)"
            }
        })

service.spreadsheets().batchUpdate(
    spreadsheetId=config.sheet_id,
    body={"requests": requests}
).execute()

print(f"Готово! Лист '{SHEET_TITLE}' успешно создан и оформлен.")
