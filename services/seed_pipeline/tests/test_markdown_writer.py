import tempfile
import unittest
from pathlib import Path

from seed_pipeline.intake.markdown_writer import (
    ProcessedMessageRegistry,
    SeedDuplicateError,
    SeedMarkdownWriter,
)
from seed_pipeline.schemas import SeedInput


class SeedMarkdownWriterTests(unittest.TestCase):
    @staticmethod
    def _seed_input(message_id: str = "tg-msg-1", material: str = "Материал") -> SeedInput:
        return SeedInput(
            telegram_message_id=message_id,
            telegram_user_id="tg-user-synthetic-pavel",
            received_at="2026-04-27T10:00:00+04:00",
            material=material,
            comment="Комментарий Павла",
            source_url=None,
        )

    def test_writer_creates_minimal_markdown_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            writer = SeedMarkdownWriter(
                seed_root=root / "seeds",
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            created = writer.write(self._seed_input())

            self.assertEqual(created.seed_plan.seed_id, "2026-04-27-001")
            self.assertEqual(created.seed_plan.full_markdown_path, "seeds/2026/full/2026-04-27-001-f.md")
            self.assertEqual(created.seed_plan.slim_markdown_path, "seeds/2026/slim/2026-04-27-001-s.md")
            full_content = created.full_file.read_text(encoding="utf-8")
            slim_content = created.slim_file.read_text(encoding="utf-8")
            self.assertIn("# Технические сведения", full_content)
            self.assertIn("input_fingerprint", full_content)
            self.assertIn("[Короткая версия Seed](", full_content)
            self.assertIn("/slim/2026-04-27-001-s.md", full_content)
            self.assertIn("[2026-04-27-001](", slim_content)
            self.assertIn("/full/2026-04-27-001-f.md", slim_content)
            self.assertNotIn("input_fingerprint", slim_content)
            self.assertFalse(created.seed_plan.firestore_required)

    def test_writer_increments_seed_id_when_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            existing_dir = root / "seeds" / "2026" / "full"
            existing_dir.mkdir(parents=True)
            (existing_dir / "2026-04-27-001-f.md").write_text("existing", encoding="utf-8")
            writer = SeedMarkdownWriter(
                seed_root=root / "seeds",
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            created = writer.write(self._seed_input())

            self.assertEqual(created.seed_plan.seed_id, "2026-04-27-002")
            self.assertTrue((existing_dir / "2026-04-27-001-f.md").exists())
            self.assertTrue((existing_dir / "2026-04-27-002-f.md").exists())
            self.assertTrue((root / "seeds" / "2026" / "slim" / "2026-04-27-002-s.md").exists())

    def test_writer_uses_preallocated_seed_id_for_synced_external_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            writer = SeedMarkdownWriter(
                seed_root=root / "seeds",
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            created = writer.write(self._seed_input(), seed_id="2026-04-27-003")

            self.assertEqual(created.seed_plan.seed_id, "2026-04-27-003")
            self.assertTrue((root / "seeds" / "2026" / "full" / "2026-04-27-003-f.md").exists())
            self.assertTrue((root / "seeds" / "2026" / "slim" / "2026-04-27-003-s.md").exists())

    def test_duplicate_message_id_does_not_create_second_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            writer = SeedMarkdownWriter(
                seed_root=root / "seeds",
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )
            writer.write(self._seed_input(message_id="tg-msg-duplicate"))

            with self.assertRaises(SeedDuplicateError) as caught:
                writer.write(self._seed_input(message_id="tg-msg-duplicate", material="Похожий материал"))

            self.assertEqual(caught.exception.error_record.error_code, "SEED_DUPLICATE_MESSAGE")
            self.assertEqual(len(list((root / "seeds" / "2026").rglob("*.md"))), 2)

    def test_similar_material_with_new_message_id_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            writer = SeedMarkdownWriter(
                seed_root=root / "seeds",
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )
            first = writer.write(self._seed_input(message_id="tg-msg-1", material="Похожая мысль"))
            second = writer.write(self._seed_input(message_id="tg-msg-2", material="Похожая мысль"))

            self.assertEqual(first.seed_plan.seed_id, "2026-04-27-001")
            self.assertEqual(second.seed_plan.seed_id, "2026-04-27-002")

    def test_write_error_does_not_leave_temp_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            seed_root = root / "seeds"
            seed_root.write_text("not a directory", encoding="utf-8")
            writer = SeedMarkdownWriter(
                seed_root=seed_root,
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            with self.assertRaises(OSError):
                writer.write(self._seed_input())

            self.assertFalse((root / "processed.json").exists())


if __name__ == "__main__":
    unittest.main()
