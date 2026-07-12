from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class LinkQueueItem:
    path: Path
    relative_path: str
    url: str
    platform: str


class LinkQueueWriter(Protocol):
    def write(self, *, url: str, platform: str, context: str = "") -> LinkQueueItem:
        pass


def build_link_queue_markdown(*, url: str, platform: str, context: str = "") -> str:
    normalized_url = url.strip()
    normalized_platform = platform.strip()
    normalized_context = context.strip()
    if not normalized_url:
        raise ValueError("Link queue URL must not be empty")
    if not normalized_platform:
        raise ValueError("Link queue platform must not be empty")

    blocks = [
        "status: new",
        f"url: {normalized_url}",
        f"platform: {normalized_platform}",
    ]
    if normalized_context:
        context_lines = ["context: |-", *[f"  {line}" for line in normalized_context.splitlines()]]
        blocks.append("\n".join(context_lines))
    return "\n\n".join(blocks) + "\n"


class LocalLinkQueueWriter:
    def __init__(self, *, repo_root: Path | None = None, seed_root: Path | None = None) -> None:
        self.repo_root = repo_root or _repo_root()
        self.seed_root = seed_root or self.repo_root / "1inbox" / "seeds"
        if not self.seed_root.is_absolute():
            self.seed_root = self.repo_root / self.seed_root

    def write(self, *, url: str, platform: str, context: str = "") -> LinkQueueItem:
        created_at = datetime.now(timezone.utc)
        target_dir = self.seed_root / str(created_at.year) / "links"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = self._build_unique_path(target_dir, created_at)
        markdown = build_link_queue_markdown(url=url, platform=platform, context=context)

        temp_path = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target_dir,
                prefix=".tmp-link-queue-",
                suffix=".md",
                delete=False,
            ) as temp_file:
                temp_file.write(markdown)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)

            os.replace(temp_path, target)
            return LinkQueueItem(
                path=target,
                relative_path=self._display_path(target),
                url=url.strip(),
                platform=platform.strip(),
            )
        except Exception:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise

    @staticmethod
    def _build_unique_path(target_dir: Path, created_at: datetime) -> Path:
        day = created_at.date().isoformat()
        for index in range(1, 1000):
            candidate = target_dir / f"{day}-{index:03d}-link.md"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Could not allocate unique Link Queue filename for {day}")

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            parts = path.parts
            if "1inbox" in parts:
                idx = parts.index("1inbox")
                return "/".join(parts[idx:])
            return str(path)


class GitHubLinkQueueWriter:
    def __init__(
        self,
        *,
        token: str,
        repository: str,
        branch: str = "main",
        repo_root: Path | None = None,
        seed_root_path: str = "Inbox",
        api_base_url: str = "https://api.github.com",
    ) -> None:
        self.token = token
        self.repository = repository
        self.branch = branch
        self.repo_root = repo_root or _repo_root()
        self.seed_root_path = seed_root_path.strip("/")
        self.api_base_url = api_base_url.rstrip("/")

    @classmethod
    def from_env(cls, *, repo_root: Path | None = None) -> "GitHubLinkQueueWriter":
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
        return cls(token=token, repository=repository, branch=branch, repo_root=repo_root)

    def write(self, *, url: str, platform: str, context: str = "") -> LinkQueueItem:
        created_at = datetime.now(timezone.utc)
        relative_path = self._build_unique_path(created_at)
        markdown = build_link_queue_markdown(url=url, platform=platform, context=context)
        self._create_file(
            path=relative_path,
            content=markdown,
            message=f"Create Seed link queue {Path(relative_path).name}",
        )
        return LinkQueueItem(
            path=self.repo_root / relative_path,
            relative_path=relative_path,
            url=url.strip(),
            platform=platform.strip(),
        )

    def _build_unique_path(self, created_at: datetime) -> str:
        day = created_at.date().isoformat()
        links_root = f"{self.seed_root_path}/{created_at.year}/links"
        existing_names = set(self._existing_link_names(links_root))
        for index in range(1, 1000):
            name = f"{day}-{index:03d}-link.md"
            if name not in existing_names:
                return f"{links_root}/{name}"
        raise RuntimeError(f"Could not allocate unique Link Queue filename for {day}")

    def _existing_link_names(self, links_root: str) -> list[str]:
        response = self._request_json(
            "GET",
            self._contents_url(links_root) + f"?ref={quote(self.branch, safe='')}",
            expected_statuses={200, 404},
        )
        if response is None:
            return []
        if not isinstance(response, list):
            raise RuntimeError("GitHub API returned invalid link queue directory payload")
        names: list[str] = []
        for item in response:
            if isinstance(item, dict) and item.get("type") == "file":
                name = item.get("name")
                if isinstance(name, str):
                    names.append(name)
        return names

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


def build_link_queue_writer_from_env(*, repo_root: Path | None = None) -> LinkQueueWriter:
    storage_provider = os.getenv("LINK_QUEUE_STORAGE", "").strip().lower()
    if not storage_provider:
        storage_provider = os.getenv("SEED_MARKDOWN_STORAGE", "local").strip().lower()
    if storage_provider in {"", "local"}:
        return LocalLinkQueueWriter(repo_root=repo_root)
    if storage_provider == "github":
        return GitHubLinkQueueWriter.from_env(repo_root=repo_root)
    raise RuntimeError("Unknown LINK_QUEUE_STORAGE/SEED_MARKDOWN_STORAGE; supported values: local, github")
