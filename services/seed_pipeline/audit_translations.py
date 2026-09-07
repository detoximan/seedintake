"""Аудит переводов в Google Sheets и Inbox/2026/.

Выявляет:
- Группа А: Англоязычные посты без маркера перевода (не переведены)
- Группа Б: Карусели с обрезанным/неполным переводом (потеря слайдов, ratio < 0.5)
- Группа В: Рассинхрон между Google Sheets и файлами full/slim
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root / "services" / "seed_pipeline" / "src"))

load_dotenv(repo_root / "services" / "seed_pipeline" / ".env")

from seed_pipeline.integrations.google_workspace_live import LiveGoogleWorkspace

TRANS_MARKER = "===================="
CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")
LATIN_RE = re.compile(r"[a-zA-Z]")
SLIDE_MARKER_RE = re.compile(r"(\[[^\[\]\n]+\.(?:jpg|jpeg|png|webp|mp4|mov|webm)\]:?)", re.IGNORECASE)
SEED_ID_RE = re.compile(r"\b(202\d-\d{2}-\d{2}-\d{3})\b")

EMPTY_PATTERNS = {"нет", "no", "текста нет", ""}


def get_pure_content(text: str) -> str:
    """Удаляет служебные заголовки и пустые маркеры для анализа языка."""
    clean = text
    for h in [
        "1 – текст на фото:", "1 – Текст на фото:",
        "2 – транскрибация аудио/видео:", "2 – Транскрибация аудио/видео:",
        "3 – текст под медиа:", "3 – Текст под медиа:",
    ]:
        clean = clean.replace(h, " ")
    lines = [l.strip() for l in clean.split("\n") if l.strip().lower() not in EMPTY_PATTERNS]
    return "\n".join(lines)


def audit() -> dict[str, list[dict]]:
    ws = LiveGoogleWorkspace.from_env()
    rows = ws.get_all_rows()

    group_a = []  # Не переведено
    group_b = []  # Обрезанный / неполный перевод
    group_c = []  # Рассинхрон

    for i, row in enumerate(rows):
        if i == 0:
            continue  # Пропускаем заголовки таблицы
        row_num = i + 1
        col_a = row[0] if len(row) > 0 else ""
        col_e = row[4] if len(row) > 4 else ""

        seed_match = SEED_ID_RE.search(col_a)
        seed_id = seed_match.group(1) if seed_match else col_a.strip()
        if not seed_id:
            continue

        # Читаем локальные файлы, если они есть
        year = seed_id.split("-")[0]
        full_path = repo_root / "Inbox" / year / "full" / f"{seed_id}-f.md"
        slim_path = repo_root / "Inbox" / year / "slim" / f"{seed_id}-s.md"

        full_content = full_path.read_text(encoding="utf-8") if full_path.exists() else ""
        slim_content = slim_path.read_text(encoding="utf-8") if slim_path.exists() else ""

        full_has_marker = TRANS_MARKER in full_content
        sheet_has_marker = TRANS_MARKER in col_e

        # Проверка Группы В (Рассинхрон)
        if full_has_marker and not sheet_has_marker:
            group_c.append({
                "row_num": row_num,
                "seed_id": seed_id,
                "reason": "Перевод есть в full-файле, но отсутствует в таблице",
            })
        elif not full_has_marker and sheet_has_marker:
            group_c.append({
                "row_num": row_num,
                "seed_id": seed_id,
                "reason": "Перевод есть в таблице, но отсутствует в full-файле",
            })

        # Анализ содержимого ячейки таблицы
        if sheet_has_marker:
            parts = col_e.split(TRANS_MARKER, 1)
            orig_part = parts[0].strip()
            trans_part = parts[1].strip()

            orig_slides = SLIDE_MARKER_RE.findall(orig_part)
            trans_slides = SLIDE_MARKER_RE.findall(trans_part)

            # Проверка Группы Б (Обрезанный перевод)
            if orig_slides:
                orig_names = [s.strip().rstrip(":") for s in orig_slides]
                trans_names = [s.strip().rstrip(":") for s in trans_slides]
                missing_slides = [s for s in orig_names if s not in trans_names]

                # Если есть слайды в оригинале, но перевод не содержит слайдов или пропустил их
                if missing_slides:
                    group_b.append({
                        "row_num": row_num,
                        "seed_id": seed_id,
                        "orig_slides_cnt": len(orig_names),
                        "trans_slides_cnt": len(trans_names),
                        "missing_cnt": len(missing_slides),
                        "missing_slides": missing_slides,
                        "orig_len": len(orig_part),
                        "trans_len": len(trans_part),
                        "reason": f"Пропущено {len(missing_slides)} из {len(orig_names)} слайдов",
                    })
                elif len(trans_part) < 0.4 * len(orig_part) and len(orig_part) > 200:
                    group_b.append({
                        "row_num": row_num,
                        "seed_id": seed_id,
                        "orig_slides_cnt": len(orig_names),
                        "trans_slides_cnt": len(trans_names),
                        "missing_cnt": 0,
                        "missing_slides": [],
                        "orig_len": len(orig_part),
                        "trans_len": len(trans_part),
                        "reason": f"Подозрительно малый объем перевода (ratio={len(trans_part)/len(orig_part):.2f})",
                    })
            else:
                # Не карусель, но проверим ratio для длинных текстов
                if len(orig_part) > 300 and len(trans_part) < 0.25 * len(orig_part):
                    group_b.append({
                        "row_num": row_num,
                        "seed_id": seed_id,
                        "orig_slides_cnt": 0,
                        "trans_slides_cnt": 0,
                        "missing_cnt": 0,
                        "missing_slides": [],
                        "orig_len": len(orig_part),
                        "trans_len": len(trans_part),
                        "reason": f"Слишком короткий перевод видео/поста (ratio={len(trans_part)/len(orig_part):.2f})",
                    })
        else:
            # Нет маркера перевода в таблице
            pure = get_pure_content(col_e)
            if pure:
                latin_cnt = len(LATIN_RE.findall(pure))
                cyr_cnt = len(CYRILLIC_RE.findall(pure))
                # Если латиницы значительно больше, чем кириллицы
                if latin_cnt > 30 and cyr_cnt < 20:
                    group_a.append({
                        "row_num": row_num,
                        "seed_id": seed_id,
                        "latin_cnt": latin_cnt,
                        "cyr_cnt": cyr_cnt,
                        "content_len": len(pure),
                        "preview": pure[:100].replace("\n", " "),
                    })

    return {
        "group_a": group_a,
        "group_b": group_b,
        "group_c": group_c,
    }


def main():
    print("Запуск аудита переводов в Google Sheets и Inbox/2026/...")
    results = audit()

    ga = results["group_a"]
    gb = results["group_b"]
    gc = results["group_c"]

    print("\n" + "=" * 60)
    print(f"ГРУППА А: Непереведённый контент без маркера ({len(ga)} шт.)")
    print("=" * 60)
    for item in ga:
        print(f"Строка {item['row_num']:4d} | ID: {item['seed_id']:15s} | len={item['content_len']:5d} | {item['preview']}")

    print("\n" + "=" * 60)
    print(f"ГРУППА Б: Обрезанный / неполный перевод каруселей ({len(gb)} шт.)")
    print("=" * 60)
    for item in gb:
        print(
            f"Строка {item['row_num']:4d} | ID: {item['seed_id']:15s} | "
            f"Слайдов: {item['trans_slides_cnt']}/{item['orig_slides_cnt']} | "
            f"len: {item['trans_len']}/{item['orig_len']} | {item['reason']}"
        )

    print("\n" + "=" * 60)
    print(f"ГРУППА В: Рассинхрон файлов и Google Sheets ({len(gc)} шт.)")
    print("=" * 60)
    for item in gc:
        print(f"Строка {item['row_num']:4d} | ID: {item['seed_id']:15s} | {item['reason']}")

    print("\n" + "=" * 60)
    print("ИТОГО:")
    print(f"  Группа А (не переведено): {len(ga)}")
    print(f"  Группа Б (обрезанный перевод): {len(gb)}")
    print(f"  Группа В (рассинхрон): {len(gc)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
