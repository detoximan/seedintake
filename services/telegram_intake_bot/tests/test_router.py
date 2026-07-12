import unittest

from telegram_intake_bot.router import BUTTON_END_SESSION, BUTTON_SEED, BUTTON_TASK, MAIN_MENU_KEYBOARD, IntakeRouter
from telegram_intake_bot.types import FlowName, FlowResponse, InboundUpdate


class ActiveSeedShell:
    flow = FlowName.SEED
    implemented = True
    activates_session_on_start = True

    def on_start(self, update: InboundUpdate) -> str:
        return "seed shell started"

    def on_repeat_start(self, update: InboundUpdate) -> str:
        return "seed shell already active"

    def on_message(self, update: InboundUpdate) -> str:
        return "seed shell message"


class StandaloneSeedUrlFlow:
    flow = FlowName.SEED
    implemented = True
    activates_session_on_start = True

    def __init__(self) -> None:
        self.started = 0
        self.messages: list[str] = []

    def on_start(self, update: InboundUpdate) -> FlowResponse:
        self.started += 1
        return FlowResponse(text="seed started")

    def on_repeat_start(self, update: InboundUpdate) -> str:
        return "seed already active"

    def on_message(self, update: InboundUpdate) -> FlowResponse:
        self.messages.append(update.text)
        return FlowResponse(text="queued standalone url", end_session=True)


class IntakeRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = IntakeRouter()

    def _update(self, text: str, chat_id: int = 1) -> InboundUpdate:
        return InboundUpdate(chat_id=chat_id, text=text, user_id=100)

    def test_task_command_starts_task_session(self) -> None:
        reply = self.router.process(self._update("/task"))
        self.assertEqual("Запишите задачу", reply.text)
        session = self.router.session_store.get(1)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.flow, FlowName.TASK)

    def test_task_button_starts_task_session(self) -> None:
        reply = self.router.process(self._update(BUTTON_TASK))
        self.assertEqual("Запишите задачу", reply.text)
        session = self.router.session_store.get(1)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.flow, FlowName.TASK)

    def test_start_shows_main_menu_keyboard(self) -> None:
        reply = self.router.process(self._update("/start"))
        self.assertIn("Выберите", reply.text)
        self.assertEqual(reply.reply_markup, MAIN_MENU_KEYBOARD)

    def test_seed_conflict_when_task_session_is_active(self) -> None:
        self.router.process(self._update("/task"))
        reply = self.router.process(self._update("/seed"))
        self.assertIn("Сейчас активен flow /task", reply.text)

    def test_cancel_clears_active_session(self) -> None:
        self.router.process(self._update("/task"))
        reply = self.router.process(self._update(BUTTON_END_SESSION))
        self.assertIn("Сессия /task завершена", reply.text)
        self.assertEqual(reply.reply_markup, MAIN_MENU_KEYBOARD)
        self.assertIsNone(self.router.session_store.get(1))

    def test_seed_command_starts_seed_session(self) -> None:
        reply = self.router.process(self._update("/seed"))
        self.assertEqual("Отправьте исходник (голос, текст или ссылка)", reply.text)
        session = self.router.session_store.get(1)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.flow, FlowName.SEED)

    def test_seed_button_starts_seed_session(self) -> None:
        reply = self.router.process(self._update(BUTTON_SEED))
        self.assertEqual("Отправьте исходник (голос, текст или ссылка)", reply.text)
        session = self.router.session_store.get(1)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.flow, FlowName.SEED)

    def test_unknown_input_without_session_returns_help(self) -> None:
        reply = self.router.process(self._update("hello"))
        self.assertIn(BUTTON_TASK, reply.text)
        self.assertEqual(reply.reply_markup, MAIN_MENU_KEYBOARD)

    def test_caption_from_telegram_share_is_normalized_as_text(self) -> None:
        update = InboundUpdate.from_telegram_update(
            {
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 1},
                    "from": {"id": 100},
                    "photo": [{"file_id": "p1", "width": 1, "height": 1}],
                    "caption": "https://www.instagram.com/reel/ABC/",
                },
            }
        )

        self.assertEqual(update.text, "https://www.instagram.com/reel/ABC/")

    def test_url_without_session_auto_routes_to_seed_flow(self) -> None:
        seed_flow = StandaloneSeedUrlFlow()
        router = IntakeRouter(seed_flow=seed_flow)

        reply = router.process(self._update("https://www.threads.net/@user/post/abc"))

        self.assertEqual(reply.text, "queued standalone url")
        self.assertEqual(seed_flow.started, 1)
        self.assertEqual(seed_flow.messages, ["https://www.threads.net/@user/post/abc"])
        self.assertIsNone(router.session_store.get(1))

    def test_task_command_with_bot_suffix_is_supported(self) -> None:
        reply = self.router.process(self._update("/task@detoximan_bot"))
        self.assertEqual("Запишите задачу", reply.text)
        session = self.router.session_store.get(1)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.flow, FlowName.TASK)

    def test_task_is_blocked_when_seed_session_is_active(self) -> None:
        router = IntakeRouter(seed_flow=ActiveSeedShell())
        router.process(self._update("/seed"))
        reply = router.process(self._update("/task"))
        self.assertIn("Сейчас активен flow /seed", reply.text)


if __name__ == "__main__":
    unittest.main()
