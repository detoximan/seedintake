import tempfile
import unittest
from pathlib import Path

from seed_pipeline.intake.github_storage import GitHubFile, GitHubSeedMarkdownWriter
from seed_pipeline.intake.markdown_writer import ProcessedMessageRegistry
from seed_pipeline.schemas import SeedInput


class FakeGitHubContentsClient:
    repository = "detoximan/seedintake"
    branch = "main"

    def __init__(self, *, fail_on_path: str | None = None) -> None:
        self.files: dict[str, tuple[str, str]] = {}
        self.deleted: list[str] = []
        self.fail_on_path = fail_on_path

    def get_file(self, path: str) -> GitHubFile | None:
        item = self.files.get(path)
        if item is None:
            return None
        _, sha = item
        return GitHubFile(path=path, sha=sha)

    def create_file(self, *, path: str, content: str, message: str) -> GitHubFile:
        if self.fail_on_path == path:
            raise RuntimeError(f"create failed for {path}")
        if path in self.files:
            raise RuntimeError(f"file exists: {path}")
        sha = f"sha-{len(self.files) + 1}"
        self.files[path] = (content, sha)
        return GitHubFile(path=path, sha=sha)

    def delete_file(self, *, path: str, sha: str, message: str) -> None:
        self.deleted.append(path)
        self.files.pop(path, None)


class GitHubSeedMarkdownWriterTests(unittest.TestCase):
    @staticmethod
    def _seed_input(message_id: str = "tg-msg-github-1") -> SeedInput:
        return SeedInput(
            telegram_message_id=message_id,
            telegram_user_id="tg-user-synthetic-pavel",
            received_at="2026-04-27T10:00:00+04:00",
            material="Текстовый seed для Cloud Run",
            comment="Комментарий Павла",
            source_url=None,
        )

    def test_writer_creates_full_and_slim_via_github_contents_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            client = FakeGitHubContentsClient()
            writer = GitHubSeedMarkdownWriter(
                client=client,  # type: ignore[arg-type]
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            created = writer.write(self._seed_input())

            self.assertEqual(created.seed_plan.seed_id, "2026-04-27-001")
            self.assertIn("Inbox/2026/full/2026-04-27-001-f.md", client.files)
            self.assertIn("Inbox/2026/slim/2026-04-27-001-s.md", client.files)
            full_content, _ = client.files["Inbox/2026/full/2026-04-27-001-f.md"]
            slim_content, _ = client.files["Inbox/2026/slim/2026-04-27-001-s.md"]
            self.assertIn("[Короткая версия Seed](", full_content)
            self.assertIn("/slim/2026-04-27-001-s.md", full_content)
            self.assertIn("/full/2026-04-27-001-f.md", slim_content)
            self.assertEqual(created.seed_plan.external_calls, ["github_contents_api"])

    def test_writer_rolls_back_full_if_slim_create_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            slim_path = "Inbox/2026/slim/2026-04-27-001-s.md"
            client = FakeGitHubContentsClient(fail_on_path=slim_path)
            writer = GitHubSeedMarkdownWriter(
                client=client,  # type: ignore[arg-type]
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            with self.assertRaises(RuntimeError):
                writer.write(self._seed_input())

            self.assertEqual(client.files, {})
            self.assertEqual(client.deleted, ["Inbox/2026/full/2026-04-27-001-f.md"])

    def test_next_seed_id_skips_existing_remote_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            client = FakeGitHubContentsClient()
            client.files["Inbox/2026/full/2026-04-27-001-f.md"] = ("existing", "sha-existing")
            writer = GitHubSeedMarkdownWriter(
                client=client,  # type: ignore[arg-type]
                registry=ProcessedMessageRegistry(root / "processed.json", repo_root=root),
                repo_root=root,
            )

            self.assertEqual(writer.next_seed_id("2026-04-27T10:00:00+04:00"), "2026-04-27-002")


if __name__ == "__main__":
    unittest.main()
