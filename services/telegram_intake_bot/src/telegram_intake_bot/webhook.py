from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .config import BotConfig
from .router import IntakeRouter
from .runtime import TelegramApiClient
from .types import InboundUpdate


MAX_WEBHOOK_BODY_BYTES = 1024 * 1024


@dataclass
class WebhookUpdateProcessor:
    router: IntakeRouter
    client: TelegramApiClient
    config: BotConfig

    def process(self, raw_update: dict[str, Any]) -> str:
        try:
            update = InboundUpdate.from_telegram_update(raw_update)
        except Exception:
            return "ignored"

        if not self.config.is_user_allowed(update.user_id):
            self.client.send_message(
                chat_id=update.chat_id,
                text="Этот бот не принимает сообщения от текущего пользователя.",
            )
            return "forbidden"

        reply = self.router.process(update)
        self.client.send_message(
            chat_id=reply.chat_id,
            text=reply.text,
            reply_markup=dict(reply.reply_markup) if reply.reply_markup is not None else None,
        )
        return "processed"


def build_webhook_handler(
    *,
    processor: WebhookUpdateProcessor,
    config: BotConfig,
) -> type[BaseHTTPRequestHandler]:
    class TelegramWebhookHandler(BaseHTTPRequestHandler):
        server_version = "TelegramIntakeWebhook/0.1"

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._write_text(200, "ok\n")
                return
            self._write_text(404, "not found\n")

        def do_POST(self) -> None:
            if self.path != config.webhook_path:
                self._write_text(404, "not found\n")
                return

            if config.webhook_secret:
                received = self.headers.get("X-Telegram-Bot-Api-Secret-Token")
                if received != config.webhook_secret:
                    self._write_text(403, "forbidden\n")
                    return

            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or "0")
            except ValueError:
                self._write_text(411, "invalid content length\n")
                return

            if length < 1:
                self._write_text(400, "empty body\n")
                return
            if length > MAX_WEBHOOK_BODY_BYTES:
                self._write_text(413, "payload too large\n")
                return

            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                self._write_text(400, "invalid json\n")
                return
            if not isinstance(payload, dict):
                self._write_text(400, "invalid payload\n")
                return

            try:
                status = processor.process(payload)
            except Exception as exc:
                print(f"telegram_webhook_error: {exc}", file=sys.stderr, flush=True)
                self._write_text(500, "error\n")
                return

            self._write_json(200, {"status": status})

        def log_message(self, format: str, *args: object) -> None:
            print(f"telegram_webhook_http: {format % args}", file=sys.stderr, flush=True)

        def _write_text(self, status: int, text: str) -> None:
            encoded = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _write_json(self, status: int, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return TelegramWebhookHandler


def build_webhook_server(
    *,
    router: IntakeRouter,
    client: TelegramApiClient,
    config: BotConfig,
) -> ThreadingHTTPServer:
    processor = WebhookUpdateProcessor(router=router, client=client, config=config)
    handler = build_webhook_handler(processor=processor, config=config)
    return ThreadingHTTPServer(("0.0.0.0", config.webhook_port), handler)
