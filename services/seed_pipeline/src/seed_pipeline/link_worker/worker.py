from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from seed_pipeline.integrations import MockGoogleWorkspace
from seed_pipeline.intake import MockSeedIntakeOrchestrator
from seed_pipeline.schemas import SeedInput

from .processors import FakeLinkProcessor, LinkProcessor
from .queue import LinkQueueItem, LinkQueueStore, LinkQueueUpdate

logger = logging.getLogger(__name__)

CYRILLIC_PATTERN = re.compile(r"[а-яА-ЯёЁ]")
TRANS_MARKER = "===================="
SERVICE_MARKERS = [
    "1 – текст на фото:",
    "1 – Текст на фото:",
    "2 – транскрибация аудио/видео:",
    "2 – Транскрибация аудио/видео:",
    "3 – текст под медиа:",
    "3 – Текст под медиа:",
]
EMPTY_WORDS = {"нет", "no", "текста нет"}


def _get_real_content(main_text: str) -> str:
    result = main_text
    for marker in SERVICE_MARKERS:
        result = result.replace(marker, " ")
    lines = []
    for line in result.split("\n"):
        stripped = line.strip()
        if stripped.lower() in EMPTY_WORDS:
            continue
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def _is_foreign_content(material: str) -> bool:
    if TRANS_MARKER in material:
        return False
    content = _get_real_content(material)
    if not content:
        return False
    return not bool(CYRILLIC_PATTERN.search(content))


def _translate_material_if_needed(material: str) -> str:
    if not _is_foreign_content(material):
        return material

    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_api_key:
        dotenv_path = Path(__file__).resolve().parents[2] / ".env"
        if dotenv_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(dotenv_path)
                groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
            except ImportError:
                pass

    if not groq_api_key:
        logger.warning("GROQ_API_KEY not found in env, skipping inline translation")
        return material

    try:
        from groq import Groq
        client = Groq(api_key=groq_api_key)
        prompt = f"""Переведи следующий текст на русский язык. Требования:
- Сохрани структуру строк вида «1 – Текст на фото: ...», «2 – Транскрибация аудио/видео: ...», «3 – Текст под медиа: ...». Сами заголовки уже на русском — не меняй их, переводи только содержимое после двоеточия.
- Сохрани переносы строк и пустые строки.
- Имена файлов в квадратных скобках (например [photo.jpg]), ссылки, хэштеги, упоминания @аккаунтов и эмодзи — не переводи, сохрани как есть.
- Если содержимое секции — «нет» или «no», оставь русское «нет».
- Переведи ВЕСЬ контент: текст на фото, транскрибацию, текст под медиа.

Текст для перевода:
---
{material}
---

Верни ТОЛЬКО перевод, без пояснений."""

        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=8192,
        )
        translated = chat.choices[0].message.content.strip()
        if translated.startswith("---"):
            translated = translated[3:].lstrip()
        if translated.endswith("---"):
            translated = translated[:-3].rstrip()
            
        logger.info("Successfully translated material inline")
        return material.rstrip() + "\n\n" + TRANS_MARKER + "\n\n" + translated
    except Exception as exc:
        logger.warning("Inline translation failed: %s", exc)
        return material


@dataclass(frozen=True)
class LinkProcessResult:
    path: str
    status: str
    seed_id: str | None = None
    seed_path: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "status": self.status,
            "seed_id": self.seed_id,
            "seed_path": self.seed_path,
            "reason": self.reason,
        }


