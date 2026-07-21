import os
import unittest
from unittest.mock import patch

from seed_pipeline.integrations.google_workspace_live import (
    LiveGoogleWorkspace,
    LiveGoogleWorkspaceConfig,
    LiveGoogleWorkspaceConfigError,
)
from seed_pipeline.schemas import SeedInput


class _Executable:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result if result is not None else {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class _FakeValues:
    def __init__(self) -> None:
        self.update_calls = []
        self.get_calls = []

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return _Executable({"updatedCells": 1})

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return _Executable({"values": []})


class _FakeSpreadsheets:
    def __init__(self, *, append_error: Exception | None = None) -> None:
        self.append_error = append_error
        self.batch_update_calls = []
        self.get_calls = []
        self.values_resource = _FakeValues()

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return _Executable({"sheets": [{"properties": {"sheetId": 0, "title": "Лист1"}}]})

    def batchUpdate(self, **kwargs):
        self.batch_update_calls.append(kwargs)
        return _Executable({"replies": [{}]}, self.append_error)

    def values(self):
        return self.values_resource


class _FakeSheetsService:
    def __init__(self, *, append_error: Exception | None = None) -> None:
        self.spreadsheets_resource = _FakeSpreadsheets(append_error=append_error)

    def spreadsheets(self):
        return self.spreadsheets_resource


class LiveGoogleWorkspaceTests(unittest.TestCase):
    @staticmethod
    def _config(**overrides) -> LiveGoogleWorkspaceConfig:
        values = {
            "credentials_path": "/tmp/synthetic-service-account.json",
            "sheet_id": "sheet-123",
        }
        values.update(overrides)
        return LiveGoogleWorkspaceConfig(**values)

    @staticmethod
    def _seed_input() -> SeedInput:
        return SeedInput(
            telegram_message_id="tg-msg-live-1001",
            telegram_user_id="tg-user-synthetic-pavel",
            received_at="2026-04-27T10:00:00+04:00",
            material="Человек спорит не с фактом, а с собственной интерпретацией факта.",
            comment="Хочу сохранить как seed про отделение фактов от интерпретаций.",
            source_url="https://example.test/source",
        )

    def test_live_workspace_appends_sheet_row_with_full_markdown_link(self) -> None:
        sheets = _FakeSheetsService()
        workspace = LiveGoogleWorkspace(
            config=self._config(),
            sheets_service=sheets,
        )

        result = workspace.create_seed_artifacts(
            seed_id="2026-04-27-001",
            seed_input=self._seed_input(),
            full_markdown_url="https://github.com/detoximan/seedintake/blob/main/Inbox/2026/full/2026-04-27-001-f.md",
        )

        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.google_doc)
        self.assertIsNotNone(result.google_sheet_row)
        assert result.google_sheet_row is not None
        self.assertIn("/full/2026-04-27-001-f.md", result.google_sheet_row.id_link_url)
        self.assertEqual(len(sheets.spreadsheets_resource.batch_update_calls), 1)
        append_body = sheets.spreadsheets_resource.batch_update_calls[0]["body"]
        values = append_body["requests"][0]["appendCells"]["rows"][0]["values"]
        self.assertEqual(values[0]["userEnteredValue"]["stringValue"], "2026-04-27-001")
        self.assertEqual(
            values[0]["userEnteredFormat"]["textFormat"]["link"]["uri"],
            "https://github.com/detoximan/seedintake/blob/main/Inbox/2026/full/2026-04-27-001-f.md",
        )
        self.assertEqual(values[1]["userEnteredValue"]["stringValue"], "")
        self.assertEqual(values[2]["userEnteredValue"]["stringValue"], "")
        self.assertEqual(values[3]["userEnteredValue"]["stringValue"], "Хочу сохранить как seed про отделение фактов от интерпретаций.")

    def test_live_sheet_failure_reports_error(self) -> None:
        workspace = LiveGoogleWorkspace(
            config=self._config(),
            sheets_service=_FakeSheetsService(append_error=RuntimeError("Sheet append failed")),
        )

        result = workspace.create_seed_artifacts(
            seed_id="2026-04-27-001",
            seed_input=self._seed_input(),
            full_markdown_url="https://github.com/detoximan/seedintake/blob/main/Inbox/2026/full/2026-04-27-001-f.md",
        )

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.google_doc)
        self.assertIsNone(result.google_sheet_row)
        self.assertEqual(result.created_artifacts, [])
        self.assertIsNotNone(result.error_record)
        assert result.error_record is not None
        self.assertEqual(result.error_record.error_code, "GOOGLE_SHEET_LIVE_APPEND_FAILED")

    def test_live_config_requires_required_env_vars(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LiveGoogleWorkspaceConfigError) as caught:
                LiveGoogleWorkspaceConfig.from_env()

        message = str(caught.exception)
        self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", message)
        self.assertIn("GOOGLE_SHEET_ID", message)

    def test_live_config_reads_sheet_id(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/synthetic-service-account.json",
                "GOOGLE_SHEET_ID": "sheet-123",
            },
            clear=True,
        ):
            config = LiveGoogleWorkspaceConfig.from_env()

        self.assertEqual(config.sheet_id, "sheet-123")

    def test_live_config_reads_optional_sheet_gid(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/synthetic-service-account.json",
                "GOOGLE_SHEET_ID": "sheet-123",
                "GOOGLE_SHEET_GID": "42",
            },
            clear=True,
        ):
            config = LiveGoogleWorkspaceConfig.from_env()

        self.assertEqual(config.sheet_gid, 42)


if __name__ == "__main__":
    unittest.main()
