"""
Генерация вкладки 'Связки 7 болей' в Google Sheets.
Анализ роликов из 'Лист1' на 7 болей клиентов с генерацией коротких разговорных CTA.
"""
import os
import re
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE / "src"))

from seed_pipeline.integrations import LiveGoogleWorkspace
from seed_pipeline.integrations.google_workspace_live import _build_sheets_service, LiveGoogleWorkspaceConfig

SHEET_TITLE = "Связки 7 болей"

# Описание 7 болей клиентов
PAIN_DEFINITIONS = {
    1: {
        "title": "1. «Я вроде все понимаю, но ничего не могу с собой сделать»",
        "must_have_any": [
            "мозг", "мысл", "привычк", "понима", "знаю", "повторяет", "замкнут",
            "срыв", "сценари", "самосаботаж", "автоматиз", "грабл", "головой",
            "паттерн", "действова", "делаю", "прокрастинац", "контрол"
        ],
        "keywords": {
            "мозг": 3, "мысли": 2, "привычк": 4, "повторяет": 4, "понима": 3,
            "срыв": 4, "замкнут": 5, "самосаботаж": 6, "грабл": 6, "головой": 3,
            "автоматиз": 4, "паттерн": 4, "знаю": 2, "сценари": 4, "разорвать": 4,
            "перестроит": 3, "внутренний диалог": 5, "нейро": 4
        },
        "cta_pool": [
            "Вроде всё понимаешь головой, но ничего не меняется? Смотри видео в закрепе. Показал, как разорвать этот круг.",
            "Ну, а если умом всё понимаешь, а по факту повторяешь то же самое, смотри видео в закрепе. Там показал, как это прекратить.",
            "Знаешь, как правильно, но всё равно срываешься? Загляни в закрепленное видео. Там дал простой способ перестроить поведение.",
            "Понимаешь всё головой, а эмоции делают по-своему? Смотри прикрепленное видео. Показал, как выйти из этого сценария.",
            "Если устал обещать себе начать жить иначе и снова наступать на те же грабли — смотри видео в закрепе. Там короткая инструкция.",
            "Устал бороться с собой и всё саботировать? Смотри видео в закрепе. Показал, как убрать автоматические срывы.",
            "Вроде начитался умных книг, а легче не становится? Смотри прикрепленное видео. Там показал, что делать на практике."
        ]
    },
    2: {
        "title": "2. «Мне кажется, я слишком остро реагирую»",
        "must_have_any": [
            "слез", "плач", "обид", "задел", "остро", "виню", "чувств", "эмоци",
            "ранимость", "взрыв", "истерик", "пустяк", "мелоч", "близко к сердцу",
            "крик", "ссора", "сдержива", "ругаю себя"
        ],
        "keywords": {
            "слез": 4, "плач": 4, "обид": 4, "задел": 4, "остро": 5, "виню": 4,
            "ранимост": 5, "взрыв": 4, "истерик": 5, "пустяк": 4, "мелоч": 3,
            "близко к сердцу": 5, "ругаю себя": 5, "сдержат": 3, "стыдно за чувства": 6,
            "обесценива": 4, "триггер": 3, "чувствительн": 4
        },
        "cta_pool": [
            "Кажется, что слишком остро на всё реагируешь, а потом винишь себя? Смотри видео в закрепе. Показал, как перестать обесценивать свои чувства.",
            "Если тебя задевает любая мелочь и ты думаешь, что с тобой что-то не так, смотри видео в закрепе. Там объяснил, откуда это берется.",
            "Постоянно ругаешь себя за слезы и вспышки эмоций? Загляни в закрепленное видео. Показал, как перестать воевать со своими чувствами.",
            "Ну, а если принимаешь всё слишком близко к сердцу и устала от качелей, смотри видео в закрепе. Там простой разбор.",
            "Сказали ерунду, а ты потом весь вечер ревешь и коришь себя? Смотри видео в закрепе. Показал, о чем говорят эти слезы.",
            "Чувствуешь себя «ненормальной» из-за того, что всё ранит? Смотри прикрепленное видео. Там объяснил, как вернуть эмоциональную броню."
        ]
    },
    3: {
        "title": "3. «Он вроде хороший, но мне с ним плохо»",
        "must_have_any": [
            "муж", "партнер", "парень", "мужчин", "отношен", "брак", "одиночеств",
            "холод", "обесценив", "пустот", "не слышит", "тошно", "не цен", "любов",
            "измен", "расставан", "развод", "ссоры", "непониман"
        ],
        "keywords": {
            "муж": 3, "мужчин": 3, "партнер": 4, "отношен": 3, "брак": 3,
            "одиночеств": 5, "холод": 4, "обесценив": 5, "не слышит": 5, "пустот": 4,
            "тошно": 4, "не цен": 4, "дистанци": 3, "развод": 3, "чужие": 4,
            "терпеть": 3, "предательств": 4, "сомнева": 3, "вдвоем": 3
        },
        "cta_pool": [
            "Если со стороны он вроде хороший, но рядом с ним тебе паршиво, смотри видео в закрепе. Там объяснил, что происходит на самом деле.",
            "Партнер вроде нормальный, но внутри пустота и холод? Смотри прикрепленное видео. Показал, почему так бывает и что делать.",
            "Живешь с постоянным чувством одиночества вдвоем? Смотри видео в закрепе. Там просто показал, как разобраться в этих отношениях.",
            "Вроде не бьет и деньги приносит, а на душе тошно? Загляни в закрепленное видео. Объяснил, о чем кричит это состояние.",
            "Сомневаешься, есть ли смысл спасать эти отношения? Смотри видео в закрепе. Показал, как понять, твой ли это человек.",
            "Устала чувствовать себя невидимкой рядом с любимым? Смотри видео в закрепе. Там коротко показал, где корень проблемы."
        ]
    },
    4: {
        "title": "4. «Я устала быть сильной»",
        "must_have_any": [
            "устал", "сил", "тащ", "тян", "контрол", "выгоран", "истощен", "опор",
            "расслаб", "сама", "паха", "всех на себе", "помощ", "ответственност"
        ],
        "keywords": {
            "устал": 4, "сильн": 4, "тащ": 5, "тян": 4, "контрол": 4, "выгоран": 5,
            "истощен": 5, "опор": 4, "расслаб": 4, "сама": 3, "паха": 4, "на себе": 4,
            "железная": 5, "спасател": 5, "помощ": 3, "отпустить": 3
        },
        "cta_pool": [
            "Ну, а если ты устала быть сильной и тащить всё на себе, смотри видео в закрепе. Показал, как сбросить этот груз.",
            "Задолбалась всё контролировать и быть железной? Смотри видео в закрепе. Там просто показал, как выдохнуть и отпустить.",
            "Чувствуешь, что батарейка на нуле, а опереться не на кого? Смотри видео в закрепе. Показал, с чего начать восстановление.",
            "Устала тянуть семью, работу и всех вокруг? Смотри прикрепленное видео. Там по шагам объяснил, как перестать быть спасателем.",
            "Боишься расслабиться, потому что без тебя всё рухнет? Загляни в видео в закрепе. Показал, как вернуть баланс без страха.",
            "Надоело быть мужиком в отношениях? Смотри видео в закрепе. Там показал, как скинуть лишнюю ответственность."
        ]
    },
    5: {
        "title": "5. «Наверное, это не настолько серьезно, чтобы идти к психологу»",
        "must_have_any": [
            "терп", "тревог", "апати", "мелоч", "ерунд", "несерьезн", "жаловат",
            "привыкл", "радост", "страх", "нормальн", "потерпеть", "отказать",
            "стыдно", "грех жаловаться"
        ],
        "keywords": {
            "терп": 4, "тревог": 4, "апати": 5, "мелоч": 4, "несерьезн": 5,
            "жаловат": 4, "привыкл": 3, "радост": 3, "потерпет": 4, "отказат": 4,
            "грех жаловаться": 6, "ерунда": 4, "дискомфорт": 4, "фонов": 4
        },
        "cta_pool": [
            "Думаешь, твоя проблема ерунда и не стоит внимания? Смотри видео в закрепе. Показал, как такие «мелочи» годами сжирают жизнь.",
            "Кажется, что идти к психологу из-за этого глупо и надо просто потерпеть? Смотри видео в закрепе. Там объяснил, почему это опасно.",
            "Привыкла терпеть дискомфорт и думаешь, что у других хуже? Загляни в видео в закрепе. Показал, почему нельзя забивать на себя.",
            "Если кажется, что твоя тревога не повод для помощи, смотри прикрепленное видео. Там просто показал, как вернуть радость в жизнь.",
            "Годами терпишь серость и думаешь, что это норма? Смотри видео в закрепе. Показал, как наконец начать жить для себя."
        ]
    },
    6: {
        "title": "6. «А вдруг я приду, а там ничего такого»",
        "must_have_any": [
            "выдум", "глуп", "стыд", "осуд", "боюсь", "самозван", "накрут",
            "оцен", "показаться", "смешно", "не поверят", "зря", "специалист"
        ],
        "keywords": {
            "выдум": 5, "глуп": 4, "стыд": 4, "осуд": 4, "самозван": 5,
            "накрут": 5, "показаться": 4, "смешно": 4, "зря": 3, "не поверят": 5,
            "обесценят": 4, "оценят": 4
        },
        "cta_pool": [
            "Боишься, что придешь на разбор, а тебе скажут, что ты всё выдумала? Смотри видео в закрепе. Показал, как всё устроено на самом деле.",
            "Страшно показаться глупым перед специалистом? Смотри видео в закрепе. Там объяснил, почему тебя точно никто не осудит.",
            "Думаешь, что зря отнимешь время или твои проблемы смешны? Загляни в видео в закрепе. Показал, как проходит первая встреча.",
            "Боишься услышать «с вами всё нормально, не накручивайте»? Смотри прикрепленное видео. Там на пальцах показал, как всё устроено."
        ]
    },
    7: {
        "title": "7. «Я не знаю, с чего начать»",
        "must_have_any": [
            "начат", "хаос", "тупик", "навалил", "запута", "шаг", "кризис",
            "клубок", "каша", "план", "растерянност", "простраци", "куда бежать",
            "с чего", "не знаю что делать"
        ],
        "keywords": {
            "начат": 4, "хаос": 5, "тупик": 5, "навалил": 5, "запута": 5,
            "шаг": 3, "кризис": 4, "клубок": 6, "каша": 5, "растерянност": 5,
            "куда бежать": 5, "не знаю": 3, "ступор": 5
        },
        "cta_pool": [
            "Навалилось так много всего, что не знаешь, за что хвататься? Смотри видео в закрепе. Там просто показал, как сделать первый шаг.",
            "Каша в голове и не понимаешь, с чего начать распутывать этот клубок? Смотри прикрепленное видео. Дал предельно простой алгоритм.",
            "Чувствуешь полный ступор и не знаешь, куда двигаться дальше? Смотри видео в закрепе. Показал, с чего начать наводить порядок.",
            "Запуталась в проблемах и нет сил разбираться? Загляни в закрепленное видео. Там пошагово показал самый первый простой шаг.",
            "Проблем накопилось столько, что опускаются руки? Смотри видео в закрепе. Показал простой ориентир, с чего начать выход."
        ]
    }
}


