from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import BotConfig
from .router import BUTTON_END_SESSION, BUTTON_SEED, BUTTON_TASK, IntakeRouter
from .runtime import PollingRunner, TelegramApiClient
from .types import InboundUpdate
from .webhook import build_webhook_server


def _default_mock_updates() -> list[dict[str, Any]]:
    return [
        {
            "update_id": 1,
            "message": {
                "message_id": 11,
                "chat": {"id": 101},
                "from": {"id": 5001},
                "text": BUTTON_TASK,
            },
        },
        {
            "update_id": 2,
            "message": {
                "message_id": 12,
                "chat": {"id": 101},
                "from": {"id": 5001},
                "text": BUTTON_SEED,
            },
        },
        {
            "update_id": 3,
            "message": {
                "message_id": 13,
                "chat": {"id": 101},
                "from": {"id": 5001},
                "text": BUTTON_END_SESSION,
            },
        },
        {
            "update_id": 4,
            "message": {
                "message_id": 14,
                "chat": {"id": 101},
                "from": {"id": 5001},
                "text": BUTTON_SEED,
            },
        },
        {
            "update_id": 5,
            "message": {
                "message_id": 15,
                "chat": {"id": 101},
                "from": {"id": 5001},
                "text": "random text",
            },
        },
    ]


def _load_updates(path: str | None) -> list[dict[str, Any]]:
    if path is None:
        return _default_mock_updates()

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Mock updates file must contain a JSON list")
    return payload


def run_mock(updates_file: str | None) -> int:
    router = IntakeRouter()
    updates = _load_updates(updates_file)

    for raw in updates:
        try:
            update = InboundUpdate.from_telegram_update(raw)
        except Exception as exc:
            print(f"skip_update error={exc}")
            continue

        reply = router.process(update)
        incoming = update.text.replace("\n", " ").strip() or "<empty>"
        print(f"chat={update.chat_id} in={incoming}")
        print(f"chat={reply.chat_id} out={reply.text}")
        if reply.reply_markup is not None:
            print(f"chat={reply.chat_id} reply_markup={json.dumps(reply.reply_markup, ensure_ascii=False)}")

    snapshot = router.session_store.snapshot()
    if snapshot:
        print("active_sessions:")
        for chat_id, record in snapshot.items():
            print(f"  chat={chat_id} flow=/{record.flow.value}")
    else:
        print("active_sessions: none")

    return 0


def run_polling() -> int:
    config = BotConfig.from_env()
    if not config.token:
        print("TELEGRAM_BOT_TOKEN is not set. Use mock mode or configure local env.", file=sys.stderr)
        return 2

    router = IntakeRouter()
    client = TelegramApiClient(config.token)
    runner = PollingRunner(router=router, client=client, config=config)
    print("polling=started", flush=True)
    runner.run_forever()
    return 0


def run_diagnose() -> int:
    config = BotConfig.from_env()
    if not config.token:
        print("TELEGRAM_BOT_TOKEN is not set. Use mock mode or configure local env.", file=sys.stderr)
        return 2

    client = TelegramApiClient(config.token)
    try:
        bot = client.get_me()
        webhook = client.get_webhook_info()
    except Exception as exc:
        print(f"telegram_diagnose_error: {exc}", file=sys.stderr)
        return 1

    username = bot.get("username") or "<unknown>"
    webhook_url = webhook.get("url")
    pending_update_count = webhook.get("pending_update_count", 0)
    last_error_date = webhook.get("last_error_date")
    allowed_updates = webhook.get("allowed_updates")

    print("telegram_api=ok")
    print(f"bot_username=@{username}" if username != "<unknown>" else "bot_username=<unknown>")
    print(f"webhook_url_set={'yes' if webhook_url else 'no'}")
    print(f"pending_update_count={pending_update_count}")
    print(f"last_error_present={'yes' if last_error_date else 'no'}")
    if isinstance(allowed_updates, list):
        print(f"allowed_updates={','.join(str(item) for item in allowed_updates)}")
    return 0


