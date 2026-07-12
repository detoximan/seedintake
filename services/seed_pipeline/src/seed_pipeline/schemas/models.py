from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SeedInput:
    telegram_message_id: str
    telegram_user_id: str
    received_at: str
    material: str
    comment: str
    source_url: str | None = None
    views: str = ""
    likes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ErrorRecord:
    error_code: str
    agent: str
    step: str
    artifact_id: str | None
    message: str
    manual_action: str
    timestamp: str
    severity: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GoogleDocSeedDossier:
    document_id: str
    url: str
    title: str
    sections: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SeedMarkdownArtifacts:
    seed_id: str
    full_path: str
    slim_path: str
    full_github_url: str
    slim_github_url: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GoogleSheetSeedRow:
    seed_id: str
    id_link_text: str
    id_link_url: str
    views: str
    likes: str
    pavel_comment: str
    normalized_text: str

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "row_values": self.to_row_values()}

    def to_row_values(self) -> list[str]:
        return [
            f'=HYPERLINK("{self.id_link_url}", "{self.id_link_text}")',
            self.views,
            self.likes,
            self.pavel_comment,
            self.normalized_text,
        ]


@dataclass(frozen=True)
class GoogleWorkspaceResult:
    status: str
    google_doc: GoogleDocSeedDossier | None
    google_sheet_row: GoogleSheetSeedRow | None
    error_record: ErrorRecord | None
    created_artifacts: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "google_doc": self.google_doc.to_dict() if self.google_doc else None,
            "google_sheet_row": self.google_sheet_row.to_dict() if self.google_sheet_row else None,
            "error_record": self.error_record.to_dict() if self.error_record else None,
            "created_artifacts": self.created_artifacts,
        }


@dataclass(frozen=True)
class SeedPlan:
    seed_id: str
    status: str
    markdown_path: str
    markdown_preview: str
    full_markdown_path: str
    slim_markdown_path: str
    full_github_url: str
    slim_github_url: str
    input_fingerprint: dict[str, object]
    firestore_required: bool
    external_calls: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunResult:
    dry_run: bool
    status: str
    seed_input: SeedInput | None
    seed_plan: SeedPlan | None
    error_record: ErrorRecord | None
    google_workspace: GoogleWorkspaceResult | None = None
    report_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "status": self.status,
            "seed_input": self.seed_input.to_dict() if self.seed_input else None,
            "seed_plan": self.seed_plan.to_dict() if self.seed_plan else None,
            "error_record": self.error_record.to_dict() if self.error_record else None,
            "google_workspace": self.google_workspace.to_dict() if self.google_workspace else None,
            "report_path": self.report_path,
        }


@dataclass(frozen=True)
class SeedCreationResult:
    status: str
    seed_input: SeedInput
    seed_plan: SeedPlan | None
    google_workspace: GoogleWorkspaceResult | None
    markdown_path: str | None
    error_record: ErrorRecord | None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "seed_input": self.seed_input.to_dict(),
            "seed_plan": self.seed_plan.to_dict() if self.seed_plan else None,
            "google_workspace": self.google_workspace.to_dict() if self.google_workspace else None,
            "markdown_path": self.markdown_path,
            "error_record": self.error_record.to_dict() if self.error_record else None,
        }
