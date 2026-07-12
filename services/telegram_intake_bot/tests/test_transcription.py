import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from telegram_intake_bot.transcription import (
    GoogleSpeechTranscriptionAdapter,
    MockTranscriptionAdapter,
    TranscriptionError,
    UnavailableTranscriptionAdapter,
    VoiceFragment,
    build_transcription_adapter_from_env,
)


class StaticDownloader:
    def __init__(self) -> None:
        self.file_ids: list[str] = []

    def download(self, file_id: str) -> bytes:
        self.file_ids.append(file_id)
        return b"voice-bytes"


class FakeAudioEncoding:
    OGG_OPUS = "OGG_OPUS"


class FakeRecognitionConfig:
    AudioEncoding = FakeAudioEncoding

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class FakeRecognitionAudio:
    def __init__(self, *, content: bytes) -> None:
        self.content = content


class FakeSpeechModule:
    RecognitionConfig = FakeRecognitionConfig
    RecognitionAudio = FakeRecognitionAudio


class FakeSpeechClient:
    def __init__(self) -> None:
        self.calls: list[tuple[FakeRecognitionConfig, FakeRecognitionAudio]] = []

    def recognize(self, *, config: FakeRecognitionConfig, audio: FakeRecognitionAudio) -> SimpleNamespace:
        self.calls.append((config, audio))
        alternative = SimpleNamespace(transcript=" тестовая транскрибация ")
        result = SimpleNamespace(alternatives=[alternative])
        return SimpleNamespace(results=[result])


class TranscriptionProviderTests(unittest.TestCase):
    def test_mock_is_default_provider(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            adapter = build_transcription_adapter_from_env()

        self.assertIsInstance(adapter, MockTranscriptionAdapter)

    def test_google_provider_requires_credentials_and_telegram_token(self) -> None:
        with patch.dict(os.environ, {"TRANSCRIPTION_PROVIDER": "google"}, clear=True):
            adapter = build_transcription_adapter_from_env()

        self.assertIsInstance(adapter, UnavailableTranscriptionAdapter)
        with self.assertRaises(TranscriptionError) as ctx:
            adapter.transcribe(self._fragment())

        message = str(ctx.exception)
        self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", message)
        self.assertIn("TELEGRAM_BOT_TOKEN", message)

    def test_unknown_provider_is_unavailable(self) -> None:
        with patch.dict(os.environ, {"TRANSCRIPTION_PROVIDER": "groq"}, clear=True):
            adapter = build_transcription_adapter_from_env()

        self.assertIsInstance(adapter, UnavailableTranscriptionAdapter)
        with self.assertRaises(TranscriptionError) as ctx:
            adapter.transcribe(self._fragment())

        self.assertIn("поддерживаются mock и google", str(ctx.exception))

    def test_google_provider_can_use_runtime_credentials_source(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TRANSCRIPTION_PROVIDER": "google",
                "TRANSCRIPTION_CREDENTIALS_SOURCE": "runtime",
                "GOOGLE_APPLICATION_CREDENTIALS": "/secrets/google/service-account.json",
                "TELEGRAM_BOT_TOKEN": "token",
            },
            clear=True,
        ):
            adapter = build_transcription_adapter_from_env()

        self.assertIsInstance(adapter, GoogleSpeechTranscriptionAdapter)
        self.assertEqual(adapter._credentials_source, "runtime")

    def test_google_adapter_transcribes_downloaded_telegram_voice(self) -> None:
        downloader = StaticDownloader()
        client = FakeSpeechClient()
        adapter = GoogleSpeechTranscriptionAdapter(
            downloader=downloader,
            language_code="ru-RU",
            sample_rate_hertz=48000,
            model="latest_long",
            speech_client=client,
            speech_module=FakeSpeechModule,
        )

        transcript = adapter.transcribe(self._fragment(file_id="voice-google-1"))

        self.assertEqual(transcript, "тестовая транскрибация")
        self.assertEqual(downloader.file_ids, ["voice-google-1"])
        self.assertEqual(len(client.calls), 1)
        config, audio = client.calls[0]
        self.assertEqual(audio.content, b"voice-bytes")
        self.assertEqual(config.kwargs["encoding"], "OGG_OPUS")
        self.assertEqual(config.kwargs["language_code"], "ru-RU")
        self.assertEqual(config.kwargs["sample_rate_hertz"], 48000)
        self.assertEqual(config.kwargs["model"], "latest_long")

    @staticmethod
    def _fragment(file_id: str = "voice-file-1") -> VoiceFragment:
        return VoiceFragment(
            file_id=file_id,
            duration_seconds=2,
            mime_type="audio/ogg",
            chat_id=1,
            message_id=15,
        )


if __name__ == "__main__":
    unittest.main()
