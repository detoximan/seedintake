import json
import urllib.request
import urllib.error
from urllib.request import Request
import re
from typing import Protocol

class JinaReader(Protocol):
    def read_text(self, url: str) -> str:
        pass

class JinaApiReader:
    endpoint = "https://r.jina.ai/"

    def read_text(self, url: str) -> str:
        # For telegram, Jina works much better with embed view instead of the wrapper page
        if "t.me/" in url and "?embed=1" not in url:
            jina_url = f"{self.endpoint}{url}?embed=1"
        else:
            jina_url = f"{self.endpoint}{url}"
            
        http_request = Request(
            jina_url,
            headers={"User-Agent": "curl/7.68.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=30) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Jina Reader failed with {exc.code}: {self._compact_error(detail) or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Jina Reader unavailable: {exc.reason}") from exc
            
        text = payload.strip()
        if not text:
            raise RuntimeError("Jina Reader returned empty text")
            
        # Clean up common Jina artifacts like inline images
        text = re.sub(r'!\[Image \d+\]\(blob:http://localhost/[^\)]+\)', '', text)
        text = re.sub(r'\[!\[Image.*?\]\(.*?\)\]\(.*?\)', '', text)
        text = re.sub(r'!\[Image.*?\]\(.*?\)', '', text)
        
        # Clean up Threads/Social media UI noise
        lines = text.splitlines()
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue
            
            if stripped in {"Translate", "·Author", "Related threads", "Telegram", "Channel Appearance, Posts in Stories and More"}:
                continue
            if stripped.startswith("Log in to see more replies") or stripped.startswith("Log in or sign up for Threads"):
                continue
            if stripped.startswith("[Log in with username instead]"):
                continue
            if stripped == "Continue with Instagram" or stripped == "Log in with username instead":
                continue
            if re.fullmatch(r'\d+', stripped):
                continue
                
            cleaned.append(line)
            
        text = "\n".join(cleaned)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        
        return text
        
    def _compact_error(self, text: str) -> str:
        return " ".join(text.strip().split())[:500]
