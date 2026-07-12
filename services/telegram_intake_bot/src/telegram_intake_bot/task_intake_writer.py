from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

LEGACY_TASK_PATTERN = re.compile(r"^task-intake-(?P<day>\d{8})-\d{6}-[0-9a-f]{8}\.md$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_task_intake_markdown(*, body: str) -> str:
    normalized_body = body.strip()
    if not normalized_body:
        raise ValueError("Task Intake body must not be empty")

    return (
        "status: new\n\n"
        "# Вход Павла\n\n"
        f"{normalized_body}\n"
    )


class TaskWriter(Protocol):
    def write(self, body: str) -> Path:
        pass


class TaskIntakeWriter:
    def __init__(self, inbox_dir: Path | None = None) -> None:
        env_inbox = os.getenv("TASK_INBOX_DIR", "").strip()
        if inbox_dir is not None:
            self.inbox_dir = inbox_dir
        elif env_inbox:
            self.inbox_dir = Path(env_inbox)
        else:
            self.inbox_dir = _repo_root() / "1inbox" / "tasks"

    def write(self, body: str) -> Path:
        created_at = datetime.now(timezone.utc)
        markdown = build_task_intake_markdown(body=body)

        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        target = self._build_unique_path(created_at)
        temp_path = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.inbox_dir,
                prefix=".tmp-task-intake-",
                suffix=".md",
                delete=False,
            ) as temp_file:
                temp_file.write(markdown)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)

            os.replace(temp_path, target)
            return target
        except Exception:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise

    def _build_unique_path(self, created_at: datetime) -> Path:
        day = created_at.date().isoformat()
        reserved_legacy = _count_legacy_task_files(self._existing_task_names(), day)
        for index in range(1, 1000):
            if index <= reserved_legacy:
                continue
            candidate = self.inbox_dir / f"{day}-{index:03d}t.md"
            if not candidate.exists():
                return candidate
        raise RuntimeError("Could not allocate unique Task Intake filename")

    def _existing_task_names(self) -> list[str]:
        if not self.inbox_dir.exists():
            return []
        return [path.name for path in self.inbox_dir.glob("*.md")]


class GitHubTaskIntakeWriter:
    def __init__(
        self,
        *,
        token: str,
        repository: str,
        branch: str = "main",
        repo_root: Path | None = None,
        tasks_root_path: str = "Inbox",
        api_base_url: str = "https://api.github.com",
    ) -> None:
        self.token = token
        self.repository = repository
        self.branch = branch
        self.repo_root = repo_root or _repo_root()
        self.tasks_root_path = tasks_root_path.strip("/")
        self.api_base_url = api_base_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "GitHubTaskIntakeWriter":
        token = os.getenv("GITHUB_TOKEN", "").strip()
        repository = os.getenv("GITHUB_REPOSITORY", "pashamal/seedintake").strip()
        branch = os.getenv("GITHUB_BRANCH", "main").strip() or "main"
        missing = [
            name
            for name, value in (("GITHUB_TOKEN", token), ("GITHUB_REPOSITORY", repository))
            if not value
        ]
        if missing:
            raise RuntimeError("Missing GitHub env vars: " + ", ".join(missing))
        return cls(token=token, repository=repository, branch=branch)

    def write(self, body: str) -> Path:
        created_at = datetime.now(timezone.utc)
        markdown = build_task_intake_markdown(body=body)
        relative_path = self._build_unique_path(created_at)
        self._create_file(
            path=relative_path,
            content=markdown,
            message=f"Create Task Intake {Path(relative_path).name}",
        )
        return self.repo_root / relative_path

    def _build_unique_path(self, created_at: datetime) -> str:
        day = created_at.date().isoformat()
        reserved_legacy = _count_legacy_task_files(self._existing_task_names(), day)
        for index in range(1, 1000):
            if index <= reserved_legacy:
                continue
            relative_path = f"{self.tasks_root_path}/{day}-{index:03d}t.md"
            if not self._file_exists(relative_path):
                return relative_path
        raise RuntimeError("Could not allocate unique Task Intake filename")

    def _existing_task_names(self) -> list[str]:
        response = self._request_json(
            "GET",
            self._contents_url(self.tasks_root_path) + f"?ref={quote(self.branch, safe='')}",
            expected_statuses={200, 404},
        )
        if response is None:
            return []
        if not isinstance(response, list):
            raise RuntimeError("GitHub API returned invalid task directory payload")
        names: list[str] = []
        for item in response:
            if isinstance(item, dict) and item.get("type") == "file":
                name = item.get("name")
                if isinstance(name, str):
                    names.append(name)
        return names

    def _file_exists(self, path: str) -> bool:
        response = self._request_json(
            "GET",
            self._contents_url(path) + f"?ref={quote(self.branch, safe='')}",
            expected_statuses={200, 404},
        )
        return response is not None

    def _create_file(self, *, path: str, content: str, message: str) -> None:
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        self._request_json("PUT", self._contents_url(path), payload=payload, expected_statuses={200, 201})

    def _contents_url(self, path: str) -> str:
        safe_path = quote(path.lstrip("/"), safe="/")
        return f"{self.api_base_url}/repos/{self.repository}/contents/{safe_path}"

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        expected_statuses: set[int],
    ) -> object | None:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url=url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                status = response.status
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404 and 404 in expected_statuses:
                return None
            raise RuntimeError(f"GitHub API {method} failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub API {method} failed: {exc.reason}") from exc

        if status not in expected_statuses:
            raise RuntimeError(f"GitHub API {method} returned unexpected HTTP {status}")
        if not body:
            return None
        return json.loads(body)


def build_task_intake_writer_from_env() -> TaskWriter:
    storage_provider = os.getenv("TASK_MARKDOWN_STORAGE", "local").strip().lower()
    if storage_provider in {"", "local"}:
        return TaskIntakeWriter()
    if storage_provider == "github":
        return GitHubTaskIntakeWriter.from_env()
    raise RuntimeError("Unknown TASK_MARKDOWN_STORAGE; supported values: local, github")


def _count_legacy_task_files(names: list[str], day: str) -> int:
    legacy_day = day.replace("-", "")
    count = 0
    for name in names:
        match = LEGACY_TASK_PATTERN.match(name)
        if match and match.group("day") == legacy_day:
            count += 1
    return count
