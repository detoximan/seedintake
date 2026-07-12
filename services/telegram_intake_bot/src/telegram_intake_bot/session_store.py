from __future__ import annotations

from datetime import datetime, timezone

from .types import FlowName, SessionRecord


class InMemorySessionStore:
    """Chat-level active session store for flow conflict guard."""

    def __init__(self) -> None:
        self._store: dict[int, SessionRecord] = {}

    def get(self, chat_id: int) -> SessionRecord | None:
        return self._store.get(chat_id)

    def set(self, chat_id: int, flow: FlowName) -> SessionRecord:
        record = SessionRecord(flow=flow, started_at_iso=datetime.now(timezone.utc).isoformat())
        self._store[chat_id] = record
        return record

    def clear(self, chat_id: int) -> SessionRecord | None:
        return self._store.pop(chat_id, None)

    def snapshot(self) -> dict[int, SessionRecord]:
        return dict(self._store)
