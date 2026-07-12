import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from seed_pipeline.cli import main
from seed_pipeline.integrations import MockGoogleWorkspace
from seed_pipeline.intake import MockSeedIntakeOrchestrator
from seed_pipeline.intake.markdown_writer import ProcessedMessageRegistry, SeedMarkdownWriter
from seed_pipeline.link_worker.processors import FailingLinkProcessor, FakeLinkProcessor, YouTubeShortsProcessor
from seed_pipeline.link_worker.queue import LinkQueueItem, LinkQueueStore
from seed_pipeline.link_worker.worker import LinkWorker


class LinkWorkerTests(unittest.TestCase):
    def test_store_lists_new_queue_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self._write_queue_item(root, "2026-04-30-001-link.md", status="new")
            self._write_queue_item(root, "2026-04-30-002-link.md", status="processed")

            store = LinkQueueStore(repo_root=root)
            items = store.list_items(status="new")

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].relative_path, "Inbox/2026/links/2026-04-30-001-link.md")
            self.assertEqual(items[0].context, "Павел context")

    def test_process_success_creates_seed_and_marks_queue_processed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            queue_path = self._write_queue_item(root, "2026-04-30-001-link.md", status="new")
            worker = self._worker(root)

            result = worker.process_file(queue_path)

            self.assertEqual(result.status, "processed")
            self.assertEqual(result.seed_id, "2026-04-30-001")
            self.assertEqual(result.seed_path, "Inbox/2026/slim/2026-04-30-001-s.md")
            self.assertTrue((root / "Inbox/2026/full/2026-04-30-001-f.md").exists())
            self.assertTrue((root / "Inbox/2026/slim/2026-04-30-001-s.md").exists())
            updated = queue_path.read_text(encoding="utf-8")
            self.assertIn("status: processed", updated)
            self.assertIn("processed_seed_id: 2026-04-30-001", updated)
            self.assertIn("processed_seed_path: Inbox/2026/slim/2026-04-30-001-s.md", updated)

    def test_process_failure_marks_queue_failed_without_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            queue_path = self._write_queue_item(root, "2026-04-30-001-link.md", status="new")
            worker = self._worker(root, processor=FailingLinkProcessor("download not available"))

            result = worker.process_file(queue_path)

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.reason, "download not available")
            self.assertFalse((root / "Inbox/2026/full/2026-04-30-001-f.md").exists())
            updated = queue_path.read_text(encoding="utf-8")
            self.assertIn("status: failed", updated)
            self.assertIn("failure_reason: download not available", updated)

    def test_youtube_shorts_processor_uses_transcript_and_deletes_temp_audio(self) -> None:
        downloader = FakeAudioDownloader()
        transcriber = FakeAudioTranscriber("короткая транскрибация")
        processor = YouTubeShortsProcessor(downloader=downloader, transcriber=transcriber)

        result = processor.process(
            LinkQueueItem(
                path=Path("Inbox/2026/links/2026-04-30-001-link.md"),
                relative_path="Inbox/2026/links/2026-04-30-001-link.md",
                status="new",
                url="https://www.youtube.com/shorts/abc123",
                platform="youtube_shorts",
                context="Павел context",
            )
        )

        self.assertIn("короткая транскрибация", result.material)
        self.assertEqual(result.comment, "Павел context")
        self.assertIsNotNone(downloader.audio_path)
        self.assertFalse(downloader.audio_path.exists())
        self.assertFalse(downloader.audio_path.parent.exists())
        self.assertEqual(transcriber.paths, [downloader.audio_path])

    def test_youtube_shorts_worker_creates_seed_and_marks_queue_processed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            queue_path = self._write_queue_item(
                root,
                "2026-04-30-001-link.md",
                status="new",
                url="https://www.youtube.com/shorts/abc123",
                platform="youtube_shorts",
            )
            worker = self._worker(
                root,
                processor=YouTubeShortsProcessor(
                    downloader=FakeAudioDownloader(),
                    transcriber=FakeAudioTranscriber("транскрибация shorts"),
                ),
            )

            result = worker.process_file(queue_path)

            self.assertEqual(result.status, "processed")
            full = (root / "Inbox/2026/full/2026-04-30-001-f.md").read_text(encoding="utf-8")
            self.assertIn("# Ссылка на исходный материал", full)
            self.assertIn("https://www.youtube.com/shorts/abc123", full)
            self.assertIn("транскрибация shorts", full)
            updated = queue_path.read_text(encoding="utf-8")
            self.assertIn("status: processed", updated)
            self.assertIn("processed_seed_id: 2026-04-30-001", updated)

    def test_youtube_shorts_failure_marks_queue_failed_and_deletes_temp_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            queue_path = self._write_queue_item(
                root,
                "2026-04-30-001-link.md",
                status="new",
                url="https://www.youtube.com/shorts/abc123",
                platform="youtube_shorts",
            )
            downloader = FakeAudioDownloader()
            worker = self._worker(
                root,
                processor=YouTubeShortsProcessor(
                    downloader=downloader,
                    transcriber=FakeAudioTranscriber("blocked", fail=True),
                ),
            )

            result = worker.process_file(queue_path)

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.reason, "blocked")
            self.assertIsNotNone(downloader.audio_path)
            self.assertFalse(downloader.audio_path.exists())
            self.assertFalse(downloader.audio_path.parent.exists())
            self.assertFalse((root / "Inbox/2026/full/2026-04-30-001-f.md").exists())
            updated = queue_path.read_text(encoding="utf-8")
            self.assertIn("status: failed", updated)
            self.assertIn("failure_reason: blocked", updated)

    def test_process_limit_only_handles_requested_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self._write_queue_item(root, "2026-04-30-001-link.md", status="new")
            self._write_queue_item(root, "2026-04-30-002-link.md", status="new")
            worker = self._worker(root)

            results = worker.process(limit=1)

            self.assertEqual(len(results), 1)
            self.assertIn("status: processed", (root / "Inbox/2026/links/2026-04-30-001-link.md").read_text(encoding="utf-8"))
            self.assertIn("status: new", (root / "Inbox/2026/links/2026-04-30-002-link.md").read_text(encoding="utf-8"))

    def test_seed_pipeline_cli_lists_link_worker_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self._write_queue_item(root, "2026-04-30-001-link.md", status="new")

            with patch("sys.stdout", new=io.StringIO()) as stdout:
                exit_code = main(["link-worker", "--repo-root", str(root), "list", "--json"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload[0]["path"], "Inbox/2026/links/2026-04-30-001-link.md")

    def _worker(self, root: Path, processor: object | None = None) -> LinkWorker:
        registry = ProcessedMessageRegistry(root / "runtime/tmp/seed_pipeline/processed.json", repo_root=root)
        markdown_writer = SeedMarkdownWriter(repo_root=root, registry=registry)
        orchestrator = MockSeedIntakeOrchestrator(
            google_workspace=MockGoogleWorkspace(),
            markdown_writer=markdown_writer,
            repo_root=root,
        )
        return LinkWorker(
            queue_store=LinkQueueStore(repo_root=root),
            processor=processor or FakeLinkProcessor(),
            orchestrator=orchestrator,
            clock=lambda: datetime(2026, 4, 30, 10, 0, tzinfo=timezone.utc),
        )

    @staticmethod
    def _write_queue_item(
        root: Path,
        filename: str,
        *,
        status: str,
        url: str = "https://example.com/post",
        platform: str = "threads_post",
    ) -> Path:
        target = root / "Inbox/2026/links" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "\n\n".join(
                [
                    f"status: {status}",
                    f"url: {url}",
                    f"platform: {platform}",
                    "context: |-\n  Павел context",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return target


class FakeAudioDownloader:
    def __init__(self) -> None:
        self.audio_path: Path | None = None

    def download_audio(self, url: str, target_dir: Path) -> Path:
        self.audio_path = target_dir / "audio.mp3"
        self.audio_path.write_bytes(b"fake audio")
        return self.audio_path


class FakeAudioTranscriber:
    def __init__(self, text: str, *, fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.paths: list[Path] = []

    def transcribe(self, audio_path: Path) -> str:
        self.paths.append(audio_path)
        if self.fail:
            raise RuntimeError(self.text)
        return self.text


if __name__ == "__main__":
    unittest.main()
