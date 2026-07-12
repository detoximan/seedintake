import unittest

from seed_pipeline.integrations import MockGoogleWorkspace
from seed_pipeline.schemas import SeedInput


class MockGoogleWorkspaceTests(unittest.TestCase):
    @staticmethod
    def _seed_input() -> SeedInput:
        return SeedInput(
            telegram_message_id="tg-msg-1001",
            telegram_user_id="tg-user-synthetic-pavel",
            received_at="2026-04-27T10:00:00+04:00",
            material="Человек спорит не с фактом, а с собственной интерпретацией факта.",
            comment="Хочу сохранить как seed про отделение фактов от интерпретаций.",
            source_url=None,
        )

    def test_mock_workspace_appends_sheet_row_with_full_markdown_link(self) -> None:
        workspace = MockGoogleWorkspace()

        result = workspace.create_seed_artifacts(
            seed_id="2026-04-27-001",
            seed_input=self._seed_input(),
            full_markdown_url="https://github.com/pashamal/seedintake/blob/main/Inbox/2026/full/2026-04-27-001-f.md",
        )

        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.google_doc)
        self.assertIsNotNone(result.google_sheet_row)
        assert result.google_sheet_row is not None
        self.assertEqual(result.google_sheet_row.id_link_text, "2026-04-27-001")
        self.assertIn("/full/2026-04-27-001-f.md", result.google_sheet_row.id_link_url)

    def test_mock_sheet_failure_reports_error(self) -> None:
        workspace = MockGoogleWorkspace(fail_step="google_sheets")

        result = workspace.create_seed_artifacts(
            seed_id="2026-04-27-001",
            seed_input=self._seed_input(),
            full_markdown_url="https://github.com/pashamal/seedintake/blob/main/Inbox/2026/full/2026-04-27-001-f.md",
        )

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.google_doc)
        self.assertIsNone(result.google_sheet_row)
        self.assertIsNotNone(result.error_record)
        assert result.error_record is not None
        self.assertEqual(result.error_record.step, "write_google_sheet_row")


if __name__ == "__main__":
    unittest.main()
