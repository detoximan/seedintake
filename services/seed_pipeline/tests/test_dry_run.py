import tempfile
import unittest
from pathlib import Path

from seed_pipeline.integrations import MockGoogleWorkspace
from seed_pipeline.intake.dry_run import build_dry_run, parse_case_file


class SeedPipelineDryRunTests(unittest.TestCase):
    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[3]

    def test_text_case_builds_seed_preview_without_final_seed_write(self) -> None:
        repo_root = self._repo_root()
        case_path = repo_root / "test_cases" / "seed_intake" / "text_seed_input.md"
        seed_input, duplicate = parse_case_file(case_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime_tmp_dir = Path(tmp_dir) / "runtime"
            dry_repo_root = Path(tmp_dir) / "repo"
            result = build_dry_run(
                seed_input,
                repo_root=dry_repo_root,
                duplicate_message=duplicate,
                runtime_tmp_dir=runtime_tmp_dir,
            )

            self.assertEqual(result.status, "ok")
            self.assertIsNotNone(result.seed_plan)
            assert result.seed_plan is not None
            self.assertEqual(result.seed_plan.status, "new")
            self.assertEqual(result.seed_plan.seed_id, "2026-04-27-001")
            self.assertEqual(result.seed_plan.markdown_path, "Inbox/2026/slim/2026-04-27-001-s.md")
            self.assertEqual(result.seed_plan.full_markdown_path, "Inbox/2026/full/2026-04-27-001-f.md")
            self.assertIn("/full/2026-04-27-001-f.md", result.seed_plan.full_github_url)
            self.assertFalse(result.seed_plan.firestore_required)
            self.assertEqual(result.seed_plan.external_calls, [])
            self.assertIsNotNone(result.google_workspace)
            assert result.google_workspace is not None
            self.assertEqual(result.google_workspace.status, "ok")
            self.assertIsNotNone(result.google_workspace.google_sheet_row)
            assert result.google_workspace.google_sheet_row is not None
            self.assertEqual(result.google_workspace.google_sheet_row.id_link_text, "2026-04-27-001")
            self.assertIn("input_fingerprint", result.seed_plan.input_fingerprint)
            self.assertIn("content_hash", result.seed_plan.input_fingerprint)
            self.assertTrue(result.report_path)
            assert result.report_path is not None
            self.assertTrue(Path(result.report_path).exists())

        self.assertFalse((dry_repo_root / "1inbox" / "seeds" / "2026" / "slim" / "2026-04-27-001-s.md").exists())

    def test_link_case_preserves_source_url_in_fingerprint(self) -> None:
        repo_root = self._repo_root()
        case_path = repo_root / "test_cases" / "seed_intake" / "link_seed_input.md"
        seed_input, duplicate = parse_case_file(case_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = build_dry_run(
                seed_input,
                repo_root=repo_root,
                duplicate_message=duplicate,
                runtime_tmp_dir=Path(tmp_dir),
            )

        self.assertIsNotNone(result.seed_plan)
        assert result.seed_plan is not None
        self.assertEqual(
            result.seed_plan.input_fingerprint["source_url"],
            "https://example.com/synthetic-clear-thinking-post",
        )

    def test_duplicate_case_returns_warning_without_seed_plan(self) -> None:
        repo_root = self._repo_root()
        case_path = repo_root / "test_cases" / "seed_intake" / "duplicate_message_input.md"
        seed_input, duplicate = parse_case_file(case_path)

        result = build_dry_run(seed_input, repo_root=repo_root, duplicate_message=duplicate)

        self.assertEqual(result.status, "warning")
        self.assertIsNone(result.seed_plan)
        self.assertIsNotNone(result.error_record)
        assert result.error_record is not None
        self.assertEqual(result.error_record.error_code, "SEED_DUPLICATE_MESSAGE")
        self.assertEqual(result.error_record.severity, "warning")
        self.assertEqual(result.error_record.manual_action, "none")
        self.assertIsNone(result.google_workspace)

    def test_default_report_path_uses_runtime_tmp(self) -> None:
        repo_root = self._repo_root()
        case_path = repo_root / "test_cases" / "seed_intake" / "text_seed_input.md"
        seed_input, duplicate = parse_case_file(case_path)

        result = build_dry_run(seed_input, repo_root=repo_root, duplicate_message=duplicate)

        self.assertTrue(result.report_path)
        assert result.report_path is not None
        report_path = Path(result.report_path)
        self.assertEqual(report_path.parent, repo_root / "runtime" / "tmp" / "seed_pipeline")
        self.assertTrue(report_path.exists())

    def test_google_sheet_failure_reports_without_seed_plan(self) -> None:
        repo_root = self._repo_root()
        case_path = repo_root / "test_cases" / "seed_intake" / "text_seed_input.md"
        seed_input, duplicate = parse_case_file(case_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            dry_repo_root = Path(tmp_dir) / "repo"
            result = build_dry_run(
                seed_input,
                repo_root=dry_repo_root,
                duplicate_message=duplicate,
                runtime_tmp_dir=Path(tmp_dir) / "runtime",
                google_workspace=MockGoogleWorkspace(fail_step="google_sheets"),
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.seed_plan)
            self.assertIsNotNone(result.error_record)
            assert result.error_record is not None
            self.assertEqual(result.error_record.error_code, "GOOGLE_SHEET_MOCK_APPEND_FAILED")
            self.assertIsNotNone(result.google_workspace)
            assert result.google_workspace is not None
            self.assertEqual(result.google_workspace.status, "error")
            self.assertIsNone(result.google_workspace.google_doc)
            self.assertIsNone(result.google_workspace.google_sheet_row)
            self.assertEqual(result.google_workspace.created_artifacts, [])
            self.assertTrue(result.report_path)
            assert result.report_path is not None
            self.assertTrue(Path(result.report_path).exists())

        self.assertFalse((dry_repo_root / "1inbox" / "seeds" / "2026" / "slim" / "2026-04-27-001-s.md").exists())


if __name__ == "__main__":
    unittest.main()
