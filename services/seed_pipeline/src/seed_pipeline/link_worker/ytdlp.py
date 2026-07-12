import subprocess
import shutil
import json
import tempfile
from pathlib import Path
from typing import Protocol

class YtDlpMetadataDownloader(Protocol):
    def get_metadata(self, url: str) -> dict[str, str]:
        pass

class RealYtDlpMetadataDownloader:
    def __init__(self, *, executable: str = "yt-dlp", use_cookies: bool = False, browser: str = "chrome") -> None:
        self.executable = executable
        self.use_cookies = use_cookies
        self.browser = browser

    def get_metadata(self, url: str) -> dict[str, str]:
        if shutil.which(self.executable) is None:
            raise RuntimeError("yt-dlp is not installed or is not on PATH")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            command = [
                self.executable,
                "--write-info-json",
                "--skip-download",
                "--paths", str(tmp_path),
                "--output", "%(id)s.%(ext)s",
            ]
            if self.use_cookies:
                command.extend(["--cookies-from-browser", self.browser])
            
            command.append(url)
            
            try:
                completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=30)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("yt-dlp timed out while fetching metadata") from exc

            # Find JSON file in temp directory
            json_files = list(tmp_path.glob("*.info.json"))
            if not json_files:
                # Try to get error detail
                detail = self._last_nonempty_line(completed.stderr) or self._last_nonempty_line(completed.stdout)
                raise RuntimeError(f"yt-dlp failed: {detail or 'metadata unavailable'}")
            
            try:
                parsed = json.loads(json_files[0].read_text())
            except json.JSONDecodeError as exc:
                raise RuntimeError("yt-dlp returned invalid JSON") from exc
            
            return {
                "title": str(parsed.get("title", "")).strip(),
                "description": str(parsed.get("description", "")).strip(),
                "id": str(parsed.get("id", "")).strip(),
                "view_count": str(parsed.get("view_count", "")).strip(),
                "like_count": str(parsed.get("like_count", "")).strip()
            }

    def _last_nonempty_line(self, text: str) -> str:
        for line in reversed(text.splitlines()):
            normalized = line.strip()
            if normalized:
                return normalized
        return ""
