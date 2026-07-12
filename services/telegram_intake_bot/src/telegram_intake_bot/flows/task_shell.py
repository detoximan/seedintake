from __future__ import annotations

from ..types import FlowName, InboundUpdate


class TaskFlowShell:
    """Minimal `/task` shell to reserve the shared runtime command path."""

    flow = FlowName.TASK
    implemented = True
    activates_session_on_start = True

    def on_start(self, update: InboundUpdate) -> str:
        return "Запишите задачу"

    def on_repeat_start(self, update: InboundUpdate) -> str:
        return "Режим /task уже активен в этом чате. Отправьте /cancel, чтобы завершить текущую сессию."

    def on_message(self, update: InboundUpdate) -> str:
        return (
            "Сессия /task активна. Полный сценарий накопления текста и кнопок будет подключен в TB-A009-003. "
            "Сейчас можно завершить сессию командой /cancel."
        )

    def on_cancel(self, update: InboundUpdate) -> None:
        return None
