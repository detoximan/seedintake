from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from seed_pipeline.integrations import MockGoogleWorkspace
from seed_pipeline.schemas import DryRunResult, ErrorRecord, SeedInput, SeedPlan

AGENT_NAME = "Seed Intake Agent"


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def parse_case_file(path: Path) -> tuple[SeedInput, bool]:
    text = path.read_text(encoding="utf-8")
    duplicate = "Duplicate Message Input" in text or "уже был обработан" in text

    return (
        SeedInput(
            telegram_message_id=_extract_backtick_field(text, "telegram_message_id"),
            telegram_user_id=_extract_backtick_field(text, "telegram_user_id"),
            received_at=_extract_backtick_field(text, "received_at"),
            material=_extract_label_field(text, "Основной материал"),
            comment=_extract_label_field(text, "Комментарий Павла", required=False),
            source_url=_normalize_optional(_extract_backtick_field(text, "source_url", required=False)),
        ),
        duplicate,
    )


def build_dry_run(
    seed_input: SeedInput,
    *,
    repo_root: Path | None = None,
    duplicate_message: bool = False,
    runtime_tmp_dir: Path | None = None,
    google_workspace: MockGoogleWorkspace | None = None,
) -> DryRunResult:
    root = repo_root or find_repo_root()
    _validate_seed_input(seed_input)

    if duplicate_message:
        return DryRunResult(
            dry_run=True,
            status="warning",
            seed_input=seed_input,
            seed_plan=None,
            error_record=_error_record(
                error_code="SEED_DUPLICATE_MESSAGE",
                step="check_input_fingerprint",
                message="Incoming Telegram message was already converted into a Seed.",
                manual_action="none",
                timestamp=seed_input.received_at,
                severity="warning",
            ),
        )

    seed_id = _next_seed_id(root / "Inbox", seed_input.received_at)
    full_markdown_path = f"Inbox/{seed_id[:4]}/full/{seed_id}-f.md"
    slim_markdown_path = f"Inbox/{seed_id[:4]}/slim/{seed_id}-s.md"
    full_github_url = _github_url(full_markdown_path)
    slim_github_url = _github_url(slim_markdown_path)
    workspace = google_workspace or MockGoogleWorkspace()
    google_result = workspace.create_seed_artifacts(
        seed_id=seed_id,
        seed_input=seed_input,
        full_markdown_url=full_github_url,
    )
    if google_result.status != "ok":
        result = DryRunResult(
            dry_run=True,
            status="error",
            seed_input=seed_input,
            seed_plan=None,
            error_record=google_result.error_record,
            google_workspace=google_result,
        )
        report_path = write_dry_run_report(result, repo_root=root, runtime_tmp_dir=runtime_tmp_dir)
        return DryRunResult(
            dry_run=result.dry_run,
            status=result.status,
            seed_input=result.seed_input,
            seed_plan=result.seed_plan,
            error_record=result.error_record,
            google_workspace=result.google_workspace,
            report_path=str(report_path),
        )

    fingerprint = _build_fingerprint(seed_input)
    plan = SeedPlan(
        seed_id=seed_id,
        status="new",
        markdown_path=slim_markdown_path,
        markdown_preview=_build_markdown_preview(
            seed_id=seed_id,
            full_github_url=full_github_url,
            comment=seed_input.comment,
            material=seed_input.material,
        ),
        full_markdown_path=full_markdown_path,
        slim_markdown_path=slim_markdown_path,
        full_github_url=full_github_url,
        slim_github_url=slim_github_url,
        input_fingerprint=fingerprint,
        firestore_required=False,
        external_calls=[],
    )
    result = DryRunResult(
        dry_run=True,
        status="ok",
        seed_input=seed_input,
        seed_plan=plan,
        error_record=None,
        google_workspace=google_result,
    )
    report_path = write_dry_run_report(result, repo_root=root, runtime_tmp_dir=runtime_tmp_dir)
    return DryRunResult(
        dry_run=result.dry_run,
        status=result.status,
        seed_input=result.seed_input,
        seed_plan=result.seed_plan,
        error_record=result.error_record,
        google_workspace=result.google_workspace,
        report_path=str(report_path),
    )


