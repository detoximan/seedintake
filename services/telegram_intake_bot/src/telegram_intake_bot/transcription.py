from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class VoiceFragment:
    file_id: str
    duration_seconds: int | None
    mime_type: str | None
    chat_id: int
    message_id: int | None


class TranscriptionError(RuntimeError):
    pass


class TranscriptionAdapter(Protocol):
    def transcribe(self, fragment: VoiceFragment) -> str:
        ...


class VoiceDownloader(Protocol):
    def download(self, file_id: str) -> bytes:
        ...


class MockTranscriptionAdapter:
    """Deterministic local adapter for tests and mock smoke-checks."""

    def transcribe(self, fragment: VoiceFragment) -> str:
        duration = fragment.duration_seconds if fragment.duration_seconds is not None else "?"
        return f"[voice:{fragment.file_id}; duration={duration}s]"


class UnavailableTranscriptionAdapter:
    def __init__(self, *, provider: str, reason: str) -> None:
        self._provider = provider
        self._reason = reason

    def transcribe(self, fragment: VoiceFragment) -> str:
        raise TranscriptionError(f"Provider '{self._provider}' недоступен: {self._reason}")


class TelegramVoiceDownloader:
    def __init__(self, *, token: str) -> None:
        self._api_base_url = f"https://api.telegram.org/bot{token}"
        self._file_base_url = f"https://api.telegram.org/file/bot{token}"

    def download(self, file_id: str) -> bytes:
        file_path = self._get_file_path(file_id)
        safe_path = quote(file_path, safe="/")
        request = Request(url=f"{self._file_base_url}/{safe_path}", method="GET")
        try:
            with urlopen(request, timeout=60) as response:
                payload = response.read()
        except HTTPError as exc:
            raise TranscriptionError(f"Telegram voice download failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise TranscriptionError(f"Telegram voice download failed: {exc.reason}") from exc

        if not payload:
            raise TranscriptionError("Telegram voice download returned empty audio")
        return payload

    def _get_file_path(self, file_id: str) -> str:
        body = json.dumps({"file_id": file_id}).encode("utf-8")
        request = Request(
            url=f"{self._api_base_url}/getFile",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                decoded = response.read().decode("utf-8")
        except HTTPError as exc:
            raise TranscriptionError(f"Telegram getFile failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise TranscriptionError(f"Telegram getFile failed: {exc.reason}") from exc

        try:
            data = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise TranscriptionError("Telegram getFile returned invalid JSON") from exc
        if not data.get("ok"):
            description = data.get("description", "unknown error")
            raise TranscriptionError(f"Telegram getFile failed: {description}")

        result = data.get("result")
        file_path = result.get("file_path") if isinstance(result, dict) else None
        if not file_path:
            raise TranscriptionError("Telegram getFile did not return file_path")
        return str(file_path)


class GoogleSpeechTranscriptionAdapter:
    def __init__(
        self,
        *,
        downloader: VoiceDownloader,
        language_code: str = "ru-RU",
        sample_rate_hertz: int | None = None,
        model: str | None = None,
        credentials_source: str = "default",
        speech_client: object | None = None,
        speech_module: object | None = None,
    ) -> None:
        self._downloader = downloader
        self._language_code = language_code
        self._sample_rate_hertz = sample_rate_hertz
        self._model = model
        self._credentials_source = credentials_source
        self._speech_client = speech_client
        self._speech_module = speech_module

    def transcribe(self, fragment: VoiceFragment) -> str:
        audio_bytes = self._downloader.download(fragment.file_id)
        client, speech = self._load_google_speech()

        try:
            encoding = speech.RecognitionConfig.AudioEncoding.OGG_OPUS
            config_kwargs = {
                "encoding": encoding,
                "language_code": self._language_code,
            }
            if self._sample_rate_hertz is not None:
                config_kwargs["sample_rate_hertz"] = self._sample_rate_hertz
            if self._model:
                config_kwargs["model"] = self._model

            config = speech.RecognitionConfig(**config_kwargs)
            audio = speech.RecognitionAudio(content=audio_bytes)
            response = client.recognize(config=config, audio=audio)
        except Exception as exc:
            raise TranscriptionError(f"Google Speech transcription failed: {exc}") from exc

        transcripts: list[str] = []
        for result in getattr(response, "results", []):
            alternatives = getattr(result, "alternatives", [])
            if alternatives:
                transcript = getattr(alternatives[0], "transcript", "").strip()
                if transcript:
                    transcripts.append(transcript)

        if not transcripts:
            raise TranscriptionError("Google Speech returned empty transcription")
        return "\n".join(transcripts)

    def _load_google_speech(self) -> tuple[object, object]:
        if self._speech_client is not None and self._speech_module is not None:
            return self._speech_client, self._speech_module

        try:
            from google.cloud import speech
        except Exception as exc:
            raise TranscriptionError("Python package google-cloud-speech is not installed or unavailable") from exc

        credentials = None
        if self._credentials_source == "runtime":
            try:
                from google.auth import compute_engine
            except Exception as exc:
                raise TranscriptionError("Google runtime credentials are unavailable") from exc
            credentials = compute_engine.Credentials()
        elif self._credentials_source not in {"", "default"}:
            raise TranscriptionError(
                "Unknown TRANSCRIPTION_CREDENTIALS_SOURCE; supported values: default and runtime"
            )

        self._speech_module = speech
        self._speech_client = speech.SpeechClient(credentials=credentials)
        return self._speech_client, self._speech_module


def build_transcription_adapter_from_env() -> TranscriptionAdapter:
    provider = os.getenv("TRANSCRIPTION_PROVIDER", "mock").strip().lower()
    if provider in {"", "mock"}:
        return MockTranscriptionAdapter()

    if provider == "google":
        missing = [
            name
            for name in ("GOOGLE_APPLICATION_CREDENTIALS", "TELEGRAM_BOT_TOKEN")
            if not os.getenv(name, "").strip()
        ]
        if missing:
            return UnavailableTranscriptionAdapter(
                provider="google",
                reason=f"env {', '.join(missing)} не настроен",
            )

        try:
            sample_rate_hertz = _optional_int_env("TRANSCRIPTION_SAMPLE_RATE_HERTZ")
        except TranscriptionError as exc:
            return UnavailableTranscriptionAdapter(provider="google", reason=str(exc))
        return GoogleSpeechTranscriptionAdapter(
            downloader=TelegramVoiceDownloader(token=os.environ["TELEGRAM_BOT_TOKEN"]),
            language_code=os.getenv("TRANSCRIPTION_LANGUAGE_CODE", "ru-RU").strip() or "ru-RU",
            sample_rate_hertz=sample_rate_hertz,
            model=os.getenv("TRANSCRIPTION_MODEL", "").strip() or None,
            credentials_source=os.getenv("TRANSCRIPTION_CREDENTIALS_SOURCE", "default").strip().lower()
            or "default",
        )

    return UnavailableTranscriptionAdapter(
        provider=provider,
        reason="неизвестный провайдер; поддерживаются mock и google",
    )


def _optional_int_env(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise TranscriptionError(f"env {name} должен быть целым числом") from exc
    if value < 1:
        raise TranscriptionError(f"env {name} должен быть положительным числом")
    return value
