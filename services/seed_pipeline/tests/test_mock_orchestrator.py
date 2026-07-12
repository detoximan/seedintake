import tempfile
import unittest
from pathlib import Path

from seed_pipeline.integrations import MockGoogleWorkspace
from seed_pipeline.intake.mock_orchestrator import MockSeedIntakeOrchestrator
from seed_pipeline.intake.markdown_writer import ProcessedMessageRegistry
from seed_pipeline.schemas import SeedInput


class MockSeedIntakeOrchestratorTests(unittest.TestCase):
    @staticmethod
    def _seed_input(message_id: str = "tg-msg-1001") -> SeedInput:
        return SeedInput(
            telegram_message_id=message_id,
            telegram_user_id="tg-user-synthetic-pavel",
            received_at="2026-04-27T10:00:00+04:00",
            material="Человек спорит не с фактом, а с собственной интерпретацией факта.",
            comment="Хочу сохранить как seed про отделение фактов от интерпретаций.",
            source_url=None,
        )

    def test_success_creates_markdown_seed_pair_then_sheet_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = MockGoogleWorkspace()
            orchestrator = MockSeedIntakeOrchestrator(
                google_workspace=workspace,
                seed_root=root / "seeds",
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            result = orchestrator.create_seed(self._seed_input())

            self.assertEqual(result.status, "ok")
            self.assertIsNotNone(result.seed_plan)
            self.assertIsNotNone(result.google_workspace)
            assert result.seed_plan is not None
            assert result.google_workspace is not None
            self.assertEqual(result.seed_plan.seed_id, "2026-04-27-001")
            self.assertEqual(result.markdown_path, "seeds/2026/slim/2026-04-27-001-s.md")
            self.assertEqual(result.seed_plan.full_markdown_path, "seeds/2026/full/2026-04-27-001-f.md")
            self.assertIn("/full/2026-04-27-001-f.md", result.seed_plan.full_github_url)
            self.assertEqual(result.google_workspace.status, "ok")
            self.assertEqual(len(workspace.sheets_adapter.rows), 1)
            full_file = root / "seeds" / "2026" / "full" / "2026-04-27-001-f.md"
            slim_file = root / "seeds" / "2026" / "slim" / "2026-04-27-001-s.md"
            self.assertTrue(full_file.exists())
            self.assertTrue(slim_file.exists())
            self.assertIn(result.seed_plan.full_github_url, slim_file.read_text(encoding="utf-8"))
            self.assertEqual(orchestrator.registry.find("tg-msg-1001"), "2026-04-27-001")

    def test_markdown_failure_creates_no_sheet_or_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            seed_root = root / "seeds"
            seed_root.write_text("not a directory", encoding="utf-8")
            workspace = MockGoogleWorkspace()
            orchestrator = MockSeedIntakeOrchestrator(
                google_workspace=workspace,
                seed_root=seed_root,
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            result = orchestrator.create_seed(self._seed_input())

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.seed_plan)
            self.assertIsNotNone(result.error_record)
            assert result.error_record is not None
            self.assertEqual(result.error_record.error_code, "MARKDOWN_SEED_WRITE_FAILED")
            self.assertEqual(len(workspace.sheets_adapter.rows), 0)
            self.assertFalse((root / "processed.json").exists())

    def test_google_sheet_failure_rolls_back_markdown_and_skips_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = MockGoogleWorkspace(fail_step="google_sheets")
            orchestrator = MockSeedIntakeOrchestrator(
                google_workspace=workspace,
                seed_root=root / "seeds",
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            result = orchestrator.create_seed(self._seed_input())

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.seed_plan)
            self.assertIsNotNone(result.google_workspace)
            assert result.google_workspace is not None
            self.assertEqual(result.google_workspace.status, "error")
            self.assertIsNone(result.google_workspace.google_doc)
            self.assertIsNone(result.google_workspace.google_sheet_row)
            self.assertEqual(len(workspace.sheets_adapter.rows), 0)
            self.assertEqual(len(list((root / "seeds").rglob("*.md"))) if (root / "seeds").exists() else 0, 0)
            self.assertFalse((root / "processed.json").exists())

    def test_duplicate_message_does_not_create_new_google_or_markdown_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = MockGoogleWorkspace()
            orchestrator = MockSeedIntakeOrchestrator(
                google_workspace=workspace,
                seed_root=root / "seeds",
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )
            first = orchestrator.create_seed(self._seed_input(message_id="tg-msg-duplicate"))

            second = orchestrator.create_seed(self._seed_input(message_id="tg-msg-duplicate"))

            self.assertEqual(first.status, "ok")
            self.assertEqual(second.status, "warning")
            self.assertIsNone(second.seed_plan)
            self.assertIsNone(second.google_workspace)
            self.assertIsNotNone(second.error_record)
            assert second.error_record is not None
            self.assertEqual(second.error_record.error_code, "SEED_DUPLICATE_MESSAGE")
            self.assertEqual(len(workspace.sheets_adapter.rows), 1)
            self.assertEqual(len(list((root / "seeds" / "2026").rglob("*.md"))), 2)


if __name__ == "__main__":
    unittest.main()
