"""Синхронное применение двуязычного перевода в full, slim и Google Sheets.

Usage:
    python3 apply_bilingual_sync.py <seed_id> --translation-file <path>
    python3 apply_bilingual_sync.py <seed_id> --translation "<text>"
    python3 apply_bilingual_sync.py <seed_id> --sync-existing
    python3 apply_bilingual_sync.py <seed_id> --translation-file <path> --dry-run
"""
from __future__ import annotations

import argparse
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
SLIDE_MARKER_RE = re.compile(r"(\[[^\[\]\n]+\.(?:jpg|jpeg|png|webp|mp4|mov|webm)\]:?)", re.IGNORECASE)

REQUIRED_HEADERS = [
    "1 – текст на фото:",
    "2 – транскрибация аудио/видео:",
    "3 – текст под медиа:",
]


def extract_original_from_full(full_content: str) -> str:
    full_marker = "# Транскрибация / текст источника\n\n"
    tech_marker = "\n# Технические сведения"
    if full_marker not in full_content or tech_marker not in full_content:
        raise ValueError("В full-файле не найдены необходимые маркеры структуры.")
    f_rest = full_content.split(full_marker, 1)[1]
    material_block = f_rest.split(tech_marker, 1)[0].strip()
    if TRANS_MARKER in material_block:
        material_block = material_block.split(TRANS_MARKER, 1)[0].strip()
    return material_block


def extract_translation_from_full(full_content: str) -> str:
    full_marker = "# Транскрибация / текст источника\n\n"
    tech_marker = "\n# Технические сведения"
    if full_marker not in full_content or tech_marker not in full_content:
        raise ValueError("В full-файле не найдены необходимые маркеры структуры.")
    f_rest = full_content.split(full_marker, 1)[1]
    material_block = f_rest.split(tech_marker, 1)[0].strip()
    if TRANS_MARKER not in material_block:
        raise ValueError("В full-файле нет маркера перевода ====================")
    return material_block.split(TRANS_MARKER, 1)[1].strip()


def validate_translation(original: str, translation: str, *, force: bool = False) -> list[str]:
    errors = []
    if not CYRILLIC_RE.search(translation):
        errors.append("Перевод не содержит кириллицы!")

    lower_trans = translation.lower()
    for header in REQUIRED_HEADERS:
        if header not in lower_trans:
            errors.append(f"В переводе отсутствует обязательный заголовок: '{header}'")

    # Проверка слайдов для каруселей
    orig_slides = SLIDE_MARKER_RE.findall(original)
    trans_slides = SLIDE_MARKER_RE.findall(translation)

    if orig_slides:
        orig_names = [s.strip().rstrip(":") for s in orig_slides]
        trans_names = [s.strip().rstrip(":") for s in trans_slides]
        missing = [s for s in orig_names if s not in trans_names]
        if missing and not force:
            errors.append(
                f"В переводе потеряны маркеры слайдов ({len(missing)} из {len(orig_names)}): "
                f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}"
            )

    return errors


