from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ErrorRecord:
    error_code: str
    agent: str
    step: str
    artifact_id: str | None
    message: str
    manual_action: str
    timestamp: str
    severity: str


def build_error_record(
    *,
    error_code: str,
    step: str,
    message: str,
    severity: str = "error",
    artifact_id: str | None = None,
    manual_action: str = "Повторить запрос позже или отправить /cancel.",
    agent: str = "Telegram Intake Bot",
) -> dict[str, str | None]:
    record = ErrorRecord(
        error_code=error_code,
        agent=agent,
        step=step,
        artifact_id=artifact_id,
        message=message,
        manual_action=manual_action,
        timestamp=datetime.now(timezone.utc).isoformat(),
        severity=severity,
    )
    return asdict(record)
