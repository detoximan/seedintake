from __future__ import annotations

import os
import logging
import tempfile
from pathlib import Path
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import (
    LinkProcessorResult, ImageOcrExtractor, GroqAudioTranscriber,
    RealYtDlpMetadataDownloader, YtDlpAudioDownloader, InstaloaderMediaDownloader
)

logger = logging.getLogger(__name__)


class InstagramProcessor:
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

    def process_reels(self, item: LinkQueueItem) -> LinkProcessorResult:
        with tempfile.TemporaryDirectory(prefix="seed-insta-reel-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            downloader = YtDlpAudioDownloader.from_env(use_cookies=self.use_cookies, rate_limiter=self.rate_limiter)
            audio_path = downloader.download_audio(item.url, tmp_path)
            transcript = self.get_transcriber().transcribe(audio_path).strip()

        views, likes, desc = "", "", ""
        try:
            meta = self.meta_downloader.get_metadata(item.url)
            views = str(meta.get("view_count", ""))
            likes = str(meta.get("like_count", ""))
            desc = meta.get("description", "").strip()
        except Exception as e:
            logger.warning(f"Could not fetch metadata for Insta reel: {e}")

        parts = [
            "1 – Текст на фото: нет",
            f"2 – Транскрибация аудио/видео:\n{transcript}",
            f"3 – Текст под медиа:\n{desc if desc else 'нет'}"
        ]
        return LinkProcessorResult(
            material="\n\n".join(parts),
            comment=item.context.strip() or "Instagram Reels processed by InstagramProcessor.",
            views=views,
            likes=likes
        )

    def process_carousel(self, item: LinkQueueItem) -> LinkProcessorResult:
        with tempfile.TemporaryDirectory(prefix="seed-insta-carousel-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            files = []
            try:
                instaloader = InstaloaderMediaDownloader(use_cookies=self.use_cookies)
                files = instaloader.download_all(item.url, tmp_path)
            except Exception as e:
                logger.warning(f"Instaloader failed: {e}")

            images = sorted([f for f in files if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}])
            ocr_results = []
            for img in images:
                txt = self.ocr.extract(img)
                if txt and not txt.startswith("(пусто)") and not txt.startswith("(ошибка"):
                    ocr_results.append(f"[{img.name}]: {txt}")

            views, likes, desc = "", "", ""
            try:
                meta = self.meta_downloader.get_metadata(item.url)
                views = str(meta.get("view_count", ""))
                likes = str(meta.get("like_count", ""))
                desc = meta.get("description", "").strip()
            except Exception:
                pass

            ocr_text = "\n".join(ocr_results) if ocr_results else "нет"
            parts = [
                f"1 – Текст на фото:\n{ocr_text}",
                "2 – Транскрибация аудио/видео: нет",
                f"3 – Текст под медиа:\n{desc if desc else 'нет'}"
            ]
            return LinkProcessorResult(
                material="\n\n".join(parts),
                comment=item.context.strip() or "Instagram Carousel/Post processed by InstagramProcessor.",
                views=views,
                likes=likes
            )
