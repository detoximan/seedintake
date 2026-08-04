from __future__ import annotations

import tempfile
from pathlib import Path
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import (
    LinkProcessorResult, GroqAudioTranscriber, YtDlpAudioDownloader, RealYtDlpMetadataDownloader
)


class YouTubeProcessor:
    def __init__(self, use_cookies: bool = False, rate_limiter = None):
        self._transcriber = None
        self.use_cookies = use_cookies
        self.rate_limiter = rate_limiter
        self.downloader = YtDlpAudioDownloader.from_env()
        self.meta_downloader = RealYtDlpMetadataDownloader(use_cookies=use_cookies)

    def get_transcriber(self) -> GroqAudioTranscriber:
        if self._transcriber is None:
            self._transcriber = GroqAudioTranscriber.from_env()
        return self._transcriber

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        with tempfile.TemporaryDirectory(prefix="seed-yt-shorts-") as tmp_dir:
            audio_path = self.downloader.download_audio(item.url, Path(tmp_dir))
            transcript = self.get_transcriber().transcribe(audio_path).strip()

        views, likes = "", ""
        try:
            meta = self.meta_downloader.get_metadata(item.url)
            views = str(meta.get("view_count", ""))
            likes = str(meta.get("like_count", ""))
        except Exception:
            pass

        return LinkProcessorResult(
            material=transcript,
            comment=item.context.strip() or "YouTube Shorts processed by YouTubeProcessor.",
            views=views,
            likes=likes
        )
