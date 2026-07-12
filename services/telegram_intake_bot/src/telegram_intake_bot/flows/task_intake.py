from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..errors import build_error_record
from ..task_intake_writer import TaskWriter, build_task_intake_writer_from_env
from ..transcription import (
    TranscriptionAdapter,
    TranscriptionError,
    VoiceFragment,
    build_transcription_adapter_from_env,
)
from ..types import FlowName, FlowResponse, InboundUpdate

BUTTON_CONTINUE = "Продолжить"
BUTTON_FINISH = "Отправить"
BUTTON_CANCEL = "Отменить"


def _action_keyboard() -> dict[str, object]:
    return {
        "keyboard": [[BUTTON_CONTINUE, BUTTON_FINISH, BUTTON_CANCEL]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def _remove_keyboard() -> dict[str, bool]:
    return {"remove_keyboard": True}


@dataclass
class TaskDraft:
    fragments: list[str] = field(default_factory=list)
    awaiting_choice: bool = False


class TaskIntakeFlow:
    flow = FlowName.TASK
    implemented = True
    activates_session_on_start = True

    def __init__(
        self,
        *,
        writer: TaskWriter | None = None,
        transcription: TranscriptionAdapter | None = None,
    ) -> None:
        self._writer = writer or build_task_intake_writer_from_env()
        self._transcription = transcription or build_transcription_adapter_from_env()
        self._drafts: dict[int, TaskDraft] = {}

    def on_start(self, update: InboundUpdate) -> FlowResponse:
        self._drafts[update.chat_id] = TaskDraft()
        return FlowResponse(
            text="Запишите задачу",
            reply_markup=_action_keyboard(),
        )

    def on_repeat_start(self, update: InboundUpdate) -> FlowResponse:
        return FlowResponse(
            text=(
                "Режим /task уже активен. Пришлите фрагмент, "
                f"или выберите '{BUTTON_FINISH}', либо '{BUTTON_CANCEL}'."
            ),
            reply_markup=_action_keyboard(),
        )

    def on_cancel(self, update: InboundUpdate) -> None:
        self._drafts.pop(update.chat_id, None)
        return None

    def on_message(self, update: InboundUpdate) -> FlowResponse:
        draft = self._drafts.setdefault(update.chat_id, TaskDraft())
        normalized_text = update.text.strip()

        if normalized_text == BUTTON_CONTINUE:
            if not draft.fragments:
                return FlowResponse(
                    text="Пока нет фрагментов. Пришлите первый фрагмент (текст или голос).",
                    reply_markup=_action_keyboard(),
                )
            draft.awaiting_choice = False
            return FlowResponse(
                text="Ок, пришлите следующий фрагмент.",
                reply_markup=_action_keyboard(),
            )

        if normalized_text == BUTTON_FINISH:
            return self._finalize(update.chat_id, draft)

        if normalized_text == BUTTON_CANCEL:
            self._drafts.pop(update.chat_id, None)
            return FlowResponse(
                text="Сессия /task отменена.",
                end_session=True,
                reply_markup=_remove_keyboard(),
            )

        try:
            fragment = self._extract_fragment(update)
        except TranscriptionError as exc:
            return FlowResponse(
                text=(
                    f"Не удалось обработать голосовой фрагмент: {exc}. "
                    "Проверьте transcription provider или пришлите текст."
                ),
                error_record=build_error_record(
                    error_code="TASK_VOICE_TRANSCRIPTION_FAILED",
                    step="task_flow_transcription",
                    message=str(exc),
                    manual_action=(
                        "Настроить mock/google provider и повторить голосовой фрагмент, "
                        "или отправить текст."
                    ),
                ),
            )

        if not fragment:
            return FlowResponse(
                text="Пустой фрагмент. Пришлите текст или голосовое сообщение.",
                reply_markup=_action_keyboard(),
            )

        draft.fragments.append(fragment)
        draft.awaiting_choice = True
        return FlowResponse(
            text=(
                f"Фрагмент сохранён ({len(draft.fragments)}). "
                f"Выберите '{BUTTON_CONTINUE}', '{BUTTON_FINISH}' или '{BUTTON_CANCEL}'."
            ),
            reply_markup=_action_keyboard(),
        )

    def _extract_fragment(self, update: InboundUpdate) -> str:
        if update.voice is not None:
            return self._transcription.transcribe(
                VoiceFragment(
                    file_id=update.voice.file_id,
                    duration_seconds=update.voice.duration_seconds,
                    mime_type=update.voice.mime_type,
                    chat_id=update.chat_id,
                    message_id=update.message_id,
                )
            ).strip()
        return update.text.strip()

    def _finalize(self, chat_id: int, draft: TaskDraft) -> FlowResponse:
        if not draft.fragments:
            return FlowResponse(
                text="Нечего отправлять: сначала добавьте хотя бы один фрагмент.",
                reply_markup=_action_keyboard(),
            )

        body = "\n\n".join(fragment for fragment in draft.fragments if fragment.strip())
        if not body.strip():
            return FlowResponse(
                text="Нечего отправлять: фрагменты пустые. Добавьте текст или голос.",
                reply_markup=_action_keyboard(),
            )

        try:
            file_path = self._writer.write(body)
        except Exception as exc:
            return FlowResponse(
                text=(
                    "Не удалось создать markdown-файл Task Intake. "
                    "Проверьте права записи и повторите отправку."
                ),
                error_record=build_error_record(
                    error_code="TASK_MARKDOWN_WRITE_FAILED",
                    step="task_flow_finalize_write",
                    message=str(exc),
                    manual_action=(
                        f"Проверить доступ к /Inbox/ и повторить '{BUTTON_FINISH}'."
                    ),
                ),
            )

        self._drafts.pop(chat_id, None)
        return FlowResponse(
            text=(
                "Готово. Task Intake сохранён: "
                f"{self._display_path(file_path)}\n"
                "Можно запускать новую сессию через /task."
            ),
            end_session=True,
            reply_markup=_remove_keyboard(),
        )

    @staticmethod
    def _display_path(path: Path) -> str:
        parts = path.parts
        if "1inbox" in parts:
            idx = parts.index("1inbox")
            return "/".join(parts[idx:])
        return str(path)
