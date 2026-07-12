from __future__ import annotations

import logging
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
                
                # При ошибке пустого контента просто меняем статус, не перемещая файл
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

            logger.warning(
                "BEFORE CEDO WRITE: url=%s material_len=%s material_preview=%r",
                item.url,
                len(material_to_write or ""),
                (material_to_write or "")[:1000],
            )
            
            creation_result = self.orchestrator.create_seed(
                SeedInput(
                    telegram_message_id=f"link:{item.relative_path}-instaloader-v9",
                    telegram_user_id="link-worker-local",
                    received_at=_received_at_from_item(item, timestamp),
                    material=material_to_write,
                    comment=processor_result.comment,
                    source_url=item.url,
                    views=processor_result.views,
                    likes=processor_result.likes,
                )
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
        """Check if error message indicates authentication required."""
        reason_lower = reason.lower()
        auth_keywords = ["cookie", "login", "auth", "empty media", "instagram sent an empty", "нет контента", "no content"]
        return any(kw in reason_lower for kw in auth_keywords)

    @staticmethod
    def _is_empty_result(material: str) -> bool:
        """Check if material contains only template headers and 'нет' values, no real content."""
        for line in material.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Skip section headers like '1 – Текст на фото:' etc.
            if re.match(r'^\d+\s*[–-]\s*(Текст на фото|Транскрибация видео|Текст под медиа)', stripped):
                continue
            # Skip lines that are just 'нет' or 'нет (error...)'
            if re.match(r'^нет\s*(\(.*?\))?\s*$', stripped):
                continue
            # Anything else is real content
            return False
        return True


def _received_at_from_item(item: LinkQueueItem, fallback: str) -> str:
    filename_date = item.path.name[:10]
    if len(filename_date) == 10 and filename_date[4] == "-" and filename_date[7] == "-":
        return f"{filename_date}T00:00:00+04:00"
    return fallback
