from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from seed_pipeline.schemas import ErrorRecord, GoogleSheetSeedRow, GoogleWorkspaceResult, SeedInput

AGENT_NAME = "Seed Intake Agent"
GOOGLE_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


class LiveGoogleWorkspaceConfigError(RuntimeError):
    pass


class LiveGoogleWorkspaceDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveGoogleWorkspaceConfig:
    credentials_path: str
    sheet_id: str
    sheet_gid: int | None = None
    sheet_range: str = "A:D"

    @classmethod
    def from_env(cls) -> "LiveGoogleWorkspaceConfig":
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
        sheet_gid_value = os.getenv("GOOGLE_SHEET_GID", "").strip()

        missing = [
            name
            for name, value in (
                ("GOOGLE_APPLICATION_CREDENTIALS", credentials_path),
                ("GOOGLE_SHEET_ID", sheet_id),
            )
            if not value
        ]
        if missing:
            raise LiveGoogleWorkspaceConfigError(
                "Missing Google Workspace env vars: " + ", ".join(missing)
            )

        sheet_gid = int(sheet_gid_value) if sheet_gid_value else None
        return cls(credentials_path=credentials_path, sheet_id=sheet_id, sheet_gid=sheet_gid)


class LiveGoogleWorkspace:
    def __init__(
        self,
        *,
        config: LiveGoogleWorkspaceConfig,
        sheets_service: Any | None = None,
    ) -> None:
        self.config = config
        self.sheets_service = sheets_service or _build_sheets_service(config)

    @classmethod
    def from_env(cls) -> "LiveGoogleWorkspace":
        return cls(config=LiveGoogleWorkspaceConfig.from_env())

    def create_seed_artifacts(
        self,
        *,
        seed_id: str,
        seed_input: SeedInput,
        full_markdown_url: str,
    ) -> GoogleWorkspaceResult:
        try:
            import logging
            logger = logging.getLogger(__name__)
            
            material_to_write = (seed_input.material or "").strip()
            if not material_to_write:
                material_to_write = "текста нет"
                
            row_payload = {
                "url": seed_input.source_url,
                "views": seed_input.views,
                "likes": seed_input.likes,
                "comment": seed_input.comment,
                "material": material_to_write,
            }
                
            logger.warning(
                "BEFORE SHEET WRITE: url=%s material_len=%s sheet_text_preview=%r row_payload=%r",
                seed_input.source_url,
                len(material_to_write or ""),
                (material_to_write or "")[:1000],
                row_payload,
            )
            
            logger.warning(
                "WRITE TARGET: url=%s sheet_id=%s sheet_range=%s",
                seed_input.source_url,
                self.config.sheet_id,
                self.config.sheet_range,
            )
            
            # Create a modified seed_input with the processed material
            modified_seed_input = SeedInput(
                telegram_message_id=seed_input.telegram_message_id,
                telegram_user_id=seed_input.telegram_user_id,
                received_at=seed_input.received_at,
                material=material_to_write,
                comment=seed_input.comment,
                source_url=seed_input.source_url,
                views=seed_input.views,
                likes=seed_input.likes,
            )
            
            google_sheet_row = self.append_seed_registry_row(
                seed_id=seed_id,
                full_markdown_url=full_markdown_url,
                seed_input=modified_seed_input,
            )
            
            logger.warning("SHEET UPDATE RESULT: success, row appended")
            
        except Exception as exc:
            return GoogleWorkspaceResult(
                status="error",
                google_doc=None,
                google_sheet_row=None,
                error_record=_error_record(
                    error_code="GOOGLE_SHEET_LIVE_APPEND_FAILED",
                    step="write_google_sheet_row",
                    artifact_id=seed_id,
                    message=_safe_error_message(exc),
                    manual_action="Check Google Sheet access for the service account, then retry.",
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

    def append_seed_registry_row(
        self,
        *,
        seed_id: str,
        full_markdown_url: str,
        seed_input: SeedInput,
    ) -> GoogleSheetSeedRow:
        self.ensure_headers()
        row = GoogleSheetSeedRow(
            seed_id=seed_id,
            id_link_text=seed_id,
            id_link_url=full_markdown_url,
            views=seed_input.views,
            likes=seed_input.likes,
            pavel_comment=_normalize_or_default(seed_input.comment, "Без комментария."),
            normalized_text=seed_input.material.strip(),
        )
        self.sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=self.config.sheet_id,
            body={
                "requests": [
                    {
                        "appendCells": {
                            "sheetId": self._target_sheet_gid(),
                            "rows": [
                                {
                                    "values": [
                                        _linked_string_cell(row.id_link_text, row.id_link_url),
                                        _string_cell(row.views),
                                        _string_cell(row.likes),
                                        _string_cell(row.pavel_comment),
                                        _string_cell(row.normalized_text),
                                    ]
                                }
                            ],
                            "fields": "userEnteredValue,userEnteredFormat.textFormat.link",
                        }
                    }
                ]
            },
        ).execute()
        return row

    def ensure_headers(self) -> None:
        """Ensure the first row has the correct headers: ID, Просмотры, Лайки, Комментарий, Транскрибация источника."""
        headers = ["ID", "Просмотры", "Лайки", "Комментарий Павла", "Транскрибация источника"]
        self.sheets_service.spreadsheets().values().update(
            spreadsheetId=self.config.sheet_id,
            range=f"A1:E1",
            valueInputOption="RAW",
            body={"values": [headers]},
        ).execute()

    def _target_sheet_gid(self) -> int:
        if self.config.sheet_gid is not None:
            return self.config.sheet_gid
        spreadsheet = self.sheets_service.spreadsheets().get(spreadsheetId=self.config.sheet_id).execute()
        sheets = spreadsheet.get("sheets", [])
        if not sheets:
            raise LiveGoogleWorkspaceConfigError("Google Sheet contains no sheets.")
        return spreadsheet.get("sheets", [])[0]["properties"]["sheetId"]

    def get_all_rows(self) -> list[list[str]]:
        """Get all rows from the sheet for matching seed_ids."""
        result = self.sheets_service.spreadsheets().values().get(
            spreadsheetId=self.config.sheet_id,
            range="A:E"
        ).execute()
        return result.get("values", [])

    def update_range(self, range_name: str, values: list[list[str]]) -> None:
        """Update a specific range with provided values."""
        self.sheets_service.spreadsheets().values().update(
            spreadsheetId=self.config.sheet_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": values}
        ).execute()


def config_error_record(*, message: str, timestamp: str) -> ErrorRecord:
    return _error_record(
        error_code="GOOGLE_WORKSPACE_CONFIG_MISSING",
        step="configure_google_workspace",
        artifact_id=None,
        message=message,
        manual_action=(
            "Set GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_SHEET_ID in the protected local environment, "
            "then retry live smoke."
        ),
        timestamp=timestamp,
        severity="error",
    )


def dependency_error_record(*, message: str, timestamp: str) -> ErrorRecord:
    return _error_record(
        error_code="GOOGLE_WORKSPACE_DEPENDENCY_MISSING",
        step="load_google_workspace_client",
        artifact_id=None,
        message=message,
        manual_action=(
            "Install seed_pipeline dependencies from services/seed_pipeline/pyproject.toml "
            "in the local environment, then retry live smoke."
        ),
        timestamp=timestamp,
        severity="error",
    )


def _build_sheets_service(config: LiveGoogleWorkspaceConfig) -> Any:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise LiveGoogleWorkspaceDependencyError(
            "Google API client packages are not installed for seed_pipeline."
        ) from exc

    credentials = service_account.Credentials.from_service_account_file(
        config.credentials_path,
        scopes=list(GOOGLE_SCOPES),
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _string_cell(value: str) -> dict[str, Any]:
    return {"userEnteredValue": {"stringValue": value}}


def _linked_string_cell(text: str, url: str) -> dict[str, Any]:
    return {
        "userEnteredValue": {"stringValue": text},
        "userEnteredFormat": {"textFormat": {"link": {"uri": url}}},
    }


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


def _normalize_or_default(value: str, default: str) -> str:
    normalized = value.strip()
    return normalized if normalized else default


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if credentials_path:
        message = message.replace(credentials_path, "[GOOGLE_APPLICATION_CREDENTIALS]")
    return message[:1000]
