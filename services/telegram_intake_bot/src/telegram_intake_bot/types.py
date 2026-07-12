from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class FlowName(str, Enum):
    TASK = "task"
    SEED = "seed"


@dataclass(frozen=True)
class VoiceAttachment:
    file_id: str
    duration_seconds: int | None = None
    mime_type: str | None = None
    file_unique_id: str | None = None


@dataclass(frozen=True)
class InboundUpdate:
    """Minimal Telegram update normalized for router logic."""

    chat_id: int
    text: str
    voice: VoiceAttachment | None = None
    user_id: int | None = None
    message_id: int | None = None
    update_id: int | None = None

    @classmethod
    def from_telegram_update(cls, update: Mapping[str, Any]) -> "InboundUpdate":
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, Mapping):
            raise ValueError("Unsupported Telegram update payload: missing message")

        chat = message.get("chat")
        if not isinstance(chat, Mapping) or "id" not in chat:
            raise ValueError("Telegram payload is missing chat.id")

        text = message.get("text")
        if text is None:
            text = message.get("caption")
        if text is None:
            text = ""

        voice = None
        raw_voice = message.get("voice")
        if isinstance(raw_voice, Mapping):
            file_id = raw_voice.get("file_id")
            if file_id is not None:
                duration = raw_voice.get("duration")
                voice = VoiceAttachment(
                    file_id=str(file_id),
                    duration_seconds=int(duration) if isinstance(duration, int) else None,
                    mime_type=str(raw_voice["mime_type"]) if "mime_type" in raw_voice else None,
                    file_unique_id=str(raw_voice["file_unique_id"]) if "file_unique_id" in raw_voice else None,
                )

        from_user = message.get("from") if isinstance(message.get("from"), Mapping) else None
        user_id = from_user.get("id") if from_user else None

        return cls(
            chat_id=int(chat["id"]),
            text=str(text),
            voice=voice,
            user_id=int(user_id) if user_id is not None else None,
            message_id=int(message["message_id"]) if "message_id" in message else None,
            update_id=int(update["update_id"]) if "update_id" in update else None,
        )


@dataclass(frozen=True)
class SessionRecord:
    flow: FlowName
    started_at_iso: str


@dataclass(frozen=True)
class BotReply:
    chat_id: int
    text: str
    reply_markup: Mapping[str, Any] | None = None
    error_record: dict[str, Any] | None = None


@dataclass(frozen=True)
class FlowResponse:
    text: str
    end_session: bool = False
    reply_markup: Mapping[str, Any] | None = None
    error_record: dict[str, Any] | None = None