def run_delete_webhook(*, drop_pending_updates: bool) -> int:
    config = BotConfig.from_env()
    if not config.token:
        print("TELEGRAM_BOT_TOKEN is not set. Use mock mode or configure local env.", file=sys.stderr)
        return 2

    client = TelegramApiClient(config.token)
    try:
        deleted = client.delete_webhook(drop_pending_updates=drop_pending_updates)
    except Exception as exc:
        print(f"telegram_delete_webhook_error: {exc}", file=sys.stderr)
        return 1

    print(f"delete_webhook={'ok' if deleted else 'not_changed'}")
    print(f"drop_pending_updates={'yes' if drop_pending_updates else 'no'}")
    return 0


def run_set_webhook(*, url: str, drop_pending_updates: bool) -> int:
    config = BotConfig.from_env()
    if not config.token:
        print("TELEGRAM_BOT_TOKEN is not set. Use mock mode or configure local env.", file=sys.stderr)
        return 2

    client = TelegramApiClient(config.token)
    try:
        configured = client.set_webhook(
            url=url,
            secret_token=config.webhook_secret,
            drop_pending_updates=drop_pending_updates,
        )
    except Exception as exc:
        print(f"telegram_set_webhook_error: {exc}", file=sys.stderr)
        return 1

    print(f"set_webhook={'ok' if configured else 'not_changed'}")
    print(f"webhook_path={config.webhook_path}")
    print(f"drop_pending_updates={'yes' if drop_pending_updates else 'no'}")
    print(f"secret_token={'configured' if config.webhook_secret else 'not_configured'}")
    return 0


def run_set_commands() -> int:
    config = BotConfig.from_env()
    if not config.token:
        print("TELEGRAM_BOT_TOKEN is not set. Use mock mode or configure local env.", file=sys.stderr)
        return 2

    client = TelegramApiClient(config.token)
    commands = [
        {"command": "start", "description": "Показать кнопки"},
        {"command": "task", "description": BUTTON_TASK},
        {"command": "seed", "description": BUTTON_SEED},
        {"command": "cancel", "description": BUTTON_END_SESSION},
    ]
    try:
        configured = client.set_my_commands(commands)
    except Exception as exc:
        print(f"telegram_set_commands_error: {exc}", file=sys.stderr)
        return 1

    print(f"set_commands={'ok' if configured else 'not_changed'}")
    print("commands=start,task,seed,cancel")
    return 0


def run_webhook() -> int:
    config = BotConfig.from_env()
    if not config.token:
        print("TELEGRAM_BOT_TOKEN is not set. Use mock mode or configure local env.", file=sys.stderr)
        return 2

    router = IntakeRouter()
    client = TelegramApiClient(config.token)
    server = build_webhook_server(router=router, client=client, config=config)
    print(f"webhook=started port={config.webhook_port} path={config.webhook_path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Intake Bot runtime shell")
    subparsers = parser.add_subparsers(dest="command", required=True)

    mock_parser = subparsers.add_parser("mock", help="Run local mock router check")
    mock_parser.add_argument("--updates-file", dest="updates_file", help="Path to JSON array with Telegram updates")

    subparsers.add_parser("diagnose", help="Check Telegram token and webhook state without printing secrets")

    delete_parser = subparsers.add_parser("delete-webhook", help="Clear Telegram webhook before local polling")
    delete_parser.add_argument(
        "--drop-pending-updates",
        action="store_true",
        help="Ask Telegram to drop pending updates while deleting webhook",
    )

    set_webhook_parser = subparsers.add_parser("set-webhook", help="Register Telegram webhook URL")
    set_webhook_parser.add_argument("--url", required=True, help="Public HTTPS webhook URL")
    set_webhook_parser.add_argument(
        "--drop-pending-updates",
        action="store_true",
        help="Ask Telegram to drop pending updates while setting webhook",
    )

    subparsers.add_parser("set-commands", help="Configure Telegram bot command menu")

    subparsers.add_parser("polling", help="Run long polling loop against Telegram API")
    subparsers.add_parser("webhook", help="Run HTTP webhook server for Cloud Run")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "mock":
        return run_mock(args.updates_file)
    if args.command == "diagnose":
        return run_diagnose()
    if args.command == "delete-webhook":
        return run_delete_webhook(drop_pending_updates=args.drop_pending_updates)
    if args.command == "set-webhook":
        return run_set_webhook(url=args.url, drop_pending_updates=args.drop_pending_updates)
    if args.command == "set-commands":
        return run_set_commands()
    if args.command == "polling":
        return run_polling()
    if args.command == "webhook":
        return run_webhook()

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
