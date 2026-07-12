import unittest

from telegram_intake_bot.config import BotConfig
from telegram_intake_bot.router import IntakeRouter
from telegram_intake_bot.types import FlowName, InboundUpdate
from telegram_intake_bot.webhook import WebhookUpdateProcessor


class _FakeClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def send_message(self, *, chat_id: int, text: str, reply_markup: dict[str, object] | None = None) -> None:
        payload: dict[str, object] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        self.messages.append(payload)


class _EchoSeedFlow:
    flow = FlowName.SEED
    implemented = True
    activates_session_on_start = True

    def on_start(self, update: InboundUpdate) -> str:
        return "seed started"

    def on_repeat_start(self, update: InboundUpdate) -> str:
        return "seed already active"

    def on_message(self, update: InboundUpdate) -> str:
        return "seed message"


class WebhookUpdateProcessorTests(unittest.TestCase):
    def test_processes_allowed_message_and_sends_reply(self) -> None:
        client = _FakeClient()
        router = IntakeRouter(seed_flow=_EchoSeedFlow())
        processor = WebhookUpdateProcessor(
            router=router,
            client=client,  # type: ignore[arg-type]
            config=BotConfig(allowed_user_ids=frozenset({5001})),
        )

        status = processor.process(
            {
                "update_id": 1,
                "message": {
                    "message_id": 11,
                    "chat": {"id": 101},
                    "from": {"id": 5001},
                    "text": "/seed",
                },
            }
        )

        self.assertEqual(status, "processed")
        self.assertEqual(client.messages, [{"chat_id": 101, "text": "seed started"}])

    def test_blocks_disallowed_user_before_router(self) -> None:
        client = _FakeClient()
        processor = WebhookUpdateProcessor(
            router=IntakeRouter(seed_flow=_EchoSeedFlow()),
            client=client,  # type: ignore[arg-type]
            config=BotConfig(allowed_user_ids=frozenset({5001})),
        )

        status = processor.process(
            {
                "update_id": 1,
                "message": {
                    "message_id": 11,
                    "chat": {"id": 101},
                    "from": {"id": 7777},
                    "text": "/seed",
                },
            }
        )

        self.assertEqual(status, "forbidden")
        self.assertEqual(
            client.messages,
            [{"chat_id": 101, "text": "Этот бот не принимает сообщения от текущего пользователя."}],
        )

    def test_ignores_unsupported_update(self) -> None:
        client = _FakeClient()
        processor = WebhookUpdateProcessor(
            router=IntakeRouter(seed_flow=_EchoSeedFlow()),
            client=client,  # type: ignore[arg-type]
            config=BotConfig(),
        )

        status = processor.process({"update_id": 1, "callback_query": {"id": "1"}})

        self.assertEqual(status, "ignored")
        self.assertEqual(client.messages, [])


if __name__ == "__main__":
    unittest.main()
