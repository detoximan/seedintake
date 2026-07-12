from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BotConfig:
    token: str | None = field(default=None, repr=False)
    allowed_user_ids: frozenset[int] = frozenset()
    polling_timeout_seconds: int = 25
    webhook_port: int = 8080
    webhook_path: str = "/telegram/webhook"
    webhook_secret: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "BotConfig":
        raw_user_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
        parsed: set[int] = set()
        if raw_user_ids:
            for chunk in raw_user_ids.split(","):
                part = chunk.strip()
                if not part:
                    continue
                parsed.add(int(part))

        timeout_raw = os.getenv("TELEGRAM_POLL_TIMEOUT_SECONDS", "25")
        timeout_value = int(timeout_raw)
        if timeout_value < 1:
            timeout_value = 1

        port_raw = os.getenv("PORT", "8080")
        port_value = int(port_raw)
        if port_value < 1:
            port_value = 8080

        webhook_path = os.getenv("TELEGRAM_WEBHOOK_PATH", "/telegram/webhook").strip()
        if not webhook_path.startswith("/"):
            webhook_path = "/" + webhook_path

        return cls(
            token=os.getenv("TELEGRAM_BOT_TOKEN"),
            allowed_user_ids=frozenset(parsed),
            polling_timeout_seconds=timeout_value,
            webhook_port=port_value,
            webhook_path=webhook_path,
            webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET") or None,
        )

    def is_user_allowed(self, user_id: int | None) -> bool:
        if not self.allowed_user_ids:
            return True
        if user_id is None:
            return False
        return user_id in self.allowed_user_ids
