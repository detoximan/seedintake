from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from seed_pipeline.intake.dry_run import (
    _build_fingerprint,
    _build_markdown_preview,
    _error_record,
    _next_seed_id,
    find_repo_root,
)
from seed_pipeline.schemas import ErrorRecord, SeedInput, SeedMarkdownArtifacts, SeedPlan


class SeedDuplicateError(RuntimeError):
    def __init__(self, error_record: ErrorRecord) -> None:
        super().__init__(error_record.message)
        self.error_record = error_record


@dataclass(frozen=True)
class CreatedMarkdownSeed:
    seed_plan: SeedPlan
    full_file: Path
    slim_file: Path
    artifacts: SeedMarkdownArtifacts


class ProcessedMessageRegistry:
    def __init__(self, path: Path | None = None, *, repo_root: Path | None = None) -> None:
        root = repo_root or find_repo_root()
        if path is None:
            path = root / "runtime" / "tmp" / "seed_pipeline" / "processed_messages.json"
        elif not path.is_absolute():
            path = root / path
        self.path = path

    def find(self, telegram_message_id: str) -> str | None:
        data = self._read()
        value = data.get(telegram_message_id)
        return str(value) if value is not None else None

    def record(self, telegram_message_id: str, seed_id: str) -> None:
        data = self._read()
        data[telegram_message_id] = seed_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".tmp-processed-messages-",
                suffix=".json",
                delete=False,
            ) as temp_file:
                json.dump(data, temp_file, ensure_ascii=False, indent=2, sort_keys=True)
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)
            os.replace(temp_path, self.path)
        except Exception:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Processed message registry must contain a JSON object")
        return {str(key): str(value) for key, value in payload.items()}


class SeedMarkdownWriter:
    def __init__(
        self,
        *,
        seed_root: Path | None = None,
        registry: ProcessedMessageRegistry | None = None,
        repo_root: Path | None = None,
        github_base_url: str | None = None,
    ) -> None:
        self.repo_root = repo_root or find_repo_root()
        self.seed_root = seed_root or self.repo_root / "Inbox"
        if not self.seed_root.is_absolute():
            self.seed_root = self.repo_root / self.seed_root
        self.registry = registry or ProcessedMessageRegistry(repo_root=self.repo_root)
        self.github_base_url = (github_base_url or os.getenv("GITHUB_SEED_BASE_URL", "")).strip()
        if not self.github_base_url:
            self.github_base_url = "https://github.com/detoximan/seedintake/blob/main"

    def next_seed_id(self, received_at: str) -> str:
        return _next_seed_id(self.seed_root, received_at)

    def write(
        self,
        seed_input: SeedInput,
        *,
        seed_id: str | None = None,
        record_processed: bool = True,
    ) -> CreatedMarkdownSeed:
        existing_seed_id = self.registry.find(seed_input.telegram_message_id)
        if existing_seed_id is not None:
            raise SeedDuplicateError(
                _error_record(
                    error_code="SEED_DUPLICATE_MESSAGE",
                    step="check_input_fingerprint",
                    message="Incoming Telegram message was already converted into a Seed.",
                    manual_action="none",
                    timestamp=seed_input.received_at,
                    severity="warning",
                )
            )

        seed_id = seed_id or self.next_seed_id(seed_input.received_at)
        year_dir = self.seed_root / seed_id[:4]
        full_target = year_dir / "full" / f"{seed_id}-f.md"
        slim_target = year_dir / "slim" / f"{seed_id}-s.md"
        full_github_url = self._github_url(full_target)
        slim_github_url = self._github_url(slim_target)
        full_markdown = _build_full_markdown(
            seed_id=seed_id,
            seed_input=seed_input,
            slim_github_url=slim_github_url,
        )
        slim_markdown = _build_markdown_preview(
            seed_id=seed_id,
            full_github_url=full_github_url,
            comment=seed_input.comment,
            material=seed_input.material,
        )
        artifacts = SeedMarkdownArtifacts(
            seed_id=seed_id,
            full_path=self._display_path(full_target),
            slim_path=self._display_path(slim_target),
            full_github_url=full_github_url,
            slim_github_url=slim_github_url,
        )
        plan = SeedPlan(
            seed_id=seed_id,
            status="new",
            markdown_path=artifacts.slim_path,
            markdown_preview=slim_markdown,
            full_markdown_path=artifacts.full_path,
            slim_markdown_path=artifacts.slim_path,
            full_github_url=artifacts.full_github_url,
            slim_github_url=artifacts.slim_github_url,
            input_fingerprint=_build_fingerprint(seed_input),
            firestore_required=False,
            external_calls=[],
        )

        self._write_pair_atomic(full_target=full_target, full_markdown=full_markdown, slim_target=slim_target, slim_markdown=slim_markdown)
        if record_processed:
            self.registry.record(seed_input.telegram_message_id, seed_id)
        return CreatedMarkdownSeed(seed_plan=plan, full_file=full_target, slim_file=slim_target, artifacts=artifacts)

    def rollback(self, created: CreatedMarkdownSeed) -> None:
        for path in (created.full_file, created.slim_file):
            if path.exists():
                path.unlink()

    def _write_atomic(self, target: Path, markdown: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Seed markdown already exists: {self._display_path(target)}")

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

            if target.exists():
                raise FileExistsError(f"Seed markdown already exists: {self._display_path(target)}")
            os.replace(temp_path, target)
        except Exception:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise

    def _write_pair_atomic(self, *, full_target: Path, full_markdown: str, slim_target: Path, slim_markdown: str) -> None:
        written: list[Path] = []
        try:
            self._write_atomic(full_target, full_markdown)
            written.append(full_target)
            self._write_atomic(slim_target, slim_markdown)
            written.append(slim_target)
        except Exception:
            for path in written:
                if path.exists():
                    path.unlink()
            raise

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _github_url(self, path: Path) -> str:
        return f"{self.github_base_url.rstrip('/')}/{self._display_path(path)}"


def _build_full_markdown(*, seed_id: str, seed_input: SeedInput, slim_github_url: str) -> str:
    normalized_comment = seed_input.comment.strip() or "Без комментария."
    
    # Strip Jina API noise from the full markdown as well to avoid duplicates
    lines = seed_input.material.strip().splitlines()
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Warning:") or stripped.startswith("URL Source:") or stripped.startswith("Title: "):
            continue
        if stripped.startswith("Markdown Content:") or stripped == "# Telegram: View @durov":
            continue
        cleaned_lines.append(line)
        
    import re
    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text).strip()
    
    if not cleaned_text:
        cleaned_text = seed_input.material.strip()
        
    fingerprint = _build_fingerprint(seed_input)
    fingerprint_lines = "\n".join(
        f"- {key}: {_format_fingerprint_value(value)}" for key, value in fingerprint.items()
    )
    source_line = f"\n\n# Ссылка на исходный материал\n\n{seed_input.source_url}\n" if seed_input.source_url else ""
    return (
        f"# {seed_id}\n\n"
        "status: new\n\n"
        "# Оригинал\n\n"
        f"[Короткая версия Seed]({slim_github_url})\n"
        f"{source_line}\n\n"
        "# Комментарий Павла\n\n"
        f"{normalized_comment}\n\n"
        "# Транскрибация / текст источника\n\n"
        f"{cleaned_text}\n\n"
        "# Технические сведения\n\n"
        f"{fingerprint_lines}\n"
    )


def _format_fingerprint_value(value: object) -> str:
    return "" if value is None else str(value)
