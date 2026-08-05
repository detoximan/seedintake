from __future__ import annotations

import os
import logging
import tempfile
from pathlib import Path
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import (
    LinkProcessorResult, ImageOcrExtractor, GroqAudioTranscriber,
    RealYtDlpMetadataDownloader, YtDlpAudioDownloader, YtDlpMediaDownloader,
    InstaloaderMediaDownloader, GalleryDlMediaDownloader, VideoFrameOCRExtractor
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

    def _process_video_file(self, vid: Path, tmp_path: Path) -> tuple[str, str]:
        """
        Обрабатывает один видеофайл: транскрибация → если пусто, покадровый OCR.
        Возвращает (transcript_text, ocr_text).
        """
        ocr_text = ""
        transcript = ""
        try:
            audio_path = self._extract_audio_from_video(vid, tmp_path)
            transcript = self.get_transcriber().transcribe(audio_path).strip()
        except Exception as e:
            logger.warning("Транскрибация не удалась для %s: %s", vid.name, e)

        # Если транскрибация пустая — покадровый OCR
        if not transcript or transcript.lower() in ('', 'нет'):
            logger.info("Транскрибация пустая для %s, запускаем покадровый OCR", vid.name)
            try:
                ocr_extractor = VideoFrameOCRExtractor(self.ocr, frame_interval=2.0)
                ocr_text = ocr_extractor.extract_text(vid, tmp_path)
            except Exception as e:
                logger.warning("Покадровый OCR не удался для %s: %s", vid.name, e)

        return transcript, ocr_text

    def process_reels(self, item: LinkQueueItem) -> LinkProcessorResult:
        with tempfile.TemporaryDirectory(prefix="seed-insta-reel-") as tmp_dir:
            tmp_path = Path(tmp_dir)

            downloader = YtDlpAudioDownloader.from_env(
                use_cookies=self.use_cookies,
                rate_limiter=self.rate_limiter,
            )

            # 1. Пробуем скачать видео целиком (один запрос — из него и аудио, и кадры)
            video_path = downloader.download_video(item.url, tmp_path)

            # 2. Транскрибация: из видео (ffmpeg) или напрямую аудио (fallback)
            transcript = ""
            if video_path:
                try:
                    audio_path = self._extract_audio_from_video(video_path, tmp_path)
                    transcript = self.get_transcriber().transcribe(audio_path).strip()
                except Exception as e:
                    logger.warning("Транскрибация из видео не удалась: %s", e)
            else:
                # Видео не скачалось — пробуем аудио напрямую
                try:
                    audio_path = downloader.download_audio(item.url, tmp_path)
                    transcript = self.get_transcriber().transcribe(audio_path).strip()
                except Exception as e:
                    logger.warning("Транскрибация (прямое аудио) не удалась: %s", e)

            # 3. Если транскрибация пустая и видео есть — покадровый OCR
            video_ocr_text = ""
            if (not transcript or transcript.lower() in ('', 'нет')) and video_path:
                logger.info("Транскрибация пустая, запускаем покадровый OCR для %s", item.url)
                try:
                    ocr_extractor = VideoFrameOCRExtractor(self.ocr, frame_interval=2.0)
                    video_ocr_text = ocr_extractor.extract_text(video_path, tmp_path)
                except Exception as e:
                    logger.warning("Покадровый OCR не удался: %s", e)

            # 4. Метаданные
            views, likes, desc = "", "", ""
            try:
                meta = self.meta_downloader.get_metadata(item.url)
                views = str(meta.get("view_count", ""))
                likes = str(meta.get("like_count", ""))
                desc = meta.get("description", "").strip()
            except Exception as e:
                logger.warning("Не удалось получить метаданные для Insta reel: %s", e)

            ocr_section = video_ocr_text if video_ocr_text else "нет"
            parts = [
                f"1 – Текст на фото:\n{ocr_section}",
                f"2 – Транскрибация аудио/видео:\n{transcript if transcript else 'нет'}",
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

            # 1. Try Instaloader first (best for carousels)
            try:
                instaloader = InstaloaderMediaDownloader(use_cookies=self.use_cookies)
                files = instaloader.download_all(item.url, tmp_path)
                if files:
                    logger.info("Instaloader downloaded %d files", len(files))
                else:
                    logger.warning("Instaloader returned empty files for %s", item.url)
            except Exception as e:
                logger.warning("Instaloader failed: %s", e)

            # 2. Fallback: gallery-dl
            if not files:
                try:
                    logger.info("Falling back to gallery-dl for %s", item.url)
                    gdl = GalleryDlMediaDownloader(use_cookies=self.use_cookies)
                    files = gdl.download_all(item.url, tmp_path)
                    if files:
                        logger.info("gallery-dl downloaded %d files", len(files))
                    else:
                        logger.warning("gallery-dl also returned empty files for %s", item.url)
                except Exception as e:
                    logger.warning("gallery-dl fallback also failed: %s", e)

            # 3. Fallback: yt-dlp (для видео-каруселей)
            if not files:
                try:
                    logger.info("Falling back to yt-dlp for %s", item.url)
                    ytdlp = YtDlpMediaDownloader(
                        use_cookies=self.use_cookies,
                        browser="firefox",
                        rate_limiter=self.rate_limiter,
                    )
                    files = ytdlp.download_all(item.url, tmp_path)
                except Exception as e:
                    logger.warning("yt-dlp fallback also failed: %s", e)

            if not files:
                logger.warning("NO FILES downloaded by any method for %s", item.url)

            # 4. Разделяем на фото и видео
            images = sorted([f for f in files if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}])
            videos = sorted([f for f in files if f.suffix.lower() in {'.mp4', '.mov', '.webm'}])

            # 5. OCR для фото
            ocr_results = []
            for img in images:
                txt = self.ocr.extract(img)
                if txt and not txt.startswith("(пусто)") and not txt.startswith("(ошибка"):
                    ocr_results.append(f"[{img.name}]: {txt}")

            # 6. Обработка видео в карусели (транскрибация → если пусто, OCR кадров)
            trans_results = []
            for vid in videos:
                transcript, video_ocr_text = self._process_video_file(vid, tmp_path)
                if transcript and transcript.lower() not in ('', 'нет'):
                    trans_results.append(f"[{vid.name}]: {transcript}")
                if video_ocr_text:
                    ocr_results.append(f"[{vid.name}]: {video_ocr_text}")

            # 7. Метаданные
            views, likes, desc = "", "", ""
            try:
                meta = self.meta_downloader.get_metadata(item.url)
                views = str(meta.get("view_count", ""))
                likes = str(meta.get("like_count", ""))
                desc = meta.get("description", "").strip()
            except Exception:
                pass

            ocr_text = "\n".join(ocr_results) if ocr_results else "нет"
            trans_text = "\n".join(trans_results) if trans_results else "нет"
            parts = [
                f"1 – Текст на фото:\n{ocr_text}",
                f"2 – Транскрибация аудио/видео:\n{trans_text}",
                f"3 – Текст под медиа:\n{desc if desc else 'нет'}"
            ]
            return LinkProcessorResult(
                material="\n\n".join(parts),
                comment=item.context.strip() or "Instagram Carousel/Post processed by InstagramProcessor.",
                views=views,
                likes=likes
            )