import base64
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from telegram_intake_bot.link_queue_writer import (
    GitHubLinkQueueWriter,
    LocalLinkQueueWriter,
    build_link_queue_markdown,
    build_link_queue_writer_from_env,
)


class LinkQueueWriterTests(unittest.TestCase):
    def test_build_markdown_contains_minimal_fields(self) -> None:
        markdown = build_link_queue_markdown(
            url="https://example.com/post",
            platform="unknown",
            context="Комментарий Павла\nвторая строка",
        )

        self.assertEqual(
            markdown,
            (
                "status: new\n"
                "\n"
                "url: https://example.com/post\n"
                "\n"
                "platform: unknown\n"
                "\n"
                "context: |-\n"
                "  Комментарий Павла\n"
                "  вторая строка\n"
            ),
        )

    def test_build_markdown_omits_empty_context(self) -> None:
        markdown = build_link_queue_markdown(url="https://example.com/post", platform="unknown")

        self.assertEqual(
            markdown,
            "status: new\n\nurl: https://example.com/post\n\nplatform: unknown\n",
        )
        self.assertNotIn("context:", markdown)

    def test_local_writer_creates_link_queue_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            writer = LocalLinkQueueWriter(repo_root=root)

            item = writer.write(
                url="https://www.instagram.com/reel/abc/",
                platform="instagram_reels",
                context="Reels context",
            )

            self.assertRegex(item.relative_path, r"^Inbox/\d{4}/links/\d{4}-\d{2}-\d{2}-001-link\.md$")
            self.assertTrue(item.path.exists())
            content = item.path.read_text(encoding="utf-8")
            self.assertIn("status: new", content)
            self.assertIn("url: https://www.instagram.com/reel/abc/", content)
            self.assertIn("platform: instagram_reels", content)
            self.assertIn("context: |-", content)

    def test_local_writer_generates_unique_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            writer = LocalLinkQueueWriter(repo_root=root)

            first = writer.write(url="https://example.com/1", platform="unknown")
            second = writer.write(url="https://example.com/2", platform="unknown")

            self.assertNotEqual(first.relative_path, second.relative_path)
            self.assertTrue(first.relative_path.endswith("-001-link.md"))
            self.assertTrue(second.relative_path.endswith("-002-link.md"))

    def test_factory_uses_seed_markdown_storage_for_github(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SEED_MARKDOWN_STORAGE": "github",
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY": "pashamal/seedintake",
                "GITHUB_BRANCH": "main",
            },
            clear=True,
        ):
            writer = build_link_queue_writer_from_env()

        self.assertIsInstance(writer, GitHubLinkQueueWriter)

    def test_github_writer_creates_contract_markdown_via_client(self) -> None:
        requests: list[tuple[str, str, dict[str, object] | None]] = []
        today = datetime.now(timezone.utc)

        class FakeGitHubWriter(GitHubLinkQueueWriter):
            def _request_json(
                self,
                method: str,
                url: str,
                *,
                payload: dict[str, object] | None = None,
                expected_statuses: set[int],
            ) -> object | None:
                del expected_statuses
                requests.append((method, url, payload))
                if method == "GET":
                    return [{"type": "file", "name": f"{today.date().isoformat()}-001-link.md"}]
                return {"content": {"sha": "abc"}}

        writer = FakeGitHubWriter(token="token", repository="pashamal/seedintake")
        output = writer.write(url="https://t.me/channel/123", platform="telegram_post")

        self.assertTrue(output.relative_path.endswith(f"{today.date().isoformat()}-002-link.md"))
        self.assertEqual([item[0] for item in requests], ["GET", "PUT"])
        put_payload = requests[1][2]
        self.assertIsNotNone(put_payload)
        assert put_payload is not None
        self.assertIn("Create Seed link queue", str(put_payload.get("message")))
        encoded_content = put_payload.get("content")
        self.assertIsInstance(encoded_content, str)
        markdown = base64.b64decode(encoded_content).decode("utf-8")
        self.assertEqual(
            markdown,
            "status: new\n\nurl: https://t.me/channel/123\n\nplatform: telegram_post\n",
        )


if __name__ == "__main__":
    unittest.main()
