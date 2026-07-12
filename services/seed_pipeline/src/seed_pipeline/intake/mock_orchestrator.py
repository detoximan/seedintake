from __future__ import annotations

import os
import re
from pathlib import Path

from seed_pipeline.integrations import LiveGoogleWorkspace, MockGoogleWorkspace
from seed_pipeline.intake.dry_run import _next_seed_id, find_repo_root
from seed_pipeline.intake.github_storage import GitHubSeedMarkdownWriter
from seed_pipeline.intake.markdown_writer import ProcessedMessageRegistry, SeedMarkdownWriter
from seed_pipeline.schemas import ErrorRecord, SeedCreationResult, SeedInput

AGENT_NAME = "Seed Intake Agent"


class MockSeedIntakeOrchestrator:
    def __init__(
        self,
        *,
        google_workspace: MockGoogleWorkspace | None = None,
        markdown_writer: object | None = None,
        registry: ProcessedMessageRegistry | None = None,
        seed_root: Path | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.repo_root = repo_root or find_repo_root()
        self.registry = registry or ProcessedMessageRegistry(repo_root=self.repo_root)
        self.markdown_writer = markdown_writer or SeedMarkdownWriter(
            seed_root=seed_root,
            registry=self.registry,
            repo_root=self.repo_root,
        )
        self.registry = self.markdown_writer.registry
        self.google_workspace = google_workspace or MockGoogleWorkspace()

    def create_seed(self, seed_input: SeedInput) -> SeedCreationResult:
        existing_seed_id = self.registry.find(seed_input.telegram_message_id)
        if existing_seed_id is not None:
            return SeedCreationResult(
                status="warning",
                seed_input=seed_input,
                seed_plan=None,
                google_workspace=None,
                markdown_path=None,
                error_record=_error_record(
                    error_code="SEED_DUPLICATE_MESSAGE",
                    step="check_input_fingerprint",
                    artifact_id=existing_seed_id,
                    message="Incoming Telegram message was already converted into a Seed.",
                    manual_action="none",
                    timestamp=seed_input.received_at,
                    severity="warning",
                ),
            )

        match = re.search(r"(\d{4}-\d{2}-\d{2}-\d{3})-link\.md$", seed_input.telegram_message_id)
        if match:
            seed_id = match.group(1)
        elif hasattr(self.markdown_writer, "next_seed_id"):
            seed_id = self.markdown_writer.next_seed_id(seed_input.received_at)
        else:
            seed_id = _next_seed_id(self.markdown_writer.seed_root, seed_input.received_at)
        try:
            created = self.markdown_writer.write(seed_input, seed_id=seed_id, record_processed=False)
        except Exception as exc:
            return SeedCreationResult(
                status="error",
                seed_input=seed_input,
                seed_plan=None,
                google_workspace=None,
                markdown_path=None,
                error_record=_error_record(
                    error_code="MARKDOWN_SEED_WRITE_FAILED",
                    step="create_markdown_seed",
                    artifact_id=seed_id,
                    message=str(exc),
                    manual_action="Fix the markdown write issue, then retry Seed creation.",
                    timestamp=seed_input.received_at,
                    severity="error",
                ),
            )

        google_result = self.google_workspace.create_seed_artifacts(
            seed_id=seed_id,
            seed_input=seed_input,
            full_markdown_url=created.artifacts.full_github_url,
        )
        if google_result.status != "ok":
            self.markdown_writer.rollback(created)
            return SeedCreationResult(
                status="error",
                seed_input=seed_input,
                seed_plan=None,
                google_workspace=google_result,
                markdown_path=None,
                error_record=google_result.error_record,
            )

        self.registry.record(seed_input.telegram_message_id, seed_id)
        return SeedCreationResult(
            status="ok",
            seed_input=seed_input,
            seed_plan=created.seed_plan,
            google_workspace=google_result,
            markdown_path=created.seed_plan.slim_markdown_path,
            error_record=None,
        )


def build_seed_orchestrator_from_env(
    *,
    repo_root: Path | None = None,
    google_workspace: MockGoogleWorkspace | LiveGoogleWorkspace | None = None,
) -> MockSeedIntakeOrchestrator:
    root = repo_root or find_repo_root()
    storage_provider = os.getenv("SEED_MARKDOWN_STORAGE", "local").strip().lower()
    google_provider = os.getenv("SEED_GOOGLE_WORKSPACE", "mock").strip().lower()

    if storage_provider in {"", "local"}:
        markdown_writer = SeedMarkdownWriter(repo_root=root)
    elif storage_provider == "github":
        markdown_writer = GitHubSeedMarkdownWriter.from_env(repo_root=root)
    else:
        raise RuntimeError("Unknown SEED_MARKDOWN_STORAGE; supported values: local, github")

    if google_workspace is None:
        if google_provider in {"", "mock"}:
            google_workspace = MockGoogleWorkspace()
        elif google_provider == "live":
            google_workspace = LiveGoogleWorkspace.from_env()
        else:
            raise RuntimeError("Unknown SEED_GOOGLE_WORKSPACE; supported values: mock, live")

    return MockSeedIntakeOrchestrator(
        google_workspace=google_workspace,
        markdown_writer=markdown_writer,
        repo_root=root,
    )


def _error_record(
    *,
    error_code: str,
    step: str,
    artifact_id: str | None,
    message: str,
    manual_action: str,
    timestamp: str,
    severity: str,
) -> ErrorRecord:
    return ErrorRecord(
        error_code=error_code,
        agent=AGENT_NAME,
        step=step,
        artifact_id=artifact_id,
        message=message,
        manual_action=manual_action,
        timestamp=timestamp,
        severity=severity,
    )
