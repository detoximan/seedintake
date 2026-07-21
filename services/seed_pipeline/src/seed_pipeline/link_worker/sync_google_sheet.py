from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from seed_pipeline.integrations import LiveGoogleWorkspace, LiveGoogleWorkspaceConfigError, LiveGoogleWorkspaceDependencyError
from seed_pipeline.link_worker.queue import LinkQueueStore
from seed_pipeline.intake.dry_run import find_repo_root


SEED_ID_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}-\d{3})$")


def _parse_seed_id_from_name(name: str) -> str | None:
    base = Path(name).stem
    m = SEED_ID_PATTERN.match(base)
    return m.group(1) if m else None


def _build_link_index(repo_root: Path) -> dict[str, dict[str, str]]:
    links_dir = repo_root / "Inbox" / "2026" / "links"
    index: dict[str, dict[str, str]] = {}
    if not links_dir.exists():
        return index
    for path in sorted(links_dir.glob("2026-07-12-*-link.md")):
        seed_id = _parse_seed_id_from_name(path.name)
        if not seed_id:
            continue
        text = path.read_text(encoding="utf-8")
        url = ""
        m = re.search(r"^url:\s*(.+)$", text, re.M)
        if m:
            url = m.group(1).strip()
        status = ""
        m = re.search(r"^status:\s*(.+)$", text, re.M)
        if m:
            status = m.group(1).strip()
        index[seed_id] = {"path": str(path.relative_to(repo_root)), "url": url, "status": status}
    return index


def _build_seed_files(repo_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    slim_dir = repo_root / "Inbox" / "2026" / "slim"
    full_dir = repo_root / "Inbox" / "2026" / "full"
    slim: dict[str, str] = {}
    full: dict[str, str] = {}
    if slim_dir.exists():
        for path in sorted(slim_dir.glob("2026-07-12-*-s.md")):
            seed_id = _parse_seed_id_from_name(path.name)
            if seed_id:
                slim[seed_id] = str(path.relative_to(repo_root))
    if full_dir.exists():
        for path in sorted(full_dir.glob("2026-07-12-*-f.md")):
            seed_id = _parse_seed_id_from_name(path.name)
            if seed_id:
                full[seed_id] = str(path.relative_to(repo_root))
    return slim, full


def _load_sheet_rows(workspace: LiveGoogleWorkspace) -> list[list[str]]:
    return workspace.get_all_rows()


def _row_seed_id(row: list[str]) -> str | None:
    if not row:
        return None
    cell = str(row[0]).strip()
    # cell may be markdown link or plain id
    m = re.search(r"\[([^\]]+)\]", cell)
    if m:
        cell = m.group(1)
    m = SEED_ID_PATTERN.match(cell)
    return m.group(1) if m else None


def _make_link_markdown(seed_id: str, full_rel_path: str | None) -> str:
    base = "https://github.com/detoximan/seedintake/blob/main"
    url = f"{base}/{full_rel_path}" if full_rel_path else ""
    if url:
        return f"[{seed_id}]({url})"
    return seed_id


def normalize_workspace(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root()
    links = _build_link_index(repo_root)
    slim, full = _build_seed_files(repo_root)

    expected: dict[str, dict[str, Any]] = {}
    for seed_id, meta in links.items():
        expected[seed_id] = {
            "url": meta.get("url", ""),
            "full_url": "",
            "slim": slim.get(seed_id),
            "full": full.get(seed_id),
        }
        if expected[seed_id]["full"]:
            expected[seed_id]["full_url"] = _make_link_markdown(seed_id, expected[seed_id]["full"])

    workspace = LiveGoogleWorkspace.from_env()
    rows = _load_sheet_rows(workspace)
    if not rows:
        print("Google Sheet пуст или недоступен.")
        return 1

    header = rows[0]
    data_rows = rows[1:]
    keep: list[list[str]] = []
    to_append: list[list[str]] = []

    for row in data_rows:
        seed_id = _row_seed_id(row)
        if not seed_id:
            keep.append(row)
            continue
        if seed_id not in expected:
            # orphan row in sheet -> remove
            continue
        # ensure link markdown in A, full url if exists
        full_rel = expected[seed_id].get("full")
        desired_id_cell = _make_link_markdown(seed_id, full_rel)
        # normalize first cell
        if len(row) > 0:
            row[0] = desired_id_cell
        keep.append(row)
        del expected[seed_id]

    # remaining expected seeds -> append
    for seed_id, meta in expected.items():
        if not meta.get("slim") and not meta.get("full"):
            continue
        row = [
            _make_link_markdown(seed_id, meta.get("full")),
            "",
            "",
            "instagram_reels processed by Universal Media Worker.",
            "",
        ]
        to_append.append(row)

    print(f"Sheet rows to keep: {len(keep)}")
    print(f"Sheet rows to append: {len(to_append)}")

    if getattr(args, "dry_run", False):
        print("Dry-run: no sheet changes.")
        return 0

    # rewrite sheet
    values: list[list[str]] = [header] + keep + to_append
    workspace.update_range("A:E", values)
    print(f"Updated Google Sheet. Total rows now: {len(values)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync Google Sheet with actual processed seeds for a date")
    parser.add_argument("--repo-root", help="Repository root. Defaults to auto-detection.")
    parser.add_argument("--date", default="2026-07-12", help="Date prefix to sync, default 2026-07-12")
    parser.add_argument("--dry-run", action="store_true", help="Do not write, just print plan")
    return normalize_workspace(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())