def write_dry_run_report(
    result: DryRunResult,
    *,
    repo_root: Path | None = None,
    runtime_tmp_dir: Path | None = None,
) -> Path:
    root = repo_root or find_repo_root()
    env_runtime_tmp_dir = os.getenv("RUNTIME_TMP_DIR", "").strip()
    if runtime_tmp_dir is not None:
        target_dir = runtime_tmp_dir
    elif env_runtime_tmp_dir:
        target_dir = Path(env_runtime_tmp_dir).expanduser()
    else:
        target_dir = root / "runtime" / "tmp" / "seed_pipeline"
    if not target_dir.is_absolute():
        target_dir = root / target_dir

    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = target_dir / f"dry-run-{timestamp}.json"
    target.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _validate_seed_input(seed_input: SeedInput) -> None:
    missing = []
    for field_name in ("telegram_message_id", "telegram_user_id", "received_at", "material"):
        value = getattr(seed_input, field_name)
        if not isinstance(value, str) or not value.strip():
            missing.append(field_name)
    if missing:
        raise ValueError(f"Seed dry-run input is missing required fields: {', '.join(missing)}")


def _next_seed_id(seed_root: Path, received_at: str) -> str:
    day = received_at[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("received_at must start with YYYY-MM-DD")

    year_dir = seed_root / day[:4]
    max_number = 0
    if year_dir.exists():
        for candidate in year_dir.rglob(f"{day}-*.md"):
            match = re.fullmatch(rf"{re.escape(day)}-(\d{{3}})(?:-[fs])?\.md", candidate.name)
            if match:
                max_number = max(max_number, int(match.group(1)))
    return f"{day}-{max_number + 1:03d}"


def _build_fingerprint(seed_input: SeedInput) -> dict[str, object]:
    normalized_material = _normalize(seed_input.material)
    normalized_comment = _normalize(seed_input.comment)
    source_url = seed_input.source_url or None
    content_hash = _sha256("\n".join([normalized_material, normalized_comment, source_url or ""]))
    input_fingerprint = _sha256(
        "\n".join(
            [
                seed_input.telegram_message_id.strip(),
                seed_input.telegram_user_id.strip(),
                seed_input.received_at.strip(),
                source_url or "",
                content_hash,
            ]
        )
    )
    return {
        "input_fingerprint": input_fingerprint,
        "telegram_message_id": seed_input.telegram_message_id.strip(),
        "telegram_user_id": seed_input.telegram_user_id.strip(),
        "source_url": source_url,
        "received_at": seed_input.received_at.strip(),
        "content_hash": content_hash,
    }


def _build_markdown_preview(*, seed_id: str, full_github_url: str, comment: str, material: str) -> str:
    normalized_comment = comment.strip() or "Без комментария."
    
    # Keep the FULL material, just strip API metadata and widget noise
    lines = material.strip().splitlines()
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        # Drop Jina system artifacts
        if stripped.startswith("Warning:") or stripped.startswith("URL Source:") or stripped.startswith("Title: "):
            continue
        if stripped.startswith("Markdown Content:") or stripped == "# Telegram: View @durov":
            continue
        # Drop Telegram embed utility links
        if stripped.startswith("[](") or stripped.startswith("[Context](") or stripped.startswith("[Embed]("):
            continue
        if stripped.startswith("[View In Channel](") or stripped.startswith("[Copy]("):
            continue
            
        cleaned_lines.append(line)
            
    import re
    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text).strip()
    
    if not cleaned_text:
        cleaned_text = material.strip()
        
    return (
        "status: new\n\n"
        f"[{seed_id}]({full_github_url})\n\n"
        "# Комментарий Павла\n\n"
        f"{normalized_comment}\n\n"
        "# Источник\n\n"
        f"{cleaned_text}\n"
    )


def _github_url(markdown_path: str) -> str:
    base_url = os.getenv("GITHUB_SEED_BASE_URL", "").strip()
    if not base_url:
        base_url = "https://github.com/detoximan/seedintake/blob/main"
    return f"{base_url.rstrip('/')}/{markdown_path}"


def _error_record(
    *,
    error_code: str,
    step: str,
    message: str,
    manual_action: str,
    timestamp: str,
    severity: str,
) -> ErrorRecord:
    return ErrorRecord(
        error_code=error_code,
        agent=AGENT_NAME,
        step=step,
        artifact_id=None,
        message=message,
        manual_action=manual_action,
        timestamp=timestamp,
        severity=severity,
    )


def _extract_backtick_field(text: str, field_name: str, *, required: bool = True) -> str:
    pattern = rf"`{re.escape(field_name)}`:\s*`([^`]*)`"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    if required:
        raise ValueError(f"Test case is missing `{field_name}`")
    return ""


def _extract_label_field(text: str, label: str, *, required: bool = True) -> str:
    pattern = rf"{re.escape(label)}:\s*`([^`]*)`"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    if required:
        raise ValueError(f"Test case is missing `{label}`")
    return ""


def _normalize_optional(value: str) -> str | None:
    normalized = value.strip()
    if not normalized or normalized.lower() in {"пусто", "null", "none"}:
        return None
    return normalized


def _normalize(value: str) -> str:
    return " ".join(value.strip().split())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
