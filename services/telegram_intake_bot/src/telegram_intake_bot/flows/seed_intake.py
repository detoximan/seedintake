from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..errors import build_error_record
from ..link_queue_writer import LinkQueueWriter, build_link_queue_writer_from_env
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
BUTTON_SKIP_COMMENT = "Пропустить комментарий"
URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = ".,!?:;]}\"'"


def _action_keyboard() -> dict[str, object]:
    return {
        "keyboard": [[BUTTON_CONTINUE, BUTTON_FINISH, BUTTON_CANCEL]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def _remove_keyboard() -> dict[str, bool]:
    return {"remove_keyboard": True}


@dataclass
class SeedDraft:
    material_fragments: list[str] = field(default_factory=list)
    comment_fragments: list[str] = field(default_factory=list)
    telegram_message_id: str = ""
    received_at: str = ""
    phase: str = "material"

    @property
    def material(self) -> str:
        return "\n\n".join(fragment for fragment in self.material_fragments if fragment.strip())

    @property
    def comment(self) -> str:
        return "\n\n".join(fragment for fragment in self.comment_fragments if fragment.strip())


@dataclass(frozen=True)
class _SeedInputPayload:
    telegram_message_id: str
    telegram_user_id: str
    received_at: str
    material: str
    comment: str
    source_url: str | None = None


class SeedIntakeFlow:
    flow = FlowName.SEED
    implemented = True
    activates_session_on_start = True

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        transcription: TranscriptionAdapter | None = None,
        orchestrator_factory: Callable[[], object] | None = None,
        link_queue_writer: LinkQueueWriter | None = None,
    ) -> None:
        self._repo_root = repo_root or self._find_repo_root()
        self._transcription = transcription or build_transcription_adapter_from_env()
        self._orchestrator_factory = orchestrator_factory
        self._link_queue_writer = link_queue_writer or build_link_queue_writer_from_env(repo_root=self._repo_root)
        self._drafts: dict[int, SeedDraft] = {}
        self._ensure_pipeline_in_path()

    def on_start(self, update: InboundUpdate) -> FlowResponse:
        self._drafts[update.chat_id] = SeedDraft()
        return FlowResponse(
            text="Отправьте исходник (голос, текст или ссылка)",
            reply_markup=_action_keyboard(),
        )

    def on_repeat_start(self, update: InboundUpdate) -> FlowResponse:
        return FlowResponse(
            text=(
                "Режим /seed уже активен. Пришлите фрагмент, "
                f"или выберите '{BUTTON_FINISH}', либо '{BUTTON_CANCEL}'."
            ),
            reply_markup=_action_keyboard(),
        )

    def on_cancel(self, update: InboundUpdate) -> None:
        self._drafts.pop(update.chat_id, None)
        return None

    def on_message(self, update: InboundUpdate) -> FlowResponse:
        draft = self._drafts.setdefault(update.chat_id, SeedDraft())
        normalized_text = update.text.strip()

        if normalized_text == BUTTON_CONTINUE:
            return self._handle_continue(draft)

        if normalized_text == BUTTON_FINISH:
            return self._handle_finish(update.chat_id, draft)

        if normalized_text == BUTTON_CANCEL:
            self._drafts.pop(update.chat_id, None)
            return FlowResponse(
                text="Сессия /seed отменена.",
                end_session=True,
                reply_markup=_remove_keyboard(),
            )

        if draft.phase == "comment" and normalized_text == BUTTON_SKIP_COMMENT:
            return self._finalize(update.chat_id, draft)

        try:
            content = self._extract_content(update)
        except TranscriptionError as exc:
            return FlowResponse(
                text=(
                    f"Не удалось обработать голосовое сообщение: {exc}. "
                    "Проверьте настройки или пришлите текст."
                ),
                error_record=build_error_record(
                    error_code="SEED_VOICE_TRANSCRIPTION_FAILED",
                    step="seed_flow_transcription",
                    message=str(exc),
                    manual_action="Настроить mock/google provider и повторить отправку.",
                ),
            )

        if draft.phase == "material":
            if not content:
                return FlowResponse(
                    text="Пожалуйста, пришлите текстовый материал, ссылку или голос.",
                    reply_markup=_action_keyboard(),
                )

            draft.material_fragments.append(content)
            if not draft.telegram_message_id:
                draft.telegram_message_id = str(
                    update.message_id or f"tg-msg-{update.chat_id}-{int(datetime.now().timestamp())}"
                )
                draft.received_at = datetime.now(timezone.utc).isoformat()

            if extract_first_url(draft.material) is not None:
                return self._queue_link(update.chat_id, draft)

            return FlowResponse(
                text=(
                    f"Фрагмент материала сохранён ({len(draft.material_fragments)}). "
                    f"Выберите '{BUTTON_CONTINUE}', '{BUTTON_FINISH}' или '{BUTTON_CANCEL}'."
                ),
                reply_markup=_action_keyboard(),
            )

        if not content:
            return FlowResponse(
                text=(
                    "Пустой комментарий. Пришлите текст или голос, "
                    f"либо выберите '{BUTTON_FINISH}' без комментария."
                ),
                reply_markup=_action_keyboard(),
            )

        draft.comment_fragments.append(content)
        return FlowResponse(
            text=(
                f"Фрагмент комментария сохранён ({len(draft.comment_fragments)}). "
                f"Выберите '{BUTTON_CONTINUE}', '{BUTTON_FINISH}' или '{BUTTON_CANCEL}'."
            ),
            reply_markup=_action_keyboard(),
        )

    def _handle_continue(self, draft: SeedDraft) -> FlowResponse:
        if draft.phase == "material":
            if not draft.material_fragments:
                return FlowResponse(
                    text="Пока нет фрагментов материала. Пришлите первый фрагмент (текст, ссылку или голос).",
                    reply_markup=_action_keyboard(),
                )
            return FlowResponse(
                text="Ок, пришлите следующий фрагмент материала.",
                reply_markup=_action_keyboard(),
            )

        if not draft.comment_fragments:
            return FlowResponse(
                text=(
                    "Пока нет комментария. Пришлите комментарий или выберите "
                    f"'{BUTTON_FINISH}' без комментария."
                ),
                reply_markup=_action_keyboard(),
            )
        return FlowResponse(
            text="Ок, пришлите следующий фрагмент комментария.",
            reply_markup=_action_keyboard(),
        )

    def _handle_finish(self, chat_id: int, draft: SeedDraft) -> FlowResponse:
        if draft.phase == "material":
            if not draft.material.strip():
                return FlowResponse(
                    text="Нечего отправлять: сначала добавьте хотя бы один фрагмент материала.",
                    reply_markup=_action_keyboard(),
                )
            draft.phase = "comment"
            return FlowResponse(
                text=(
                    "Материал принят. Добавьте комментарий (текст или голос), "
                    f"выберите '{BUTTON_CONTINUE}' для продолжения или '{BUTTON_FINISH}' без комментария."
                ),
                reply_markup=_action_keyboard(),
            )

        return self._finalize(chat_id, draft)

    def _extract_content(self, update: InboundUpdate) -> str:
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

    def _finalize(self, chat_id: int, draft: SeedDraft) -> FlowResponse:
        if not draft.material.strip():
            return FlowResponse(
                text="Нечего отправлять: сначала добавьте хотя бы один фрагмент материала.",
                reply_markup=_action_keyboard(),
            )

        if extract_first_url(draft.material) is not None:
            return self._queue_link(chat_id, draft)

        try:
            if self._orchestrator_factory is None:
                from seed_pipeline.intake import build_seed_orchestrator_from_env
                from seed_pipeline.schemas import SeedInput
            else:
                SeedInput = _SeedInputPayload
        except ImportError:
            return FlowResponse(
                text="Ошибка: компонент Seed Pipeline не найден в системе.",
                error_record=build_error_record(
                    error_code="SEED_PIPELINE_NOT_FOUND",
                    step="seed_flow_finalize",
                    message="Could not import seed_pipeline. Ensure it is in PYTHONPATH.",
                    severity="error",
                ),
            )

        seed_input = SeedInput(
            telegram_message_id=draft.telegram_message_id,
            telegram_user_id=str(chat_id),
            received_at=draft.received_at,
            material=draft.material,
            comment=draft.comment,
        )

        try:
            if self._orchestrator_factory is not None:
                orchestrator = self._orchestrator_factory()
            else:
                orchestrator = build_seed_orchestrator_from_env(repo_root=self._repo_root)
            result = orchestrator.create_seed(seed_input)
        except Exception as exc:
            return FlowResponse(
                text=f"Ошибка при сохранении Seed: {exc}",
                error_record=build_error_record(
                    error_code="SEED_PIPELINE_EXECUTION_FAILED",
                    step="seed_flow_orchestrator",
                    message=str(exc),
                    severity="error",
                ),
            )

        if result.status != "ok":
            return FlowResponse(
                text=f"Не удалось создать Seed: {result.error_record.message if result.error_record else 'Unknown error'}",
                error_record=result.error_record.to_dict() if result.error_record else None,
            )

        self._drafts.pop(chat_id, None)
        
        seed_id = result.seed_plan.seed_id if result.seed_plan else "N/A"
        full_path = result.seed_plan.full_markdown_path if result.seed_plan else "N/A"
        slim_path = result.seed_plan.slim_markdown_path if result.seed_plan else "N/A"
        
        return FlowResponse(
            text=(
                f"Seed успешно создан: {seed_id}\n"
                f"Full: {full_path}\n"
                f"Slim: {slim_path}\n"
                "Сессия завершена."
            ),
            end_session=True,
            reply_markup=_remove_keyboard(),
        )

    def _queue_link(self, chat_id: int, draft: SeedDraft) -> FlowResponse:
        url = extract_first_url(draft.material)
        if url is None:
            return FlowResponse(
                text="Нечего отправлять: ссылка не найдена.",
                reply_markup=_action_keyboard(),
            )
        platform = classify_link_platform(url)
        context = _build_link_context(material=draft.material, url=url, comment=draft.comment)

        try:
            item = self._link_queue_writer.write(url=url, platform=platform, context=context)
        except Exception as exc:
            return FlowResponse(
                text=(
                    "Не удалось поставить ссылку в очередь Seed Link. "
                    "Проверьте доступ к GitHub/Inbox и повторите отправку."
                ),
                error_record=build_error_record(
                    error_code="SEED_LINK_QUEUE_WRITE_FAILED",
                    step="seed_flow_link_queue_write",
                    message=str(exc),
                    manual_action="Проверить доступ к link queue и повторить отправку ссылки.",
                ),
            )

        self._drafts.pop(chat_id, None)
        return FlowResponse(
            text=(
                "Ссылка поставлена в очередь локальной обработки.\n"
                f"Platform: {item.platform}\n"
                f"Queue: {item.relative_path}\n"
                "Seed/Sheet сейчас не создавались."
            ),
            end_session=True,
            reply_markup=_remove_keyboard(),
        )

    def _ensure_pipeline_in_path(self) -> None:
        pipeline_src = str(self._repo_root / "services" / "seed_pipeline" / "src")
        if pipeline_src not in sys.path:
            sys.path.insert(0, pipeline_src)

    def _find_repo_root(self) -> Path:
        current = Path(__file__).resolve()
        for candidate in (current, *current.parents):
            if (candidate / ".git").exists():
                return candidate
        return Path.cwd().resolve()


def extract_first_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if match is None:
        return None
    return match.group(0).rstrip(TRAILING_URL_PUNCTUATION)


def _build_link_context(*, material: str, url: str, comment: str) -> str:
    material_context = _normalize_context(material.replace(url, "", 1))
    parts = [part for part in (material_context, _normalize_context(comment)) if part]
    return "\n\n".join(parts)


def _normalize_context(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def classify_link_platform(url: str) -> str:
    normalized = url.strip().lower()
    without_scheme = normalized.split("://", 1)[-1]
    host_and_path = without_scheme.split("?", 1)[0].split("#", 1)[0]
    host = host_and_path.split("/", 1)[0].removeprefix("www.")
    path = "/" + host_and_path.split("/", 1)[1] if "/" in host_and_path else "/"

    if host in {"youtube.com", "m.youtube.com"} and path.startswith("/shorts/"):
        return "youtube_shorts"
    if host in {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"} or host.endswith(".tiktok.com"):
        return "tiktok"
    if host in {"instagram.com", "m.instagram.com"} and path.startswith("/reel/"):
        return "instagram_reels"
    
    # Text platforms that go to TextPostProcessor
    if host in {"t.me", "telegram.me"}:
        return "telegram_post"
    if host in {"threads.net", "threads.com"} or host.endswith(".threads.net") or host.endswith(".threads.com"):
        return "threads_post"
    if host in {"instagram.com", "m.instagram.com"}:
        return "instagram_post"
    if host in {"facebook.com", "m.facebook.com", "fb.com", "fb.watch"} or host.endswith(".facebook.com"):
        return "facebook_post"
    
    # Anything else with an URL is treated as text_post (articles, blogs)
    return "unknown"
