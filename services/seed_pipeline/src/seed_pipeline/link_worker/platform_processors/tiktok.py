from __future__ import annotations

import logging
import os
import requests
import subprocess
import tempfile
from pathlib import Path
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import (
    LinkProcessorResult, ImageOcrExtractor, GroqAudioTranscriber,
    YtDlpAudioDownloader, YtDlpMediaDownloader, RealYtDlpMetadataDownloader,
    VideoFrameOCRExtractor, GalleryDlMediaDownloader
)

logger = logging.getLogger(__name__)


class TikTokProcessor:
    def __init__(self, use_cookies: bool = False, rate_limiter = None):
        self.ocr = ImageOcrExtractor()
        self._transcriber = None
        self.use_cookies = use_cookies
        self.rate_limiter = rate_limiter
        self.meta_downloader = RealYtDlpMetadataDownloader(use_cookies=use_cookies)
        self.gallery_dl = GalleryDlMediaDownloader(use_cookies=use_cookies)

    def get_transcriber(self) -> GroqAudioTranscriber:
        if self._transcriber is None:
            self._transcriber = GroqAudioTranscriber.from_env()
        return self._transcriber

    def _download_via_direct_api(self, url: str, target_dir: Path) -> tuple[list[Path], dict]:
        """Скачивает медиа через TikWM API (устойчив к бот-челленджам TikTok)."""
        try:
            api_url = "https://www.tikwm.com/api/"
            res = requests.post(api_url, data={"url": url, "count": 12, "cursor": 0, "web": 1, "hd": 1}, timeout=20)
            if res.status_code != 200:
                return [], {}
            data = res.json()
            if data.get("code") != 0 or not data.get("data"):
                return [], {}
            d = data["data"]
            files: list[Path] = []
            
            # Фото-слайды (images)
            images = d.get("images") or []
            if images:
                for idx, img_url in enumerate(images, start=1):
                    ext = "jpg"
                    f_path = target_dir / f"slide_{idx:02d}.{ext}"
                    r = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                    if r.status_code == 200:
                        f_path.write_bytes(r.content)
                        files.append(f_path)
            
            # Видео (play)
            play_rel = d.get("play")
            if play_rel and not images:
                play_url = "https://www.tikwm.com" + play_rel if play_rel.startswith("/") else play_rel
                f_path = target_dir / f"{d.get('id', 'video')}.mp4"
                r = requests.get(play_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
                if r.status_code == 200:
                    f_path.write_bytes(r.content)
                    files.append(f_path)
                    
            meta = {
                "views": str(d.get("play_count", "")),
                "likes": str(d.get("digg_count", "")),
                "description": d.get("title", "").strip()
            }
            return files, meta
        except Exception as e:
            logger.warning("TikWM API download failed: %s", e)
            return [], {}

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        with tempfile.TemporaryDirectory(prefix="seed-tiktok-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            files = []
            meta_info = {}

            # 1. Сначала пробуем прямой API TikWM
            files, meta_info = self._download_via_direct_api(item.url, tmp_path)

            # 2. Если API не вернул файлы, пробуем gallery-dl
            if not files:
                logger.info("Trying gallery-dl for TikTok: %s", item.url)
                files = self.gallery_dl.download_all(item.url, tmp_path)

            # 3. Если всё ещё пусто, пробуем yt-dlp
            if not files:
                logger.info("Trying yt-dlp for TikTok: %s", item.url)
                video_downloader = YtDlpMediaDownloader(
                    use_cookies=self.use_cookies,
                    browser="firefox",
                    rate_limiter=self.rate_limiter,
                )
                files = video_downloader.download_all(item.url, tmp_path)

            images = sorted([f for f in files if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}])
            videos = sorted([f for f in files if f.suffix.lower() in {'.mp4', '.mov', '.webm'}])

            # OCR для фото/слайдов
            ocr_results = []
            for img in images:
                txt = self.ocr.extract(img)
                if txt and not txt.startswith("(пусто)") and not txt.startswith("(ошибка"):
                    ocr_results.append(f"[{img.name}]: {txt}")

            # Транскрибация речи для видео
            trans_results = []
            for vid in videos:
                try:
                    audio_path = self._extract_audio_from_video(vid, tmp_path)
                    text = self.get_transcriber().transcribe(audio_path).strip()
                    if text and text.lower() not in ('', 'нет'):
                        trans_results.append(f"[{vid.name}]: {text}")
                    else:
                        # Речи нет (музыка/тишина) -> покадровый OCR
                        logger.info("Транскрибация пустая для %s, запускаем покадровый OCR", vid.name)
                        ocr_extractor = VideoFrameOCRExtractor(self.ocr, frame_interval=2.0)
                        video_ocr_text = ocr_extractor.extract_text(vid, tmp_path)
                        if video_ocr_text:
                            ocr_results.append(f"[{vid.name}]: {video_ocr_text}")
                except Exception as e:
                    logger.warning("TikTok обработка видео %s не удалась: %s", vid.name, e)

            # Метаданные (просмотры, лайки, описание)
            views = meta_info.get("views", "")
            likes = meta_info.get("likes", "")
            desc = meta_info.get("description", "")

            if not views or not likes or not desc:
                try:
                    meta = self.meta_downloader.get_metadata(item.url)
                    if not views:
                        views = str(meta.get("view_count", ""))
                    if not likes:
                        likes = str(meta.get("like_count", ""))
                    if not desc:
                        desc = meta.get("description", "").strip()
                except Exception:
                    pass

            ocr_str = "\
".join(ocr_results) if ocr_results else "нет"
            trans_str = "\
".join(trans_results) if trans_results else "нет"
            parts = [
                f"1 – Текст на фото:\
{ocr_str}",
                f"2 – Транскрибация аудио/видео:\
{trans_str}",
                f"3 – Текст под медиа:\
{desc if desc else 'нет'}"
            ]
            return LinkProcessorResult(
                material="\
\
".join(parts),
                comment=item.context.strip() or "TikTok content processed by TikTokProcessor.",
                views=views,
                likes=likes
            )

    def _extract_audio_from_video(self, video_path: Path, workdir: Path) -> Path:
        """Извлекает аудио из видео через ffmpeg."""
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
