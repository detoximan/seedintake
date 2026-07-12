from __future__ import annotations

from seed_pipeline.schemas import (
    ErrorRecord,
    GoogleSheetSeedRow,
    GoogleWorkspaceResult,
    SeedInput,
)

AGENT_NAME = "Seed Intake Agent"


class MockGoogleWorkspaceError(RuntimeError):
    pass


class MockGoogleSheetsAdapter:
    def __init__(self, *, fail_append: bool = False) -> None:
        self.fail_append = fail_append
        self.rows: list[GoogleSheetSeedRow] = []

    def append_seed_registry_row(
        self,
        *,
        seed_id: str,
        full_markdown_url: str,
        seed_input: SeedInput,
    ) -> GoogleSheetSeedRow:
        if self.fail_append:
            raise MockGoogleWorkspaceError("Mock Google Sheets append failed.")

        row = GoogleSheetSeedRow(
            seed_id=seed_id,
            id_link_text=seed_id,
            id_link_url=full_markdown_url,
            views=seed_input.views,
            likes=seed_input.likes,
            pavel_comment=_normalize_or_default(seed_input.comment, "Без комментария."),
            normalized_text=seed_input.material.strip(),
        )
        self.rows.append(row)
        return row


class MockGoogleWorkspace:
    def __init__(
        self,
        *,
        sheets_adapter: MockGoogleSheetsAdapter | None = None,
        fail_step: str | None = None,
    ) -> None:
        if fail_step not in {None, "google_sheets"}:
            raise ValueError("fail_step must be one of: google_sheets")

        self.sheets_adapter = sheets_adapter or MockGoogleSheetsAdapter(fail_append=fail_step == "google_sheets")

    def create_seed_artifacts(self, *, seed_id: str, seed_input: SeedInput, full_markdown_url: str) -> GoogleWorkspaceResult:
        try:
            google_sheet_row = self.sheets_adapter.append_seed_registry_row(
                seed_id=seed_id,
                full_markdown_url=full_markdown_url,
                seed_input=seed_input,
            )
        except Exception as exc:
            return GoogleWorkspaceResult(
                status="error",
                google_doc=None,
                google_sheet_row=None,
                error_record=_error_record(
                    error_code="GOOGLE_SHEET_MOCK_APPEND_FAILED",
                    step="write_google_sheet_row",
                    artifact_id=seed_id,
                    message=str(exc),
                    manual_action="Retry Sheet append after checking Google Sheet access.",
                    timestamp=seed_input.received_at,
                    severity="error",
                ),
                created_artifacts=[],
            )

        return GoogleWorkspaceResult(
            status="ok",
            google_doc=None,
            google_sheet_row=google_sheet_row,
            error_record=None,
            created_artifacts=[f"google_sheet_row:{seed_id}"],
        )


def _error_record(
    *,
    error_code: str,
    step: str,
    artifact_id: str,
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


def _normalize_or_default(value: str, default: str) -> str:
    normalized = value.strip()
    return normalized if normalized else default
