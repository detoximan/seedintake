from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import (
    LinkProcessorResult, ImageOcrExtractor, GroqAudioTranscriber,
    YtDlpAudioDownloader, YtDlpMediaDownloader, RealYtDlpMetadataDownloader,
    VideoFrameOCRExtractor
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

            # 1. Скачиваем всё (видео и/или фото) через yt-dlp с cookies
            video_downloader = YtDlpMediaDownloader(
                use_cookies=self.use_cookies,
                browser="firefox",
                rate_limiter=self.rate_limiter,
            )
            files = video_downloader.download_all(item.url, tmp_path)
            if not files:
                logger.warning("yt-dlp didn't download any files for %s", item.url)

            images = sorted([f for f in files if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}])
            videos = sorted([f for f in files if f.suffix.lower() in {'.mp4', '.mov', '.webm'}])

            # 2. OCR для фото
            ocr_results = []
            for img in images:
                txt = self.ocr.extract(img)
                if txt and not txt.startswith("(пусто)") and not txt.startswith("(ошибка"):
                    ocr_results.append(f"[{img.name}]: {txt}")

            # 3. Транскрибация для видео
            trans_results = []
            for vid in videos:
                try:
                    audio_path = self._extract_audio_from_video(vid, tmp_path)
                    text = self.get_transcriber().transcribe(audio_path).strip()
                    if text and text.lower() not in ('', 'нет'):
                        trans_results.append(f"[{vid.name}]: {text}")
                    else:
                        # Транскрибация пустая — значит музыка без речи.
                        # Делаем покадровый OCR видео.
                        logger.info("Транскрибация пустая для %s, запускаем покадровый OCR", vid.name)
                        ocr_extractor = VideoFrameOCRExtractor(self.ocr, frame_interval=2.0)
                        video_ocr_text = ocr_extractor.extract_text(vid, tmp_path)
                        if video_ocr_text:
                            ocr_results.append(f"[{vid.name}]: {video_ocr_text}")
                except Exception as e:
                    logger.warning("TikTok обработка видео %s не удалась: %s", vid.name, e)

            # 4. Метаданные
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

    def _extract_audio_from_video(self, video_path: Path, workdir: Path) -> Path:
        """Извлекает аудио из видео через ffmpeg."""
        import subprocess
        audio_path = workdir / f"{video_path.stem}.mp3"
        command = [
            "ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "libmp3lame",
            "-ab", "64k", str(audio_path)
        ]
        try:
            subprocess.run(command, capture_output=True, check=True, timeout=60)
            return audio_path
        except Exception as e:
            logger.warning("ffmpeg audio extraction failed, using original video: %s", e)
            return video_path