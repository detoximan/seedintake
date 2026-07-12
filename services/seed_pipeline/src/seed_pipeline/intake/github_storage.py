from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from seed_pipeline.intake.dry_run import _build_fingerprint, _build_markdown_preview, _error_record
from seed_pipeline.intake.markdown_writer import (
    CreatedMarkdownSeed,
    ProcessedMessageRegistry,
    SeedDuplicateError,
    _build_full_markdown,
)
from seed_pipeline.schemas import SeedInput, SeedMarkdownArtifacts, SeedPlan


class GitHubStorageConfigError(RuntimeError):
    pass


class GitHubContentsError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubFile:
    path: str
    sha: str


class GitHubContentsClient:
    def __init__(
        self,
        *,
        token: str,
        repository: str,
        branch: str = "main",
        api_base_url: str = "https://api.github.com",
    ) -> None:
        self.token = token
        self.repository = repository
        self.branch = branch
        self.api_base_url = api_base_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "GitHubContentsClient":
        token = os.getenv("GITHUB_TOKEN", "").strip()
        repository = os.getenv("GITHUB_REPOSITORY", "pashamal/seedintake").strip()
        branch = os.getenv("GITHUB_BRANCH", "main").strip() or "main"
        missing = [
            name
            for name, value in (("GITHUB_TOKEN", token), ("GITHUB_REPOSITORY", repository))
            if not value
        ]
        if missing:
            raise GitHubStorageConfigError("Missing GitHub env vars: " + ", ".join(missing))
        return cls(token=token, repository=repository, branch=branch)

    def get_file(self, path: str) -> GitHubFile | None:
        response = self._request_json(
            "GET",
            self._contents_url(path) + f"?ref={quote(self.branch, safe='')}",
            expected_statuses={200, 404},
        )
        if response is None:
            return None
        if not isinstance(response, dict):
            raise GitHubContentsError(f"GitHub get contents returned invalid payload for {path}")
        sha = response.get("sha")
        if not sha:
            raise GitHubContentsError(f"GitHub get contents returned no sha for {path}")
        return GitHubFile(path=path, sha=str(sha))

    def create_file(self, *, path: str, content: str, message: str) -> GitHubFile:
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        response = self._request_json("PUT", self._contents_url(path), payload=payload, expected_statuses={200, 201})
        if not isinstance(response, dict):
            raise GitHubContentsError(f"GitHub create contents returned invalid payload for {path}")
        content_payload = response.get("content")
        sha = content_payload.get("sha") if isinstance(content_payload, dict) else None
        if not sha:
            raise GitHubContentsError(f"GitHub create contents returned no sha for {path}")
        return GitHubFile(path=path, sha=str(sha))

    def delete_file(self, *, path: str, sha: str, message: str) -> None:
        payload = {"message": message, "sha": sha, "branch": self.branch}
        self._request_json("DELETE", self._contents_url(path), payload=payload, expected_statuses={200})

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
            raise GitHubContentsError(f"GitHub API {method} failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise GitHubContentsError(f"GitHub API {method} failed: {exc.reason}") from exc

        if status not in expected_statuses:
            raise GitHubContentsError(f"GitHub API {method} returned unexpected HTTP {status}")
        if not body:
            return None
        return json.loads(body)


class GitHubSeedMarkdownWriter:
    def __init__(
        self,
        *,
        client: GitHubContentsClient | None = None,
        registry: ProcessedMessageRegistry | None = None,
        repo_root: Path | None = None,
        seed_root_path: str = "Inbox",
        github_base_url: str | None = None,
    ) -> None:
        self.client = client or GitHubContentsClient.from_env()
        self.repo_root = repo_root or Path.cwd().resolve()
        self.seed_root = self.repo_root / seed_root_path
        self.seed_root_path = seed_root_path.strip("/")
        self.registry = registry or ProcessedMessageRegistry(repo_root=self.repo_root)
        self.github_base_url = (github_base_url or os.getenv("GITHUB_SEED_BASE_URL", "")).strip()
        if not self.github_base_url:
            repository = os.getenv("GITHUB_REPOSITORY", self.client.repository).strip()
            branch = os.getenv("GITHUB_BRANCH", self.client.branch).strip() or "main"
            self.github_base_url = f"https://github.com/{repository}/blob/{branch}"

    @classmethod
    def from_env(cls, *, repo_root: Path | None = None) -> "GitHubSeedMarkdownWriter":
        return cls(client=GitHubContentsClient.from_env(), repo_root=repo_root)

    def next_seed_id(self, received_at: str) -> str:
        day = datetime.fromisoformat(received_at.replace("Z", "+00:00")).date().isoformat()
        for index in range(1, 1000):
            seed_id = f"{day}-{index:03d}"
            full_path, slim_path = self._paths(seed_id)
            if self.client.get_file(full_path) is None and self.client.get_file(slim_path) is None:
                return seed_id
        raise RuntimeError(f"No available Seed ID for day {day}")

    def write(
        self,
        seed_input: SeedInput,
        *,
        seed_id: str | None = None,
        record_processed: bool = True,
    ) -> CreatedMarkdownSeed:
        existing_seed_id = self.registry.find(seed_input.telegram_message_id)
        if existing_seed_id is not None:
            raise SeedDuplicateError(
                _error_record(
                    error_code="SEED_DUPLICATE_MESSAGE",
                    step="check_input_fingerprint",
                    message="Incoming Telegram message was already converted into a Seed.",
                    manual_action="none",
                    timestamp=seed_input.received_at,
                    severity="warning",
                )
            )

        seed_id = seed_id or self.next_seed_id(seed_input.received_at)
        full_path, slim_path = self._paths(seed_id)
        full_github_url = self._github_url(full_path)
        slim_github_url = self._github_url(slim_path)
        full_markdown = _build_full_markdown(
            seed_id=seed_id,
            seed_input=seed_input,
            slim_github_url=slim_github_url,
        )
        slim_markdown = _build_markdown_preview(
            seed_id=seed_id,
            full_github_url=full_github_url,
            comment=seed_input.comment,
            material=seed_input.material,
        )
        artifacts = SeedMarkdownArtifacts(
            seed_id=seed_id,
            full_path=full_path,
            slim_path=slim_path,
            full_github_url=full_github_url,
            slim_github_url=slim_github_url,
        )
        plan = SeedPlan(
            seed_id=seed_id,
            status="new",
            markdown_path=artifacts.slim_path,
            markdown_preview=slim_markdown,
            full_markdown_path=artifacts.full_path,
            slim_markdown_path=artifacts.slim_path,
            full_github_url=artifacts.full_github_url,
            slim_github_url=artifacts.slim_github_url,
            input_fingerprint=_build_fingerprint(seed_input),
            firestore_required=False,
            external_calls=["github_contents_api"],
        )

        written: list[GitHubFile] = []
        try:
            written.append(
                self.client.create_file(
                    path=full_path,
                    content=full_markdown,
                    message=f"Create Seed full {seed_id}",
                )
            )
            written.append(
                self.client.create_file(
                    path=slim_path,
                    content=slim_markdown,
                    message=f"Create Seed slim {seed_id}",
                )
            )
        except Exception:
            for item in reversed(written):
                self._safe_delete(item)
            raise

        if record_processed:
            self.registry.record(seed_input.telegram_message_id, seed_id)

        return CreatedMarkdownSeed(
            seed_plan=plan,
            full_file=self.repo_root / full_path,
            slim_file=self.repo_root / slim_path,
            artifacts=artifacts,
        )

    def rollback(self, created: CreatedMarkdownSeed) -> None:
        for path in (created.artifacts.slim_path, created.artifacts.full_path):
            remote_file = self.client.get_file(path)
            if remote_file is not None:
                self._safe_delete(remote_file)

    def _safe_delete(self, file: GitHubFile) -> None:
        self.client.delete_file(
            path=file.path,
            sha=file.sha,
            message=f"Rollback Seed artifact {file.path}",
        )

    def _paths(self, seed_id: str) -> tuple[str, str]:
        year = seed_id[:4]
        return (
            f"{self.seed_root_path}/{year}/full/{seed_id}-f.md",
            f"{self.seed_root_path}/{year}/slim/{seed_id}-s.md",
        )

    def _github_url(self, path: str) -> str:
        return f"{self.github_base_url.rstrip('/')}/{path}"