def clean_text(raw: str) -> str:
    """Очищает текст от служебных отметок, заголовков и скобок."""
    if not raw:
        return ""
    if "====================" in raw:
        raw = raw.split("====================", 1)[1]
    
    lines = []
    for line in raw.split("\n"):
        l = line.strip()
        if not l:
            continue
        # Пропуск служебных заголовков
        if re.match(r"^[123]\s*[–-]\s*(Текст на фото|Транскрибация|Текст под медиа):?", l, re.IGNORECASE):
            continue
        if l.lower() in ("нет", "нет (ошибка получения метаданных)", "текста нет", "no"):
            continue
        # Удаление файловых меток [DXGOJpcjNmU...jpg]: или [7428...mp4]:
        l = re.sub(r"^.*?\]:\s*", "", l)
        l = re.sub(r"\[.*?\]", "", l)
        l = re.sub(r"#\w+", "", l)
        l = re.sub(r"\s+", " ", l).strip()
        if l and len(l) > 3:
            lines.append(l)
            
    return " ".join(lines).strip()


def score_text_for_pain(text_lower: str, pain_id: int) -> float:
    """Вычисляет процент релевантности (0-100) текста к боли."""
    p_def = PAIN_DEFINITIONS[pain_id]
    
    # 1. Проверяем обязательное наличие хотя бы одного корневого маркера темы
    must_have = p_def["must_have_any"]
    if not any(mh in text_lower for mh in must_have):
        return 0.0
        
    # 2. Подсчет весов совпадений
    keywords = p_def["keywords"]
    raw_score = 0.0
    matched_keys = 0
    
    for kw, weight in keywords.items():
        count = len(re.findall(re.escape(kw), text_lower))
        if count > 0:
            matched_keys += 1
            raw_score += min(count, 3) * weight
            
    # Контекстные фильтры
    if pain_id == 3:  # Отношения
        rel_tokens = ["муж", "партнер", "парень", "отношен", "брак", "мужчин", "женщин", "любов"]
        if not any(rt in text_lower for rt in rel_tokens):
            return 0.0
    elif pain_id == 4:  # Устала быть сильной
        strong_tokens = ["устал", "тащ", "тян", "сил", "выгоран", "на себе", "сам"]
        if not any(st in text_lower for st in strong_tokens):
            return 0.0
            
    # Требуем минимум 2 совпавших ключевика и базовый порог
    if matched_keys < 2 or raw_score < 10.0:
        return 0.0
        
    # Формула процента: от 52% до 98%
    pct = 50.0 + min(46.0, (raw_score / 45.0) * 44.0)
    return round(pct, 1)