class LinkWorker:
    def __init__(
        self,
        *,
        queue_store: LinkQueueStore | None = None,
        processor: LinkProcessor | None = None,
        orchestrator: MockSeedIntakeOrchestrator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.queue_store = queue_store or LinkQueueStore()
        self.processor = processor or FakeLinkProcessor()
        self.orchestrator = orchestrator or MockSeedIntakeOrchestrator(google_workspace=MockGoogleWorkspace())
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def list_new(self, *, platform: str | None = None) -> list[LinkQueueItem]:
        return self.queue_store.list_items(status="new", platform=platform)

    def process(self, *, limit: int | None = None, platform: str | None = None) -> list[LinkProcessResult]:
        items = self.list_new(platform=platform)
        if limit is not None:
            items = items[:limit]
        return [self.process_file(item.path) for item in items]

    def process_file(self, path: Path) -> LinkProcessResult:
        item = self.queue_store.read(path)
        if item.status not in ("new", "pending_cookies"):
            return LinkProcessResult(path=item.relative_path, status="skipped", reason=f"status is {item.status}")

        timestamp = self.clock().isoformat()
        try:
            processor_result = self.processor.process(item)
            
            logger.warning(
                "AFTER PROCESSOR: platform=%s url=%s material_len=%s material_preview=%r comment=%r views=%r likes=%r",
                item.platform,
                item.url,
                len(processor_result.material or ""),
                (processor_result.material or "")[:1000],
                processor_result.comment,
                processor_result.views,
                processor_result.likes,
            )
            
            material_to_write = (processor_result.material or "").strip()
            if not material_to_write:
                material_to_write = "текста нет"
                
            # Check if result is empty (no content)
            if self._is_empty_result(material_to_write) and not processor_result.views and not processor_result.likes:
                reason = "Нет контента (блокировка/удалено)"
                
                if item.status == "new":
                    updated = self.queue_store.update(
                        item,
                        LinkQueueUpdate(status="pending_cookies", failure_reason=reason, failed_at=timestamp),
                    )
                    return LinkProcessResult(path=updated.relative_path, status="pending_cookies", reason="Нет контента (ожидает cookies)")

                updated = self.queue_store.update(
                    item,
                    LinkQueueUpdate(status="failed", failure_reason=reason, failed_at=timestamp),
                )
                return LinkProcessResult(path=updated.relative_path, status="failed", reason=reason)

            # Автоматический прямой перевод иноязычного контента перед записью
            material_to_write = _translate_material_if_needed(material_to_write)

            logger.warning(
                "BEFORE CEDO WRITE: url=%s material_len=%s material_preview=%r",
                item.url,
                len(material_to_write or ""),
                (material_to_write or "")[:1000],
            )
            
            link_stem = item.path.stem
            desired_seed_id = link_stem.rsplit("-link", 1)[0] if link_stem.endswith("-link") else None
            
            creation_result = self.orchestrator.create_seed(
                SeedInput(
                    telegram_message_id=f"link:{item.relative_path}",
                    telegram_user_id="link-worker-local",
                    received_at=_received_at_from_item(item, timestamp),
                    material=material_to_write,
                    comment=processor_result.comment,
                    source_url=item.url,
                    views=processor_result.views,
                    likes=processor_result.likes,
                ),
                seed_id=desired_seed_id,
            )
            logger.debug("Processed material (first 200 chars): %s", processor_result.material[:200])
            logger.debug("Views: %s, Likes: %s", processor_result.views, processor_result.likes)
            if creation_result.status == "error":
                message = (
                    creation_result.error_record.message
                    if creation_result.error_record is not None
                    else "Seed creation failed"
                )
                updated = self.queue_store.update(
                    item,
                    LinkQueueUpdate(status="failed", failure_reason=message, failed_at=timestamp),
                )
                return LinkProcessResult(path=updated.relative_path, status="failed", reason=message)

            seed_id = None
            seed_path = None
            if creation_result.seed_plan is not None:
                seed_id = creation_result.seed_plan.seed_id
                seed_path = creation_result.seed_plan.slim_markdown_path
            elif creation_result.error_record is not None:
                seed_id = creation_result.error_record.artifact_id
            updated = self.queue_store.update(
                item,
                LinkQueueUpdate(
                    status="processed",
                    processed_seed_id=seed_id,
                    processed_seed_path=seed_path,
                    processed_at=timestamp,
                ),
            )
            return LinkProcessResult(
                path=updated.relative_path,
                status="processed",
                seed_id=seed_id,
                seed_path=seed_path,
            )
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            logger.warning("Processing failed for %s: %s", item.relative_path, reason)
            if self._is_auth_error(reason):
                updated = self.queue_store.update(
                    item,
                    LinkQueueUpdate(status="pending_cookies", failure_reason=reason, failed_at=timestamp),
                )
                return LinkProcessResult(path=updated.relative_path, status="pending_cookies", reason="Requires cookies")
            else:
                updated = self.queue_store.update(
                    item,
                    LinkQueueUpdate(status="failed", failure_reason=reason, failed_at=timestamp),
                )
                return LinkProcessResult(path=updated.relative_path, status="failed", reason=reason)

    @staticmethod
    def _is_auth_error(reason: str) -> bool:
        reason_lower = reason.lower()
        auth_keywords = ["cookie", "login", "auth", "empty media", "instagram sent an empty", "нет контента", "no content"]
        return any(kw in reason_lower for kw in auth_keywords)

    @staticmethod
    def _is_empty_result(material: str) -> bool:
        for line in material.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r'^\d+\s*[–-]\s*(Текст на фото|Транскрибация видео|Текст под медиа)', stripped):
                continue
            if re.match(r'^нет\s*(\(.*?\))?\s*$', stripped):
                continue
            return False
        return True


def _received_at_from_item(item: LinkQueueItem, fallback: str) -> str:
    filename_date = item.path.name[:10]
    if len(filename_date) == 10 and filename_date[4] == "-" and filename_date[7] == "-":
        return f"{filename_date}T00:00:00+04:00"
    return fallback
