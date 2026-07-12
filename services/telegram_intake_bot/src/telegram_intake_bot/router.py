from __future__ import annotations

from .errors import build_error_record
from .flows import SeedIntakeFlow, TaskIntakeFlow
from .flows.base import FlowHandler
from .flows.seed_intake import extract_first_url
from .session_store import InMemorySessionStore
from .types import BotReply, FlowName, FlowResponse, InboundUpdate

BUTTON_TASK = "Дать задачу"
BUTTON_SEED = "Записать seed"
BUTTON_END_SESSION = "Завершить сессию"

MAIN_MENU_KEYBOARD: dict[str, object] = {
    "keyboard": [[BUTTON_TASK, BUTTON_SEED], [BUTTON_END_SESSION]],
    "resize_keyboard": True,
    "one_time_keyboard": False,
    "is_persistent": True,
}


class IntakeRouter:
    """Shared command router for `/start`, `/task`, `/seed`, `/cancel` and unknown input."""

    def __init__(
        self,
        *,
        task_flow: FlowHandler | None = None,
        seed_flow: FlowHandler | None = None,
        session_store: InMemorySessionStore | None = None,
    ) -> None:
        self.session_store = session_store or InMemorySessionStore()
        self.flows: dict[FlowName, FlowHandler] = {
            FlowName.TASK: task_flow or TaskIntakeFlow(),
            FlowName.SEED: seed_flow or SeedIntakeFlow(),
        }

    def register_flow(self, flow: FlowName, handler: FlowHandler) -> None:
        """Extension point for future flow implementations (e.g. TASK-A002 /seed)."""
        self.flows[flow] = handler

    def process(self, update: InboundUpdate) -> BotReply:
        try:
            command = self._parse_command(update.text)

            if command == "/start":
                return self._handle_start(update)
            if command == "/cancel":
                return self._handle_cancel(update)
            if command == "/task":
                return self._handle_start_flow(update, FlowName.TASK)
            if command == "/seed":
                return self._handle_start_flow(update, FlowName.SEED)

            return self._handle_non_command(update)
        except Exception as exc:  # pragma: no cover - defensive boundary
            error_record = build_error_record(
                error_code="TELEGRAM_ROUTER_FAILURE",
                step="router_process",
                message=str(exc),
                severity="error",
            )
            return BotReply(
                chat_id=update.chat_id,
                text="Техническая ошибка роутера. Попробуйте снова или отправьте /cancel.",
                error_record=error_record,
            )

    def _handle_start(self, update: InboundUpdate) -> BotReply:
        return BotReply(
            chat_id=update.chat_id,
            text="Выберите входящий контур.",
            reply_markup=MAIN_MENU_KEYBOARD,
        )

    def _handle_cancel(self, update: InboundUpdate) -> BotReply:
        previous = self.session_store.clear(update.chat_id)
        if previous is None:
            return BotReply(
                chat_id=update.chat_id,
                text=f"Активной сессии нет. Выберите '{BUTTON_TASK}' или '{BUTTON_SEED}'.",
                reply_markup=MAIN_MENU_KEYBOARD,
            )

        handler = self.flows.get(previous.flow)
        if handler is not None:
            on_cancel = getattr(handler, "on_cancel", None)
            if callable(on_cancel):
                try:
                    on_cancel(update)
                except Exception:
                    pass

        return BotReply(
            chat_id=update.chat_id,
            text=f"Сессия /{previous.flow.value} завершена. Можно запускать другой flow.",
            reply_markup=MAIN_MENU_KEYBOARD,
        )

    def _handle_start_flow(self, update: InboundUpdate, requested_flow: FlowName) -> BotReply:
        active = self.session_store.get(update.chat_id)
        if active is not None and active.flow != requested_flow:
            return BotReply(
                chat_id=update.chat_id,
                text=(
                    f"Сейчас активен flow /{active.flow.value}. "
                    f"Сначала завершите его через '{BUTTON_END_SESSION}', затем запускайте /{requested_flow.value}."
                ),
            )

        handler = self.flows[requested_flow]
        if active is not None and active.flow == requested_flow:
            return self._build_reply(update.chat_id, self._normalize_flow_response(handler.on_repeat_start(update)))

        response = self._normalize_flow_response(handler.on_start(update))
        if handler.implemented and handler.activates_session_on_start and not response.end_session:
            self.session_store.set(update.chat_id, requested_flow)

        return self._build_reply(update.chat_id, response)

    def _handle_non_command(self, update: InboundUpdate) -> BotReply:
        active = self.session_store.get(update.chat_id)
        if active is None:
            if extract_first_url(update.text) is not None:
                return self._handle_standalone_seed_url(update)
            return BotReply(
                chat_id=update.chat_id,
                text=(
                    f"Не распознал ввод. Используйте '{BUTTON_TASK}' для Task Intake. "
                    f"Используйте '{BUTTON_SEED}' для Seed Intake."
                ),
                reply_markup=MAIN_MENU_KEYBOARD,
            )

        handler = self.flows[active.flow]
        response = self._normalize_flow_response(handler.on_message(update))
        if response.end_session:
            self.session_store.clear(update.chat_id)
        return self._build_reply(update.chat_id, response)

    def _handle_standalone_seed_url(self, update: InboundUpdate) -> BotReply:
        handler = self.flows[FlowName.SEED]
        start_response = self._normalize_flow_response(handler.on_start(update))
        if handler.implemented and handler.activates_session_on_start and not start_response.end_session:
            self.session_store.set(update.chat_id, FlowName.SEED)

        response = self._normalize_flow_response(handler.on_message(update))
        if response.end_session:
            self.session_store.clear(update.chat_id)
        return self._build_reply(update.chat_id, response)

    @staticmethod
    def _parse_command(text: str) -> str | None:
        stripped = text.strip()
        button_commands = {
            BUTTON_TASK.lower(): "/task",
            BUTTON_SEED.lower(): "/seed",
            BUTTON_END_SESSION.lower(): "/cancel",
        }
        mapped = button_commands.get(stripped.lower())
        if mapped is not None:
            return mapped

        if not stripped.startswith("/"):
            return None

        first_token = stripped.split(maxsplit=1)[0]
        first_token = first_token.split("@", maxsplit=1)[0]
        normalized = first_token.lower()

        if normalized in {"/start", "/task", "/seed", "/cancel"}:
            return normalized

        return None

    @staticmethod
    def _normalize_flow_response(raw: str | FlowResponse) -> FlowResponse:
        if isinstance(raw, FlowResponse):
            return raw
        return FlowResponse(text=raw)

    @staticmethod
    def _build_reply(chat_id: int, response: FlowResponse) -> BotReply:
        reply_markup = MAIN_MENU_KEYBOARD if response.end_session else response.reply_markup
        return BotReply(
            chat_id=chat_id,
            text=response.text,
            reply_markup=reply_markup,
            error_record=response.error_record,
        )
