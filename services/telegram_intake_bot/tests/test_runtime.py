import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from telegram_intake_bot.runtime import TelegramApiClient, TelegramApiError


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class TelegramApiClientTests(unittest.TestCase):
    def test_http_error_includes_telegram_description_without_token(self) -> None:
        error = HTTPError(
            url="https://api.telegram.org/botSECRET/getUpdates",
            code=409,
            msg="Conflict",
            hdrs={},
            fp=BytesIO(b'{"ok":false,"description":"Conflict: webhook is active"}'),
        )

        with patch("telegram_intake_bot.runtime.urlopen", side_effect=error):
            with self.assertRaises(TelegramApiError) as caught:
                TelegramApiClient("SECRET").get_updates()

        message = str(caught.exception)
        self.assertIn("webhook is active", message)
        self.assertNotIn("SECRET", message)

    def test_delete_webhook_sends_drop_pending_updates_flag(self) -> None:
        captured_payloads: list[dict[str, object]] = []

        def fake_urlopen(request: object, timeout: int) -> _FakeResponse:
            del timeout
            data = getattr(request, "data")
            captured_payloads.append(json.loads(data.decode("utf-8")))
            return _FakeResponse({"ok": True, "result": True})

        with patch("telegram_intake_bot.runtime.urlopen", side_effect=fake_urlopen):
            deleted = TelegramApiClient("SECRET").delete_webhook(drop_pending_updates=True)

        self.assertTrue(deleted)
        self.assertEqual(captured_payloads, [{"drop_pending_updates": True}])

    def test_set_webhook_sends_secret_and_allowed_updates(self) -> None:
        captured_payloads: list[dict[str, object]] = []

        def fake_urlopen(request: object, timeout: int) -> _FakeResponse:
            del timeout
            data = getattr(request, "data")
            captured_payloads.append(json.loads(data.decode("utf-8")))
            return _FakeResponse({"ok": True, "result": True})

        with patch("telegram_intake_bot.runtime.urlopen", side_effect=fake_urlopen):
            configured = TelegramApiClient("SECRET").set_webhook(
                url="https://example.test/telegram/webhook",
                secret_token="webhook-secret",
                drop_pending_updates=True,
            )

        self.assertTrue(configured)
        self.assertEqual(
            captured_payloads,
            [
                {
                    "url": "https://example.test/telegram/webhook",
                    "drop_pending_updates": True,
                    "allowed_updates": ["message", "edited_message"],
                    "secret_token": "webhook-secret",
                }
            ],
        )

    def test_set_my_commands_sends_command_menu(self) -> None:
        captured_payloads: list[dict[str, object]] = []

        def fake_urlopen(request: object, timeout: int) -> _FakeResponse:
            del timeout
            data = getattr(request, "data")
            captured_payloads.append(json.loads(data.decode("utf-8")))
            return _FakeResponse({"ok": True, "result": True})

        commands = [{"command": "start", "description": "Показать кнопки"}]
        with patch("telegram_intake_bot.runtime.urlopen", side_effect=fake_urlopen):
            configured = TelegramApiClient("SECRET").set_my_commands(commands)

        self.assertTrue(configured)
        self.assertEqual(captured_payloads, [{"commands": commands}])


if __name__ == "__main__":
    unittest.main()
