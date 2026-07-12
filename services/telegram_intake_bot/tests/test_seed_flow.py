from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from telegram_intake_bot.flows.seed_intake import (
    BUTTON_CANCEL,
    BUTTON_CONTINUE,
    BUTTON_FINISH,
    SeedIntakeFlow,
    classify_link_platform,
    extract_first_url,
)
from telegram_intake_bot.link_queue_writer import LinkQueueItem
from telegram_intake_bot.router import IntakeRouter
from telegram_intake_bot.transcription import MockTranscriptionAdapter, UnavailableTranscriptionAdapter
from telegram_intake_bot.types import InboundUpdate


class _FakeSeedOrchestrator:
    def __init__(self) -> None:
        self.inputs = []

    def create_seed(self, seed_input):
        self.inputs.append(seed_input)
        return SimpleNamespace(
            status="ok",
            seed_plan=SimpleNamespace(
                seed_id="2026-04-30-001",
                full_markdown_path="Inbox/2026/full/2026-04-30-001-f.md",
                slim_markdown_path="Inbox/2026/slim/2026-04-30-001-s.md",
            ),
            error_record=None,
        )


class _FakeLinkQueueWriter:
    def __init__(self) -> None:
        self.items = []

    def write(self, *, url: str, platform: str, context: str = "") -> LinkQueueItem:
        self.items.append({"url": url, "platform": platform, "context": context})
        return LinkQueueItem(
            path=Path("/repo/Inbox/2026/links/2026-04-30-001-link.md"),
            relative_path="Inbox/2026/links/2026-04-30-001-link.md",
            url=url,
            platform=platform,
        )


class SeedIntakeFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = _FakeSeedOrchestrator()
        self.link_queue_writer = _FakeLinkQueueWriter()
        self.router = IntakeRouter(
            seed_flow=SeedIntakeFlow(
                transcription=MockTranscriptionAdapter(),
                orchestrator_factory=lambda: self.orchestrator,
                link_queue_writer=self.link_queue_writer,
            )
        )

    @staticmethod
    def _text_update(text: str, *, chat_id: int = 1, message_id: int = 10) -> InboundUpdate:
        return InboundUpdate(chat_id=chat_id, text=text, user_id=100, message_id=message_id)

    @staticmethod
    def _voice_update(*, chat_id: int = 1, file_id: str = "seed-voice-1", message_id: int = 20) -> InboundUpdate:
        return InboundUpdate.from_telegram_update(
            {
                "update_id": 99,
                "message": {
                    "message_id": message_id,
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

    def test_seed_start_shows_task_style_action_keyboard(self) -> None:
        reply = self.router.process(self._text_update("/seed"))

        self.assertEqual(reply.text, "Отправьте исходник (голос, текст или ссылка)")
        self.assertEqual(
            reply.reply_markup,
            {
                "keyboard": [[BUTTON_CONTINUE, BUTTON_FINISH, BUTTON_CANCEL]],
                "resize_keyboard": True,
                "one_time_keyboard": False,
            },
        )

    def test_multi_fragment_material_and_comment_create_seed_on_finish(self) -> None:
        self.router.process(self._text_update("/seed"))
        first_reply = self.router.process(self._text_update("Первый фрагмент материала", message_id=101))
        self.assertIn("Фрагмент материала сохранён (1)", first_reply.text)

        continue_reply = self.router.process(self._text_update(BUTTON_CONTINUE, message_id=102))
        self.assertIn("следующий фрагмент материала", continue_reply.text)

        self.router.process(self._voice_update(file_id="material-voice-2", message_id=103))
        comment_prompt = self.router.process(self._text_update(BUTTON_FINISH, message_id=104))
        self.assertIn("Материал принят", comment_prompt.text)

        self.router.process(self._text_update("Первый комментарий", message_id=105))
        continue_comment = self.router.process(self._text_update(BUTTON_CONTINUE, message_id=106))
        self.assertIn("следующий фрагмент комментария", continue_comment.text)

        self.router.process(self._voice_update(file_id="comment-voice-2", message_id=107))
        done_reply = self.router.process(self._text_update(BUTTON_FINISH, message_id=108))

        self.assertIn("Seed успешно создан: 2026-04-30-001", done_reply.text)
        self.assertIsNone(self.router.session_store.get(1))
        self.assertEqual(len(self.orchestrator.inputs), 1)
        seed_input = self.orchestrator.inputs[0]
        self.assertEqual(seed_input.telegram_message_id, "101")
        self.assertIn("Первый фрагмент материала", seed_input.material)
        self.assertIn("[voice:material-voice-2; duration=2s]", seed_input.material)
        self.assertIn("Первый комментарий", seed_input.comment)
        self.assertIn("[voice:comment-voice-2; duration=2s]", seed_input.comment)

    def test_finish_without_comment_creates_seed_with_empty_comment(self) -> None:
        self.router.process(self._text_update("/seed"))
        self.router.process(self._text_update("Материал без комментария", message_id=201))
        self.router.process(self._text_update(BUTTON_FINISH, message_id=202))

        done_reply = self.router.process(self._text_update(BUTTON_FINISH, message_id=203))

        self.assertIn("Seed успешно создан", done_reply.text)
        self.assertEqual(len(self.orchestrator.inputs), 1)
        self.assertEqual(self.orchestrator.inputs[0].comment, "")

    def test_url_material_is_queued_without_seed_or_sheet_work(self) -> None:
        self.router.process(self._text_update("/seed"))

        reply = self.router.process(
            self._text_update(
                "Контекст Павла https://www.youtube.com/shorts/abc123 досмотреть",
                message_id=301,
            )
        )

        self.assertIn("Ссылка поставлена в очередь", reply.text)
        self.assertIn("Platform: youtube_shorts", reply.text)
        self.assertIn("Inbox/2026/links/2026-04-30-001-link.md", reply.text)
        self.assertIn("Seed/Sheet сейчас не создавались", reply.text)
        self.assertIsNone(self.router.session_store.get(1))
        self.assertEqual(self.orchestrator.inputs, [])
        self.assertEqual(
            self.link_queue_writer.items,
            [
                {
                    "url": "https://www.youtube.com/shorts/abc123",
                    "platform": "youtube_shorts",
                    "context": "Контекст Павла досмотреть",
                }
            ],
        )

    def test_standalone_url_share_is_queued_without_explicit_seed_command(self) -> None:
        reply = self.router.process(
            self._text_update(
                "https://www.threads.net/@detoximan/post/abc",
                message_id=302,
            )
        )

        self.assertIn("Ссылка поставлена в очередь", reply.text)
        self.assertIn("Platform: threads_post", reply.text)
        self.assertIsNone(self.router.session_store.get(1))
        self.assertEqual(self.orchestrator.inputs, [])
        self.assertEqual(
            self.link_queue_writer.items,
            [
                {
                    "url": "https://www.threads.net/@detoximan/post/abc",
                    "platform": "threads_post",
                    "context": "",
                }
            ],
        )

    def test_finish_without_material_does_not_create_seed(self) -> None:
        self.router.process(self._text_update("/seed"))
        reply = self.router.process(self._text_update(BUTTON_FINISH))

        self.assertIn("сначала добавьте", reply.text)
        self.assertEqual(self.orchestrator.inputs, [])
        self.assertIsNotNone(self.router.session_store.get(1))

    def test_cancel_button_clears_session_without_seed(self) -> None:
        self.router.process(self._text_update("/seed"))
        self.router.process(self._text_update("Черновой материал"))

        reply = self.router.process(self._text_update(BUTTON_CANCEL))

        self.assertIn("Сессия /seed отменена", reply.text)
        self.assertEqual(self.orchestrator.inputs, [])
        self.assertIsNone(self.router.session_store.get(1))

    def test_unavailable_transcription_provider_does_not_create_seed(self) -> None:
        router = IntakeRouter(
            seed_flow=SeedIntakeFlow(
                transcription=UnavailableTranscriptionAdapter(
                    provider="google",
                    reason="credentials не настроены",
                ),
                orchestrator_factory=lambda: self.orchestrator,
                link_queue_writer=self.link_queue_writer,
            )
        )

        router.process(self._text_update("/seed"))
        reply = router.process(self._voice_update())

        self.assertIn("Не удалось обработать голосовое сообщение", reply.text)
        self.assertIsNotNone(reply.error_record)
        assert reply.error_record is not None
        self.assertEqual(reply.error_record.get("error_code"), "SEED_VOICE_TRANSCRIPTION_FAILED")
        self.assertEqual(self.orchestrator.inputs, [])

    def test_link_platform_classification(self) -> None:
        cases = {
            "https://youtube.com/shorts/abc": "youtube_shorts",
            "https://www.tiktok.com/@pavel/video/123": "tiktok",
            "https://www.instagram.com/reel/ABC/": "instagram_reels",
            "https://t.me/channel/123": "telegram_post",
            "https://www.threads.net/@user/post/abc": "threads_post",
            "https://www.instagram.com/p/ABC/": "instagram_post",
            "https://www.facebook.com/user/posts/123": "facebook_post",
            "https://example.com/post": "unknown",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(classify_link_platform(url), expected)

    def test_extract_first_url_strips_share_punctuation(self) -> None:
        self.assertEqual(
            extract_first_url("Смотри: https://www.instagram.com/reel/ABC/."),
            "https://www.instagram.com/reel/ABC/",
        )


if __name__ == "__main__":
    unittest.main()
