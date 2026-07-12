from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from seed_pipeline.intake.dry_run import find_repo_root


VALID_STATUSES = {"new", "processed", "failed", "pending_cookies"}


@dataclass(frozen=True)
class LinkQueueItem:
    path: Path
    relative_path: str
    status: str
    url: str
    platform: str
    context: str = ""
    processed_seed_id: str | None = None
    processed_seed_path: str | None = None
    processed_at: str | None = None
    failure_reason: str | None = None
    failed_at: str | None = None


@dataclass(frozen=True)
class LinkQueueUpdate:
    status: str
    processed_seed_id: str | None = None
    processed_seed_path: str | None = None
    processed_at: str | None = None
    failure_reason: str | None = None
    failed_at: str | None = None


class LinkQueueStore:
    def __init__(self, *, repo_root: Path | None = None, seed_root: Path | None = None) -> None:
        self.repo_root = repo_root or find_repo_root()
        self.seed_root = seed_root or self.repo_root / "1inbox" / "seeds"
        if not self.seed_root.is_absolute():
            self.seed_root = self.repo_root / self.seed_root

    def list_items(self, *, status: str | None = None, platform: str | None = None, include_fallback: bool = False) -> list[LinkQueueItem]:
        items: list[LinkQueueItem] = []
        if not self.seed_root.exists():
            return items

        patterns = ["*/links/*-link.md"]
        if include_fallback:
            patterns.append("*/links_fall/*-link.md")

        for pattern in patterns:
            for candidate in sorted(self.seed_root.glob(pattern)):
                if not candidate.is_file():
                    continue
                item = self.read(candidate)
                if (status is None or item.status == status) and (platform is None or item.platform == platform):
                    items.append(item)
        return items

    def read(self, path: Path) -> LinkQueueItem:
        target = self._resolve_path(path)
        fields = _parse_link_queue_markdown(target.read_text(encoding="utf-8"))
        status = fields.get("status", "").strip()
        url = fields.get("url", "").strip()
        platform = fields.get("platform", "").strip()
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid link queue status in {self._display_path(target)}: {status or '<empty>'}")
        if not url:
            raise ValueError(f"Missing link queue url in {self._display_path(target)}")
        if not platform:
            raise ValueError(f"Missing link queue platform in {self._display_path(target)}")

        return LinkQueueItem(
            path=target,
            relative_path=self._display_path(target),
            status=status,
            url=url,
            platform=platform,
            context=fields.get("context", "").strip(),
            processed_seed_id=_empty_to_none(fields.get("processed_seed_id")),
            processed_seed_path=_empty_to_none(fields.get("processed_seed_path")),
            processed_at=_empty_to_none(fields.get("processed_at")),
            failure_reason=_empty_to_none(fields.get("failure_reason")),
            failed_at=_empty_to_none(fields.get("failed_at")),
        )

    def update(self, item: LinkQueueItem, update: LinkQueueUpdate) -> LinkQueueItem:
        if update.status not in VALID_STATUSES:
            raise ValueError(f"Invalid link queue status: {update.status}")
        target = self._resolve_path(item.path)
        updated = LinkQueueItem(
            path=target,
            relative_path=self._display_path(target),
            status=update.status,
            url=item.url,
            platform=item.platform,
            context=item.context,
            processed_seed_id=update.processed_seed_id,
            processed_seed_path=update.processed_seed_path,
            processed_at=update.processed_at,
            failure_reason=_sanitize_reason(update.failure_reason) if update.failure_reason else None,
            failed_at=update.failed_at,
        )
        self._write_atomic(target, _build_link_queue_markdown(updated))
        return updated

    def move_to_fallback(self, item: LinkQueueItem) -> LinkQueueItem:
        """Move the queue item file from links/ to links_fall/ and set status to pending_cookies."""
        old_path = self._resolve_path(item.path)
        # Determine new directory: replace '/links/' with '/links_fall/'
        # Assuming path pattern: .../seeds/YYYY/links/foo.md
        new_dir = old_path.parent.parent / "links_fall"
        new_dir.mkdir(parents=True, exist_ok=True)
        new_path = new_dir / old_path.name

        # Create updated item with new path and status pending_cookies
        updated = LinkQueueItem(
            path=new_path,
            relative_path=self._display_path(new_path),
            status="pending_cookies",
            url=item.url,
            platform=item.platform,
            context=item.context,
            processed_seed_id=item.processed_seed_id,
            processed_seed_path=item.processed_seed_path,
            processed_at=item.processed_at,
            failure_reason=item.failure_reason,
            failed_at=item.failed_at,
        )
        # Write to new location
        self._write_atomic(new_path, _build_link_queue_markdown(updated))
        # Remove old file
        old_path.unlink()
        return updated

    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.repo_root / path

    def _write_atomic(self, target: Path, markdown: str) -> None:
        temp_path = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".tmp-{target.stem}-",
                suffix=".md",
                delete=False,
            ) as temp_file:
                temp_file.write(markdown)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)
            os.replace(temp_path, target)
        except Exception:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.as_posix()


def _parse_link_queue_markdown(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(?:\s*(.*))?$", line)
        if not match:
            index += 1
            continue

        key = match.group(1)
        value = (match.group(2) or "").rstrip()
        if value in {"|-", "|"}:
            block: list[str] = []
            index += 1
            while index < len(lines):
                block_line = lines[index]
                if block_line.startswith("  "):
                    block.append(block_line[2:])
                    index += 1
                    continue
                if not block_line.strip():
                    block.append("")
                    index += 1
                    continue
                break
            fields[key] = "\n".join(block).strip()
            continue

        fields[key] = value.strip()
        index += 1
    return fields


def _build_link_queue_markdown(item: LinkQueueItem) -> str:
    blocks = [
        f"status: {item.status}",
        f"url: {item.url}",
        f"platform: {item.platform}",
    ]
    if item.context:
        blocks.append(_block_field("context", item.context))
    if item.processed_seed_id:
        blocks.append(f"processed_seed_id: {item.processed_seed_id}")
    if item.processed_seed_path:
        blocks.append(f"processed_seed_path: {item.processed_seed_path}")
    if item.processed_at:
        blocks.append(f"processed_at: {item.processed_at}")
    if item.failure_reason:
        blocks.append(f"failure_reason: {item.failure_reason}")
    if item.failed_at:
        blocks.append(f"failed_at: {item.failed_at}")
    return "\n\n".join(blocks) + "\n"


def _block_field(key: str, value: str) -> str:
    lines = value.strip().splitlines()
    return "\n".join([f"{key}: |-", *[f"  {line}" for line in lines]])


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _sanitize_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    normalized = " ".join(reason.strip().split())
    return normalized[:500] if normalized else None