def sync_translation(
    seed_id: str,
    russian_translation: str | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
    row_override: int | None = None,
) -> None:
    year = seed_id.split("-")[0]
    slim_path = repo_root / "Inbox" / year / "slim" / f"{seed_id}-s.md"
    full_path = repo_root / "Inbox" / year / "full" / f"{seed_id}-f.md"

    if not slim_path.exists():
        raise FileNotFoundError(f"Slim-файл не найден: {slim_path}")
    if not full_path.exists():
        raise FileNotFoundError(f"Full-файл не найден: {full_path}")

    full_content = full_path.read_text(encoding="utf-8")
    slim_content = slim_path.read_text(encoding="utf-8")

    if russian_translation is None:
        original_source = extract_original_from_full(full_content)
        ru_trans = extract_translation_from_full(full_content)
    elif TRANS_MARKER in russian_translation:
        parts = russian_translation.split(TRANS_MARKER, 1)
        original_source = parts[0].strip()
        ru_trans = parts[1].strip()
    else:
        original_source = extract_original_from_full(full_content)
        ru_trans = russian_translation.strip()

    validation_errors = validate_translation(original_source, ru_trans, force=force)
    if validation_errors:
        print(f"ОШИБКИ ВАЛИДАЦИИ для {seed_id}:")
        for err in validation_errors:
            print(f"  - {err}")
        if not force:
            raise ValueError(f"Валидация перевода для {seed_id} провалена.")

    bilingual_text = f"{original_source}\n\n{TRANS_MARKER}\n\n{ru_trans}\n"

    print(f"[{seed_id}] Длина оригинала: {len(original_source)}, длина перевода: {len(ru_trans)}")

    if dry_run:
        print("DRY RUN: запись в файлы и таблицу не выполняется.")
        print("Предпросмотр перевода:")
        print(ru_trans[:300] + ("..." if len(ru_trans) > 300 else ""))
        return

    # 1. Обновляем slim файл
    source_marker = "# Источник\n\n"
    if source_marker not in slim_content:
        raise ValueError(f"Маркер '# Источник' не найден в {slim_path}")
    header_part = slim_content.split(source_marker, 1)[0]
    header_part = re.sub(r"^status:\s*\w+", "status: processed", header_part, flags=re.M)
    new_slim = f"{header_part}{source_marker}{bilingual_text}"
    slim_path.write_text(new_slim, encoding="utf-8")
    print(f"  - Обновлён slim: {slim_path.name}")

    # 2. Обновляем full файл
    full_marker = "# Транскрибация / текст источника\n\n"
    tech_marker = "\n# Технические сведения"
    f_top, f_rest = full_content.split(full_marker, 1)
    _, f_bottom = f_rest.split(tech_marker, 1)
    f_top = re.sub(r"^status:\s*\w+", "status: processed", f_top, flags=re.M)
    new_full = f"{f_top}{full_marker}{bilingual_text}{tech_marker}{f_bottom}"
    full_path.write_text(new_full, encoding="utf-8")
    print(f"  - Обновлён full: {full_path.name}")

    # 3. Обновляем Google Sheet
    ws = LiveGoogleWorkspace.from_env()
    target_row_indices = []
    if row_override:
        target_row_indices = [row_override]
    else:
        rows = ws.get_all_rows()
        for idx, row in enumerate(rows):
            if row and seed_id in row[0]:
                target_row_indices.append(idx + 1)

    if target_row_indices:
        for target_row_idx in target_row_indices:
            ws.update_range(f"E{target_row_idx}", [[bilingual_text.strip()]])
            print(f"  - Обновлена строка Google Sheet E{target_row_idx} для {seed_id}")
    else:
        print(f"  - ВНИМАНИЕ: строка {seed_id} не найдена в Google Sheet!")

    print(f"Успешно синхронизирован перевод для {seed_id}!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Синхронное обновление двуязычного перевода")
    parser.add_argument("seed_id", help="Идентификатор seed (например, 2026-08-06-012)")
    parser.add_argument("--translation-file", "-f", help="Путь к файлу с переводом")
    parser.add_argument("--translation", "-t", help="Текст перевода")
    parser.add_argument("--sync-existing", action="store_true", help="Синхронизировать существующий перевод из full-файла")
    parser.add_argument("--row", type=int, help="Номер строки в Google Sheet для принудительного обновления")
    parser.add_argument("--dry-run", action="store_true", help="Предпросмотр без записи")
    parser.add_argument("--force", action="store_true", help="Игнорировать ошибки валидации слайдов")
    args = parser.parse_args()

    trans_text = None
    if args.sync_existing:
        trans_text = None
    elif args.translation_file:
        trans_text = Path(args.translation_file).read_text(encoding="utf-8")
    elif args.translation:
        trans_text = args.translation
    elif not sys.stdin.isatty():
        trans_text = sys.stdin.read()
    else:
        print("Ошибка: укажите --translation-file, --translation, --sync-existing или передайте текст через stdin")
        sys.exit(1)

    sync_translation(
        args.seed_id,
        trans_text,
        dry_run=args.dry_run,
        force=args.force,
        row_override=args.row,
    )


if __name__ == "__main__":
    main()
