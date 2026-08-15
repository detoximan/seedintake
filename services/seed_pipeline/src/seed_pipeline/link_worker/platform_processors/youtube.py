from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import (
    LinkProcessorResult, GroqAudioTranscriber, YtDlpAudioDownloader, RealYtDlpMetadataDownloader,
    ImageOcrExtractor, VideoFrameOCRExtractor
)

logger = logging.getLogger(__name__)


class YouTubeProcessor:
    def __init__(self, use_cookies: bool = False, rate_limiter = None):
        self._transcriber = None
        self.use_cookies = use_cookies
        self.rate_limiter = rate_limiter
        self.downloader = YtDlpAudioDownloader.from_env(
            use_cookies=use_cookies,
            rate_limiter=rate_limiter,
        )
        self.meta_downloader = RealYtDlpMetadataDownloader(use_cookies=use_cookies)
        self.ocr = ImageOcrExtractor()

    def get_transcriber(self) -> GroqAudioTranscriber:
        if self._transcriber is None:
            self._transcriber = GroqAudioTranscriber.from_env()
        return self._transcriber

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        with tempfile.TemporaryDirectory(prefix="seed-yt-shorts-") as tmp_dir:
            tmp_path = Path(tmp_dir)

            # 1. Скачиваем аудио и транскрибируем
            transcript = ""
            try:
                audio_path = self.downloader.download_audio(item.url, tmp_path)
                transcript = self.get_transcriber().transcribe(audio_path).strip()
            except Exception as e:
                logger.warning("Транскрибация не удалась: %s", e)


            # 2. Если транскрибация пустая или ≤3 слов — покадровый OCR
            video_ocr_text = ""
            words = transcript.split() if transcript else []
            if not transcript or transcript.lower() in ('', 'нет') or len(words) <= 3:
                logger.info("Транскрибация слабая (%r), запускаем покадровый OCR для %s", transcript, item.url)
                try:
                    video_path = self.downloader.download_video(item.url, tmp_path)
                    if video_path:
                        ocr_extractor = VideoFrameOCRExtractor(self.ocr, frame_interval=2.0)
                        video_ocr_text = ocr_extractor.extract_text(video_path, tmp_path)
                except Exception as e:
                    logger.warning("Покадровый OCR не удался: %s", e)


            # 3. Метаданные
            views, likes = "", ""
            try:
                meta = self.meta_downloader.get_metadata(item.url)
                views = str(meta.get("view_count", ""))
                likes = str(meta.get("like_count", ""))
            except Exception:
                pass

            ocr_section = f"1 – Текст на фото:\n{video_ocr_text}" if video_ocr_text else "1 – Текст на фото: нет"
            material = f"{ocr_section}\n\n2 – Транскрибация аудио/видео:\n{transcript if transcript else 'нет'}"
            return LinkProcessorResult(
                material=material,
                comment=item.context.strip() or "YouTube Shorts processed by YouTubeProcessor.",
                views=views,
                likes=likes
            )