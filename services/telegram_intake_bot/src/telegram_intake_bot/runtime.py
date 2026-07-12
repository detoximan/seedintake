from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import BotConfig
from .errors import build_error_record
from .router import IntakeRouter
from .types import InboundUpdate


class TelegramApiError(RuntimeError):
    pass


class TelegramApiClient:
    def __init__(self, token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"

    def get_me(self) -> dict[str, Any]:
        response = self._post_json("getMe", {})
        result = response.get("result", {})
        return result if isinstance(result, dict) else {}

    def get_webhook_info(self) -> dict[str, Any]:
        response = self._post_json("getWebhookInfo", {})
        result = response.get("result", {})
        return result if isinstance(result, dict) else {}

    def delete_webhook(self, *, drop_pending_updates: bool = False) -> bool:
        response = self._post_json("deleteWebhook", {"drop_pending_updates": drop_pending_updates})
        return bool(response.get("result"))

    def set_webhook(
        self,
        *,
        url: str,
        secret_token: str | None = None,
        drop_pending_updates: bool = False,
    ) -> bool:
        payload: dict[str, Any] = {
            "url": url,
            "drop_pending_updates": drop_pending_updates,
            "allowed_updates": ["message", "edited_message"],
        }
        if secret_token:
            payload["secret_token"] = secret_token
        response = self._post_json("setWebhook", payload)
        return bool(response.get("result"))

    def set_my_commands(self, commands: list[dict[str, str]]) -> bool:
        response = self._post_json("setMyCommands", {"commands": commands})
        return bool(response.get("result"))

    def get_updates(self, *, offset: int | None = None, timeout: int = 25) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        response = self._post_json("getUpdates", payload)
        return response.get("result", [])

    def send_message(self, *, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        self._post_json("sendMessage", payload)

    def _post_json(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url=f"{self._base_url}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                decoded = response.read().decode("utf-8")
        except HTTPError as exc:
            raise TelegramApiError(f"Telegram API error on {method}: {self._http_error_message(exc)}") from exc
        except URLError as exc:
            raise TelegramApiError(f"Telegram connection error on {method}: {exc.reason}") from exc

        data = json.loads(decoded)
        if not data.get("ok"):
            description = data.get("description", "unknown error")
            raise TelegramApiError(f"Telegram API error on {method}: {description}")

        return data

    @staticmethod
    def _http_error_message(exc: HTTPError) -> str:
        message = f"HTTP {exc.code}"
        try:
            body = exc.read().decode("utf-8")
            data = json.loads(body)
        except Exception:
            return message

        description = data.get("description") if isinstance(data, dict) else None
        if description:
            return f"{message}: {description}"
        return message


@dataclass
class PollingRunner:
    router: IntakeRouter
    client: TelegramApiClient
    config: BotConfig

    def run_forever(self) -> None:
        offset: int | None = None
        while True:
            try:
                updates = self.client.get_updates(offset=offset, timeout=self.config.polling_timeout_seconds)
                for raw_update in updates:
                    update_id = raw_update.get("update_id")
                    if isinstance(update_id, int):
                        offset = update_id + 1

                    try:
                        normalized = InboundUpdate.from_telegram_update(raw_update)
                    except Exception:
                        continue

                    if not self.config.is_user_allowed(normalized.user_id):
                        self.client.send_message(
                            chat_id=normalized.chat_id,
                            text="Этот бот не принимает сообщения от текущего пользователя.",
                        )
                        continue

                    reply = self.router.process(normalized)
                    self.client.send_message(
                        chat_id=reply.chat_id,
                        text=reply.text,
                        reply_markup=dict(reply.reply_markup) if reply.reply_markup is not None else None,
                    )
            except TelegramApiError as exc:
                # Backoff without crashing runtime loop.
                _ = build_error_record(
                    error_code="TELEGRAM_POLLING_ERROR",
                    step="polling_loop",
                    message=str(exc),
                    severity="error",
                    manual_action="Проверить token/network и перезапустить polling.",
                )
                print(f"telegram_polling_error: {exc}", file=sys.stderr, flush=True)
                time.sleep(3)
            except KeyboardInterrupt:
                raise
            except Exception:
                time.sleep(1)