def pick_cta(pain_id: int, seed_idx: int) -> str:
    pool = PAIN_DEFINITIONS[pain_id]["cta_pool"]
    return pool[seed_idx % len(pool)]


def main():
    config = LiveGoogleWorkspaceConfig.from_env()
    service = _build_sheets_service(config)
    ws = LiveGoogleWorkspace(config=config, sheets_service=service)

    print("Читаю данные из 'Лист1'...")
    main_rows = ws.get_all_rows("Лист1")
    if not main_rows:
        print("Ошибка: Лист1 пуст.")
        return

    # Загружаем соответствие seed_id -> оригинальный URL
    links_dir = BASE.parent.parent / "Inbox" / "2026" / "links"
    seed_to_url = {}
    for f in links_dir.glob("*-link.md"):
        content = f.read_text(encoding="utf-8")
        m_url = re.search(r"url:\s*(.+)", content)
        m_id = re.search(r"processed_seed_id:\s*(.+)", content)
        url = m_url.group(1).strip() if m_url else ""
        sid = m_id.group(1).strip() if m_id else f.stem.replace("-link", "")
        if sid:
            seed_to_url[sid] = url

    print("Анализ роликов...")
    matches = []
    
    for idx, row in enumerate(main_rows[1:], start=1):
        sid = row[0].strip() if len(row) > 0 else ""
        raw_mat = row[4].strip() if len(row) > 4 else ""
        
        cleaned = clean_text(raw_mat)
        if len(cleaned) < 50:
            continue
            
        url = seed_to_url.get(sid, "")
        text_lower = cleaned.lower()
        
        # Скоринг по 7 болям
        scored_pains = []
        for p_id in range(1, 8):
            pct = score_text_for_pain(text_lower, p_id)
            if pct > 50.0:
                scored_pains.append((p_id, pct))
                
        scored_pains.sort(key=lambda x: x[1], reverse=True)
        
        # Если ролик подходит сразу под несколько болей — добавляем отдельные строки (до 2 лучших)
        for rank, (p_id, pct) in enumerate(scored_pains[:2]):
            cta = pick_cta(p_id, idx + rank * 3)
            matches.append({
                "id": sid,
                "url": url,
                "cleaned_text": cleaned,
                "pain_title": PAIN_DEFINITIONS[p_id]["title"],
                "score": f"{pct}%",
                "cta": cta
            })

    print(f"Всего отобрано связок: {len(matches)}")
    
    # Сохраняем локальный дамп
    runtime_dir = BASE.parent.parent / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    dump_path = runtime_dir / "7_pains_analysis.json"
    dump_path.write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Локальный дамп сохранен в {dump_path}")

    # --- Работа с Google Sheets ---
    print(f"Проверяю наличие вкладки '{SHEET_TITLE}'...")
    ss_meta = service.spreadsheets().get(spreadsheetId=config.sheet_id).execute()
    sheets = ss_meta.get("sheets", [])
    target_sheet_id = None
    for s in sheets:
        if s["properties"]["title"] == SHEET_TITLE:
            target_sheet_id = s["properties"]["sheetId"]
            break
            
    if target_sheet_id is None:
        print(f"Создаю новый лист '{SHEET_TITLE}'...")
        res = service.spreadsheets().batchUpdate(
            spreadsheetId=config.sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": SHEET_TITLE}}}]}
        ).execute()
        target_sheet_id = res["replies"][0]["addSheet"]["properties"]["sheetId"]
        print(f"Лист создан, ID={target_sheet_id}")
    else:
        print(f"Лист '{SHEET_TITLE}' уже существует (ID={target_sheet_id}). Очищаю диапазон A2:I...")
        service.spreadsheets().values().clear(
            spreadsheetId=config.sheet_id,
            range=f"'{SHEET_TITLE}'!A2:I"
        ).execute()

    # Заголовки
    headers = [
        "ID",
        "URL ролика",
        "Чистый текст ролика",
        "Боль / Триггерная фраза",
        "Совпадение (%)",
        "Готовый призыв (CTA)",
        "Взять в работу",
        "Бралось в работу",
        "Взятий"
    ]
    
    print("Записываю заголовки...")
    service.spreadsheets().values().update(
        spreadsheetId=config.sheet_id,
        range=f"'{SHEET_TITLE}'!A1:I1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]}
    ).execute()

    # Формируем data_rows для values.update
    data_rows = []
    for m in matches:
        data_rows.append([
            m["id"],
            m["url"],
            m["cleaned_text"],
            m["pain_title"],
            m["score"],
            m["cta"],
            False,   # Взять в работу (чекбокс)
            "",      # Бралось в работу
            0        # Взятий
        ])

    print(f"Записываю {len(data_rows)} строк данных в '{SHEET_TITLE}'!A2:I...")
    service.spreadsheets().values().update(
        spreadsheetId=config.sheet_id,
        range=f"'{SHEET_TITLE}'!A2:I{len(data_rows) + 1}",
        valueInputOption="USER_ENTERED",
        body={"values": data_rows}
    ).execute()

    # Наводим красоту: стили, ширины колонок, заморозка шапки
    print("Применяю форматирование и стили...")
    requests = [
        # Заморозка первой строки
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": target_sheet_id,
                    "gridProperties": {"frozenRowCount": 1}
                },
                "fields": "gridProperties.frozenRowCount"
            }
        },
        # Темно-серый заголовок с белым жирным шрифтом
        {
            "repeatCell": {
                "range": {
                    "sheetId": target_sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 9
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
        # Выравнивание по верху и перенос текста для строк данных
        {
            "repeatCell": {
                "range": {
                    "sheetId": target_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": len(data_rows) + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 9
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
        # Центрирование для колонки Совпадение (%)
        {
            "repeatCell": {
                "range": {
                    "sheetId": target_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": len(data_rows) + 1,
                    "startColumnIndex": 4,
                    "endColumnIndex": 5
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "textFormat": {"bold": True}
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,textFormat.bold)"
            }
        },
        # Чекбоксы в колонку "Взять в работу" (колонка G, индекс 6)
        {
            "setDataValidation": {
                "range": {
                    "sheetId": target_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": len(data_rows) + 1,
                    "startColumnIndex": 6,
                    "endColumnIndex": 7
                },
                "rule": {
                    "condition": {"type": "BOOLEAN"},
                    "showCustomUi": True
                }
            }
        }
    ]

    # Ширины колонок
    col_widths = [
        (0, 1, 130),  # ID
        (1, 2, 170),  # URL ролика
        (2, 3, 420),  # Чистый текст
        (3, 4, 250),  # Боль
        (4, 5, 95),   # Совпадение %
        (5, 6, 380),  # CTA призыв
        (6, 7, 100),  # Взять в работу
        (7, 8, 100),  # Бралось в работу
        (8, 9, 80),   # Взятий
    ]
    for start_c, end_c, w in col_widths:
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": target_sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": start_c,
                    "endIndex": end_c
                },
                "properties": {"pixelSize": w},
                "fields": "pixelSize"
            }
        })

    # Добавляем кликабельные ссылки на full markdown в колонку ID
    for i, m in enumerate(matches):
        row_idx = i + 1
        github_link = f"https://github.com/detoximan/seedintake/blob/main/Inbox/2026/full/{m['id']}-f.md"
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": target_sheet_id,
                    "startRowIndex": row_idx,
                    "endRowIndex": row_idx + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1
                },
                "cell": {
                    "userEnteredValue": {"stringValue": m["id"]},
                    "userEnteredFormat": {
                        "textFormat": {
                            "link": {"uri": github_link},
                            "underline": True,
                            "foregroundColor": {"red": 0.1, "green": 0.35, "blue": 0.75}
                        },
                        "horizontalAlignment": "CENTER"
                    }
                },
                "fields": "userEnteredValue,userEnteredFormat(textFormat,horizontalAlignment)"
            }
        })

    service.spreadsheets().batchUpdate(
        spreadsheetId=config.sheet_id,
        body={"requests": requests}
    ).execute()

    print(f"ГОТОВО! Вкладка '{SHEET_TITLE}' успешно создана и заполнена {len(data_rows)} строками.")

if __name__ == "__main__":
    main()
