from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import (
    LinkProcessorResult, ImageOcrExtractor, GroqAudioTranscriber,
    GalleryDlMediaDownloader, RealYtDlpMetadataDownloader, YtDlpAudioDownloader
)

logger = logging.getLogger(__name__)


class TikTokProcessor:
    def __init__(self, use_cookies: bool = False, rate_limiter = None):
        self.ocr = ImageOcrExtractor()
        self._transcriber = None
        self.use_cookies = use_cookies
        self.rate_limiter = rate_limiter
        self.meta_downloader = RealYtDlpMetadataDownloader(use_cookies=use_cookies)

    def get_transcriber(self) -> GroqAudioTranscriber:
        if self._transcriber is None:
            self._transcriber = GroqAudioTranscriber.from_env()
        return self._transcriber

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        with tempfile.TemporaryDirectory(prefix="seed-tiktok-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            gdl = GalleryDlMediaDownloader(use_cookies=self.use_cookies)
            files = gdl.download_all(item.url, tmp_path)

            images = sorted([f for f in files if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}])
            videos = sorted([f for f in files if f.suffix.lower() in {'.mp4', '.mov', '.webm'}])

            ocr_results = [f"[{img.name}]: {self.ocr.extract(img)}" for img in images]
            trans_results = []

            if videos:
                dl = YtDlpAudioDownloader.from_env()
                try:
                    audio_path = dl.download_audio(item.url, tmp_path)
                    trans_results.append(self.get_transcriber().transcribe(audio_path))
                except Exception as e:
                    logger.warning(f"TikTok transcription failed: {e}")

            views, likes, desc = "", "", ""
            try:
                meta = self.meta_downloader.get_metadata(item.url)
                views = str(meta.get("view_count", ""))
                likes = str(meta.get("like_count", ""))
                desc = meta.get("description", "").strip()
            except Exception:
                pass

            ocr_str = "\n".join(ocr_results) if ocr_results else "нет"
            trans_str = "\n".join(trans_results) if trans_results else "нет"
            parts = [
                f"1 – Текст на фото:\n{ocr_str}",
                f"2 – Транскрибация аудио/видео:\n{trans_str}",
                f"3 – Текст под медиа:\n{desc if desc else 'нет'}"
            ]
            return LinkProcessorResult(
                material="\n\n".join(parts),
                comment=item.context.strip() or "TikTok content processed by TikTokProcessor.",
                views=views,
                likes=likes
            )
