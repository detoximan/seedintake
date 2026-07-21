import base64
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from telegram_intake_bot.task_intake_writer import (
    GitHubTaskIntakeWriter,
    TaskIntakeWriter,
    build_task_intake_writer_from_env,
)


class TaskIntakeWriterTests(unittest.TestCase):
    def test_writer_creates_contract_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = TaskIntakeWriter(inbox_dir=Path(tmp_dir))
            output = writer.write("Идея задачи из Telegram")
            content = output.read_text(encoding="utf-8")

            self.assertTrue(output.exists())
            self.assertIn("status: new", content)
            self.assertIn("# Вход Павла", content)
            self.assertIn("Идея задачи из Telegram", content)
            self.assertNotIn("created_at:", content)
            self.assertNotIn("input_type:", content)
            self.assertNotIn("source:", content)

    def test_writer_generates_unique_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = TaskIntakeWriter(inbox_dir=Path(tmp_dir))
            first = writer.write("Первая запись")
            second = writer.write("Вторая запись")

            self.assertNotEqual(first.name, second.name)
            self.assertRegex(first.name, r"^\d{4}-\d{2}-\d{2}-001t\.md$")
            self.assertRegex(second.name, r"^\d{4}-\d{2}-\d{2}-002t\.md$")
            self.assertIn("Первая запись", first.read_text(encoding="utf-8"))
            self.assertIn("Вторая запись", second.read_text(encoding="utf-8"))

    def test_writer_reserves_legacy_task_numbers_for_same_day(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        with tempfile.TemporaryDirectory() as tmp_dir:
            inbox = Path(tmp_dir)
            (inbox / f"task-intake-{today}-120000-aaaaaaaa.md").write_text("legacy 1", encoding="utf-8")
            (inbox / f"task-intake-{today}-130000-bbbbbbbb.md").write_text("legacy 2", encoding="utf-8")
            writer = TaskIntakeWriter(inbox_dir=inbox)

            output = writer.write("Третья запись дня")

            self.assertRegex(output.name, r"^\d{4}-\d{2}-\d{2}-003t\.md$")

    def test_factory_uses_local_writer_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            writer = build_task_intake_writer_from_env()

        self.assertIsInstance(writer, TaskIntakeWriter)

    def test_factory_uses_github_writer_when_enabled(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "TASK_MARKDOWN_STORAGE": "github",
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY": "detoximan/seedintake",
                "GITHUB_BRANCH": "main",
            },
            clear=True,
        ):
            writer = build_task_intake_writer_from_env()

        self.assertIsInstance(writer, GitHubTaskIntakeWriter)

    def test_github_writer_creates_contract_markdown_via_client(self) -> None:
        requests: list[tuple[str, str, dict[str, object] | None]] = []

        class FakeGitHubWriter(GitHubTaskIntakeWriter):
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
                    return None
                return {"content": {"sha": "abc"}}

        writer = FakeGitHubWriter(token="token", repository="detoximan/seedintake")
        output = writer.write("Task из Telegram")

        self.assertRegex(str(output), r"Inbox/\d{4}-\d{2}-\d{2}-001t\.md$")
        self.assertEqual([item[0] for item in requests], ["GET", "GET", "PUT"])
        put_payload = requests[2][2]
        self.assertIsNotNone(put_payload)
        assert put_payload is not None
        self.assertIn("Create Task Intake", str(put_payload.get("message")))
        self.assertIn("content", put_payload)
        encoded_content = put_payload.get("content")
        self.assertIsInstance(encoded_content, str)
        markdown = base64.b64decode(encoded_content).decode("utf-8")
        self.assertIn("status: new", markdown)
        self.assertIn("# Вход Павла", markdown)
        self.assertIn("Task из Telegram", markdown)
        self.assertNotIn("created_at:", markdown)
        self.assertNotIn("input_type:", markdown)
        self.assertNotIn("source:", markdown)


if __name__ == "__main__":
    unittest.main()
