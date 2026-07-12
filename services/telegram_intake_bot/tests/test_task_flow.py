import tempfile
import unittest
from pathlib import Path

from telegram_intake_bot.flows.task_intake import BUTTON_CANCEL, BUTTON_CONTINUE, BUTTON_FINISH, TaskIntakeFlow
from telegram_intake_bot.router import IntakeRouter
from telegram_intake_bot.task_intake_writer import TaskIntakeWriter
from telegram_intake_bot.transcription import MockTranscriptionAdapter, UnavailableTranscriptionAdapter
from telegram_intake_bot.types import InboundUpdate


class TaskIntakeFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._inbox = Path(self._tmp.name)
        self.router = IntakeRouter(
            task_flow=TaskIntakeFlow(
                writer=TaskIntakeWriter(inbox_dir=self._inbox),
                transcription=MockTranscriptionAdapter(),
            )
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _text_update(text: str, *, chat_id: int = 1) -> InboundUpdate:
        return InboundUpdate(chat_id=chat_id, text=text, user_id=100)

    @staticmethod
    def _voice_update(*, chat_id: int = 1, file_id: str = "voice-file-1") -> InboundUpdate:
        return InboundUpdate.from_telegram_update(
            {
                "update_id": 99,
                "message": {
                    "message_id": 15,
                    "chat": {"id": chat_id},
                    "from": {"id": 100},
                    "voice": {
                        "file_id": file_id,
                        "duration": 2,
                        "mime_type": "audio/ogg",
                        "file_unique_id": "u1",
                    },
                },
            }
        )

    def _created_files(self) -> list[Path]:
        return sorted(self._inbox.glob("*.md"))

    def test_single_text_fragment_creates_markdown(self) -> None:
        start_reply = self.router.process(self._text_update("/task"))
        self.assertEqual(start_reply.text, "Запишите задачу")
        self.assertEqual(
            start_reply.reply_markup,
            {
                "keyboard": [[BUTTON_CONTINUE, BUTTON_FINISH, BUTTON_CANCEL]],
                "resize_keyboard": True,
                "one_time_keyboard": False,
            },
        )

        fragment_reply = self.router.process(self._text_update("Новая задача: сделать intake"))
        self.assertIsNotNone(fragment_reply.reply_markup)
        self.assertIn("Фрагмент сохранён", fragment_reply.text)

        done_reply = self.router.process(self._text_update(BUTTON_FINISH))
        self.assertIn("Task Intake сохранён", done_reply.text)
        self.assertIsNone(self.router.session_store.get(1))

        files = self._created_files()
        self.assertEqual(len(files), 1)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("status: new", content)
        self.assertIn("# Вход Павла", content)
        self.assertIn("Новая задача: сделать intake", content)
        self.assertNotIn("created_at:", content)
        self.assertNotIn("input_type:", content)
        self.assertNotIn("source:", content)

    def test_multi_text_flow_with_continue_button(self) -> None:
        self.router.process(self._text_update("/task"))
        self.router.process(self._text_update("Первый кусок задачи"))

        continue_reply = self.router.process(self._text_update(BUTTON_CONTINUE))
        self.assertIn("пришлите следующий фрагмент", continue_reply.text.lower())

        self.router.process(self._text_update("Второй кусок задачи"))
        self.router.process(self._text_update(BUTTON_FINISH))

        files = self._created_files()
        self.assertEqual(len(files), 1)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("Первый кусок задачи", content)
        self.assertIn("Второй кусок задачи", content)

    def test_cancel_clears_session_without_artifact(self) -> None:
        self.router.process(self._text_update("/task"))
        self.router.process(self._text_update("Черновик, который отменим"))

        cancel_reply = self.router.process(self._text_update("/cancel"))
        self.assertIn("Сессия /task завершена", cancel_reply.text)
        self.assertIsNone(self.router.session_store.get(1))
        self.assertEqual(self._created_files(), [])

    def test_cancel_button_clears_session_without_artifact(self) -> None:
        self.router.process(self._text_update("/task"))
        self.router.process(self._text_update("Черновик, который отменим"))

        cancel_reply = self.router.process(self._text_update(BUTTON_CANCEL))
        self.assertIn("Сессия /task отменена", cancel_reply.text)
        self.assertIsNone(self.router.session_store.get(1))
        self.assertEqual(self._created_files(), [])

    def test_voice_fragment_uses_mock_transcription(self) -> None:
        self.router.process(self._text_update("/task"))
        voice_reply = self.router.process(self._voice_update())
        self.assertIn("Фрагмент сохранён", voice_reply.text)

        self.router.process(self._text_update(BUTTON_FINISH))
        files = self._created_files()
        self.assertEqual(len(files), 1)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("[voice:voice-file-1; duration=2s]", content)

    def test_unavailable_transcription_provider_returns_error(self) -> None:
        router = IntakeRouter(
            task_flow=TaskIntakeFlow(
                writer=TaskIntakeWriter(inbox_dir=self._inbox),
                transcription=UnavailableTranscriptionAdapter(
                    provider="google",
                    reason="credentials не настроены",
                ),
            )
        )

        router.process(self._text_update("/task"))
        reply = router.process(self._voice_update())
        self.assertIn("Не удалось обработать голосовой фрагмент", reply.text)
        self.assertIsNotNone(reply.error_record)
        assert reply.error_record is not None
        self.assertEqual(reply.error_record.get("error_code"), "TASK_VOICE_TRANSCRIPTION_FAILED")
        self.assertEqual(self._created_files(), [])


if __name__ == "__main__":
    unittest.main()
