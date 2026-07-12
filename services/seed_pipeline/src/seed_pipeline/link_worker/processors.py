from __future__ import annotations

import json
import logging
import mimetypes
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib import error, request

# OCR dependencies
try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

logger = logging.getLogger(__name__)


class RateLimiter:
    """Ограничивает частоту запросов с cookies."""
    def __init__(self, file_path: Path, min_interval: float = 300.0):
        self.file_path = file_path
        self.min_interval = min_interval

    def wait_if_needed(self):
        now = time.time()
        last_time = 0.0
        if self.file_path.exists():
            try:
                data = json.loads(self.file_path.read_text())
                last_time = data.get('last_request', 0.0)
            except Exception:
                pass
        elapsed = now - last_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        # Update timestamp
        self.file_path.write_text(json.dumps({'last_request': time.time()}))


from .queue import LinkQueueItem
from .jina import JinaReader, JinaApiReader
from .ytdlp import YtDlpMetadataDownloader, RealYtDlpMetadataDownloader


@dataclass(frozen=True)
class LinkProcessorResult:
    material: str
    comment: str = ""
    views: str = ""
    likes: str = ""


class LinkProcessor(Protocol):
    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        pass


class AudioDownloader(Protocol):
    def download_audio(self, url: str, target_dir: Path) -> Path:
        pass


class AudioTranscriber(Protocol):
    def transcribe(self, audio_path: Path) -> str:
        pass


class FakeLinkProcessor:
    """Deterministic scaffold processor for tests and local worker smoke checks."""

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        context = item.context.strip()
        material_parts = [
            "Link worker fake processor output.",
            f"Platform: {item.platform}",
            f"URL: {item.url}",
        ]
        if context:
            material_parts.extend(["Context:", context])
        return LinkProcessorResult(
            material="\n".join(material_parts),
            comment=context or "Local link worker fake processor.",
        )


class FailingLinkProcessor:
    def __init__(self, reason: str = "Synthetic processor failure") -> None:
        self.reason = reason

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        raise RuntimeError(self.reason)


class PlatformLinkProcessor:
    def __init__(
        self,
        *,
        youtube_shorts: LinkProcessor | None = None,
        text_post: LinkProcessor | None = None,
        instagram_reels: LinkProcessor | None = None,
        tiktok: LinkProcessor | None = None,
        instagram_post: LinkProcessor | None = None,
    ) -> None:
        self.youtube_shorts = youtube_shorts
        self.text_post = text_post
        self.instagram_reels = instagram_reels
        self.tiktok = tiktok
        self.instagram_post = instagram_post

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        if item.platform == "youtube_shorts":
            if self.youtube_shorts is None:
                self.youtube_shorts = YouTubeShortsProcessor.from_env()
            return self.youtube_shorts.process(item)
        if item.platform == "text_post":
            if self.text_post is None:
                self.text_post = TextPostProcessor.from_env()
            return self.text_post.process(item)
        if item.platform == "instagram_reels":
            if self.instagram_reels is None:
                self.instagram_reels = InstagramReelsProcessor.from_env()
            return self.instagram_reels.process(item)
        if item.platform == "tiktok":
            if self.tiktok is None:
                self.tiktok = UniversalMediaProcessor.from_env(use_cookies=True)
            return self.tiktok.process(item)
        if item.platform == "instagram_post":
            if self.instagram_post is None:
                self.instagram_post = UniversalMediaProcessor.from_env()
            return self.instagram_post.process(item)
        raise RuntimeError(f"Unsupported link platform for local worker: {item.platform}")


class TextPostProcessor:
    def __init__(self, *, ytdlp: YtDlpMetadataDownloader, jina: JinaReader) -> None:
        self.ytdlp = ytdlp
        self.jina = jina

    @classmethod
    def from_env(cls) -> "TextPostProcessor":
        return cls(
            ytdlp=RealYtDlpMetadataDownloader(),
            jina=JinaApiReader(),
        )

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        if item.platform != "text_post":
            raise RuntimeError(f"Text Post processor received unsupported platform: {item.platform}")

        material_parts = []

        # 1. Try yt-dlp first (great for protected social media)
        try:
            metadata = self.ytdlp.get_metadata(item.url)
            title = metadata.get("title")
            desc = metadata.get("description")
            
            if title:
                material_parts.extend(["Заголовок:", title, ""])
            if desc:
                material_parts.extend(["Описание/Текст:", desc])
                
            if title or desc:
                comment = item.context.strip() or "Text post processed by local Seed Link Worker (yt-dlp fallback)."
                return LinkProcessorResult(
                    material="\n".join(material_parts).strip(), 
                    comment=comment,
                    views=metadata.get("view_count", ""),
                    likes=metadata.get("like_count", "")
                )
        except RuntimeError:
            pass # fallback to Jina

        # 2. Try Jina Reader API (great for articles, Telegram, open pages)
        text = self.jina.read_text(item.url)
        material_parts.append(text)
        
        comment = item.context.strip() or "Text post processed by local Seed Link Worker (Jina Reader)."
        return LinkProcessorResult(material="\n".join(material_parts).strip(), comment=comment)


class VideoTranscriptionProcessor:
    def __init__(
        self,
        *,
        platform: str,
        downloader: AudioDownloader,
        transcriber: AudioTranscriber,
        default_comment: str,
        temp_dir_prefix: str,
    ) -> None:
        self.platform = platform
        self.downloader = downloader
        self.transcriber = transcriber
        self.default_comment = default_comment
        self.temp_dir_prefix = temp_dir_prefix

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        if item.platform != self.platform:
            raise RuntimeError(f"{self.__class__.__name__} received unsupported platform: {item.platform}")

        with tempfile.TemporaryDirectory(prefix=self.temp_dir_prefix) as temp_dir:
            audio_path = self.downloader.download_audio(item.url, Path(temp_dir))
            transcript = self.transcriber.transcribe(audio_path).strip()

        if not transcript:
            raise RuntimeError("Groq transcription returned empty text")

        # Fetch metadata for views/likes
        views, likes = "", ""
        if hasattr(self.downloader, 'executable'): # Check if it's YtDlp based
            try:
                from .ytdlp import RealYtDlpMetadataDownloader
                meta_dl = RealYtDlpMetadataDownloader(executable=getattr(self.downloader, 'executable'))
                metadata = meta_dl.get_metadata(item.url)
                views = metadata.get("view_count", "")
                likes = metadata.get("like_count", "")
            except Exception:
                pass

        material = transcript
        comment = item.context.strip() or self.default_comment
        return LinkProcessorResult(material=material, comment=comment, views=views, likes=likes)


class YouTubeShortsProcessor(VideoTranscriptionProcessor):
    def __init__(self, *, downloader: AudioDownloader, transcriber: AudioTranscriber) -> None:
        super().__init__(
            platform="youtube_shorts",
            downloader=downloader,
            transcriber=transcriber,
            default_comment="YouTube Shorts processed by local Seed Link Worker.",
            temp_dir_prefix="seed-link-worker-youtube-",
        )

    @classmethod
    def from_env(cls) -> "YouTubeShortsProcessor":
        return cls(
            downloader=YtDlpAudioDownloader.from_env(),
            transcriber=GroqAudioTranscriber.from_env(),
        )


class InstagramReelsProcessor(VideoTranscriptionProcessor):
    def __init__(self, *, downloader: AudioDownloader, transcriber: AudioTranscriber) -> None:
        super().__init__(
            platform="instagram_reels",
            downloader=downloader,
            transcriber=transcriber,
            default_comment="Instagram Reels processed by local Seed Link Worker.",
            temp_dir_prefix="seed-link-worker-reels-",
        )

    @classmethod
    def from_env(cls) -> "InstagramReelsProcessor":
        return cls(
            downloader=YtDlpAudioDownloader.from_env(),
            transcriber=GroqAudioTranscriber.from_env(),
        )


class ImageOcrExtractor:
    """Извлекает текст из изображений с помощью Tesseract."""
    def __init__(self, lang: str = "rus+eng"):
        if not _OCR_AVAILABLE:
            raise RuntimeError("Для OCR нужны pytesseract и Pillow. Установи: pip install pytesseract Pillow")
        self.lang = lang
        self._available_langs: set[str] | None = None
        self._effective_lang: str | None = None
        self._diagnose_once()

    def _diagnose_once(self) -> None:
        """Один раз при инициализации логируем версию и доступные языки."""
        try:
            version = pytesseract.get_tesseract_version()
            langs = set(pytesseract.get_languages(config=""))
            self._available_langs = langs
            logger.info(
                "Tesseract OK: version=%s, cmd=%s, langs=%s",
                version,
                pytesseract.pytesseract.tesseract_cmd,
                sorted(langs),
            )
            # Подбираем фактический lang: оставляем только те, что реально есть
            requested = [p for p in self.lang.split("+") if p]
            present = [p for p in requested if p in langs]
            missing = [p for p in requested if p not in langs]
            if missing:
                logger.warning(
                    "Tesseract: запрошены языки %s, но отсутствуют %s. "
                    "Будем использовать: %s",
                    requested, missing, present or ["eng"],
                )
            self._effective_lang = "+".join(present) if present else "eng"
        except Exception as e:
            logger.error(
                "Tesseract diagnostic failed: %s. "
                "Проверь, что бинарник tesseract установлен и доступен в PATH "
                "(tesseract --version) и установлены языковые пакеты "
                "(tesseract --list-langs).",
                e,
            )
            # Не падаем — пусть extract() сам залогирует ошибку на каждом файле
            self._effective_lang = self.lang

    def extract(self, image_path: Path) -> str:
        try:
            img = Image.open(image_path)
            lang = self._effective_lang or self.lang
            text = pytesseract.image_to_string(img, lang=lang).strip()
            
            # КЛЮЧЕВОЕ: логируем сырой результат до любой фильтрации
            logger.debug(
                "OCR raw [%s] lang=%s len=%d preview=%r",
                image_path.name, lang, len(text), text[:120],
            )
            
            return text if text else "(пусто)"
        except Exception as e:
            logger.warning(
                "OCR failed for %s: %s (type=%s)",
                image_path.name, e, type(e).__name__,
            )
            return f"(ошибка OCR: {e})"


class YtDlpMediaDownloader:
    """Скачивает все медиафайлы (фото+видео) без конвертации в аудио."""
    def __init__(self, *, executable: str = "yt-dlp", use_cookies: bool = False, browser: str = "chrome", rate_limiter = None) -> None:
        self.executable = executable
        self.use_cookies = use_cookies
        self.browser = browser
        self.rate_limiter = rate_limiter

    def download_all(self, url: str, target_dir: Path) -> list[Path]:
        import os
        import uuid
        import shutil
        import subprocess

        if shutil.which(self.executable) is None:
            raise RuntimeError("yt-dlp is not installed or is not on PATH")

        target_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "--no-playlist",
            "--paths", str(target_dir),
            "--output", "%(id)s.%(ext)s",
        ]
        
        if self.use_cookies:
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()
            command.extend(["--cookies-from-browser", self.browser])
        
        command.append(url)
        
        try:
            completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("yt-dlp timed out while downloading media") from exc

        if completed.returncode != 0:
            detail = _last_nonempty_line(completed.stderr) or _last_nonempty_line(completed.stdout)
            logger.warning("yt-dlp media download failed: %s", detail or "unknown error")
            return []
        
        return [p for p in target_dir.iterdir() if p.is_file() and p.suffix not in {".part", ".ytdl", ".json"}]


class GalleryDlMediaDownloader:
    """Скачивает медиафайлы через gallery-dl (для TikTok каруселей)."""
    def __init__(self, *, executable: str | None = None, use_cookies: bool = False, browser: str = "firefox") -> None:
        self.executable = executable or os.getenv("GALLERY_DL_BIN", "gallery-dl").strip() or "gallery-dl"
        self.use_cookies = use_cookies
        self.browser = browser

    def _resolve_executable(self) -> str | None:
        import os
        import shutil
        # 1) явный путь, если он указывает на существующий файл
        if os.path.isabs(self.executable) and os.path.exists(self.executable):
            return self.executable
        # 2) что-то в PATH
        found = shutil.which(self.executable)
        if found:
            return found
        return None

    def download_all(self, url: str, target_dir: Path) -> list[Path]:
        import os
        import uuid
        import shutil
        import subprocess

        executable = self._resolve_executable()
        if not executable:
            logger.warning("gallery-dl executable not found")
            return []

        target_dir.mkdir(parents=True, exist_ok=True)
        log_file = target_dir / "_gallery_dl.log"
        command = [
            executable,
            "--verbose",
            "--write-log", str(log_file),
            "--directory", str(target_dir),
        ]
        
        cookies_file = os.getenv("SEED_TIKTOK_COOKIES")
        if cookies_file and Path(cookies_file).exists():
            command.extend(["--cookies", cookies_file])
        elif self.use_cookies:
            command.extend(["--cookies-from-browser", self.browser])
            
        command.append(url)
        
        import os
        logger.info("env diag: HOME=%s USER=%s PATH=%s CWD=%s", os.environ.get("HOME"), os.environ.get("USER"), os.environ.get("PATH"), os.getcwd())
        logger.info("gallery-dl resolved to: %s", executable)
        
        try:
            completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            logger.warning("gallery-dl timed out")
            return []

        logger.info(
            "gallery-dl finished rc=%s\nCMD: %s\nSTDOUT:\n%s\nSTDERR:\n%s",
            completed.returncode,
            " ".join(command),
            completed.stdout[:2000] if completed.stdout else "<empty>",
            completed.stderr[:2000] if completed.stderr else "<empty>",
        )

        if log_file.exists():
            artifact = Path("/tmp") / f"gallery-dl-{uuid.uuid4().hex[:8]}.log"
            import shutil
            shutil.copy(log_file, artifact)
            logger.warning("gallery-dl verbose log saved to %s", artifact)

        if completed.returncode != 0:
            logger.warning("gallery-dl failed or exited with warnings")
            # Не делаем return [], так как gallery-dl может выдать warning (например, cookies outdated), но файлы скачать
            
        all_files = []
        for p in sorted(target_dir.rglob('*')):
            if p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.webm', '.mp3', '.m4a'}:
                all_files.append(p)
        return all_files


class InstaloaderMediaDownloader:
    """Скачивает медиафайлы через instaloader Python API (поддерживает карусели Instagram).
    Загружает куки напрямую из браузера Chrome (через browser_cookie3)."""
    def __init__(self) -> None:
        pass

    def download_all(self, url: str, target_dir: Path) -> list[Path]:
        import os
        import uuid
        import shutil
        import subprocess

        import re
        try:
            import instaloader  # type: ignore
        except ImportError:
            raise RuntimeError("instaloader не установлен: pip install instaloader")

        try:
            import browser_cookie3  # type: ignore
        except ImportError:
            raise RuntimeError("browser_cookie3 не установлен: pip install browser_cookie3")

        # Extract shortcode from URL (/p/ for posts/carousels, /reel/ for reels)
        match = re.search(r'/(?:p|reel)/([^/?]+)', url)
        if not match:
            raise RuntimeError(f"Could not extract Instagram shortcode from URL: {url}")
        shortcode = match.group(1)

        target_dir.mkdir(parents=True, exist_ok=True)

        L = instaloader.Instaloader(
            dirname_pattern=str(target_dir),
            filename_pattern="{shortcode}_{mediaid}",
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
            post_metadata_txt_pattern="",
            compress_json=False,
        )

        logger.info("Instaloader: loading cookies directly from Firefox...")
        try:
            cj = browser_cookie3.firefox(domain_name='instagram.com')
            for cookie in cj:
                L.context._session.cookies.set_cookie(cookie)
            
            if 'sessionid' in L.context._session.cookies.get_dict():
                L.context.is_logged_in = True
                L.context.username = "firefox_user"
                logger.info("Instaloader: successfully injected Firefox cookies!")
            else:
                logger.warning("Instaloader: Firefox cookies loaded, but 'sessionid' not found")
        except Exception as e:
            logger.warning("Instaloader: failed to load Firefox cookies: %s", e)

        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=str(target_dir))
        except Exception as e:
            logger.warning("Instaloader download failed for %s: %s", shortcode, e)
            return []

        # Collect downloaded media files, sorted for carousel order
        all_files = []
        for p in sorted(target_dir.rglob('*')):
            if p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.webm'}:
                all_files.append(p)
        return all_files


class UniversalMediaProcessor:
    """
    Универсальный процессор для постов с медиа (Instagram Post, TikTok).
    Скачивает фото/видео, делает OCR для фото и транскрибацию для видео.
    """
    def __init__(self, *, media_downloader: YtDlpMediaDownloader, metadata_downloader, ocr_extractor: ImageOcrExtractor, transcriber, instaloader_downloader = None, gallery_dl_downloader = None) -> None:
        self.media_downloader = media_downloader
        self.metadata_downloader = metadata_downloader
        self.ocr = ocr_extractor
        self.transcriber = transcriber
        self.instaloader_downloader = instaloader_downloader
        self.gallery_dl_downloader = gallery_dl_downloader

    @classmethod
    def from_env(cls, *, use_cookies: bool = False, rate_limiter = None) -> "UniversalMediaProcessor":
        if use_cookies:
            media_downloader = YtDlpMediaDownloader(use_cookies=True, browser="firefox", rate_limiter=rate_limiter)
            metadata_downloader = RealYtDlpMetadataDownloader(use_cookies=True, browser="firefox")
            gallery_dl_downloader = GalleryDlMediaDownloader(use_cookies=True, browser="firefox")
        else:
            media_downloader = YtDlpMediaDownloader()
            metadata_downloader = RealYtDlpMetadataDownloader()
            gallery_dl_downloader = GalleryDlMediaDownloader()
        # Always try to create instaloader for carousel support
        try:
            instaloader_downloader = InstaloaderMediaDownloader()
        except Exception:
            instaloader_downloader = None
        return cls(
            media_downloader=media_downloader,
            metadata_downloader=metadata_downloader,
            ocr_extractor=ImageOcrExtractor(),
            transcriber=GroqAudioTranscriber.from_env(),
            instaloader_downloader=instaloader_downloader,
            gallery_dl_downloader=gallery_dl_downloader,
        )

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        with tempfile.TemporaryDirectory(prefix="seed-universal-") as tmp_dir:
            tmp_path = Path(tmp_dir)

            # 1. Скачиваем все файлы
            is_tiktok = item.platform == "tiktok"
            is_tiktok_photo = is_tiktok and "/photo/" in item.url

            files = []
            if is_tiktok and self.gallery_dl_downloader:
                logger.info("TikTok detected, trying gallery-dl first...")
                files = self.gallery_dl_downloader.download_all(item.url, tmp_path)
                
            if not files:
                logger.info("Falling back to yt-dlp...")
                files = self.media_downloader.download_all(item.url, tmp_path)
            
            # Если yt-dlp не скачал файлы и есть instaloader, пробуем его (для Instagram каруселей)
            if not files and self.instaloader_downloader and item.platform in ("instagram_post", "instagram_reels"):
                try:
                    logger.info("yt-dlp failed to download media. Waiting 15 seconds before trying Instaloader to prevent rate limits...")
                    import time
                    time.sleep(15)
                    files = self.instaloader_downloader.download_all(item.url, tmp_path)
                except Exception as e:
                    logger.warning(f"Instaloader also failed: {e}")
                    pass  # Игнорируем ошибки instaloader, продолжаем с пустым списком

            images = sorted([f for f in files if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}]) if files else []
            videos = sorted([f for f in files if f.suffix.lower() in {'.mp4', '.mov', '.webm'}]) if files else []
            audios = sorted([f for f in files if f.suffix.lower() in {'.mp3', '.m4a', '.wav', '.ogg'}]) if files else []

            # 2. Разделение вывода
            result_parts = []

            # Пункт 1: Текст на фото (OCR)
            if images:
                import re
                # Собираем все результаты OCR
                raw_ocr_results = []
                for img in images:
                    text = self.ocr.extract(img)
                    raw_ocr_results.append((img.name, text))
                
                # Фильтруем: убираем тексты, которые полностью содержатся в других
                # Используем нормализацию пробелов и буквы ё для корректного сравнения
                def normalize(t: str) -> str:
                    t = t.replace('ё', 'е').replace('Ё', 'Е')
                    return re.sub(r'\s+', ' ', t).strip().lower()

                # Нормализованные тексты по индексам
                normed = [normalize(text) for _, text in raw_ocr_results]

                filtered_ocr: list[tuple[str, str]] = []
                seen_norms: set[str] = set()

                for i, (name, text) in enumerate(raw_ocr_results):
                    norm = normed[i]
                    # пропускаем мусорные/служебные ответы OCR
                    if not norm or norm.startswith("(пусто)") or norm.startswith("(ошибка ocr"):
                        continue
                    # дубликат точного текста — оставляем только первое вхождение
                    if norm in seen_norms:
                        continue
                    # строгое подмножество какого-то другого (более полного) текста — выкидываем
                    is_strict_substring = any(
                        i != j and norm != normed[j] and norm in normed[j]
                        for j in range(len(raw_ocr_results))
                    )
                    if is_strict_substring:
                        continue
                    
                    filtered_ocr.append((name, text))
                    seen_norms.add(norm)
                
                if filtered_ocr:
                    ocr_texts = [f"[{name}]: {text}" for name, text in filtered_ocr]
                    result_parts.append("1 – Текст на фото:\n" + "\n".join(ocr_texts))
                else:
                    result_parts.append("1 – Текст на фото: нет")
            else:
                result_parts.append("1 – Текст на фото: нет")

            # Пункт 2: Транскрибация видео
            trans_texts = []
            for vid in videos:
                try:
                    audio_path = self._extract_audio_from_video(vid, tmp_path)
                    text = self.transcriber.transcribe(audio_path)
                    trans_texts.append(f"[{vid.name}]: {text}")
                except Exception as e:
                    trans_texts.append(f"[{vid.name}]: нет (ошибка: {e})")
            
            # Для TikTok photo/slideshow (is_tiktok_photo=True) или Instagram каруселей мы игнорируем транскрибацию аудио, 
            # так как это обычно просто музыкальный фон
            if not is_tiktok_photo:
                for aud in audios:
                    try:
                        text = self.transcriber.transcribe(aud)
                        trans_texts.append(f"[{aud.name}]: {text}")
                    except Exception as e:
                        trans_texts.append(f"[{aud.name}]: нет (ошибка: {e})")

            if trans_texts:
                result_parts.append("2 – Транскрибация аудио/видео:\n" + "\n".join(trans_texts))
            else:
                result_parts.append("2 – Транскрибация аудио/видео: нет (музыкальный фон проигнорирован)" if is_tiktok_photo else "2 – Транскрибация аудио/видео: нет")

            # Пункт 3: Текст под медиа + views/likes (один запрос метаданных)
            views, likes = "", ""
            try:
                meta = self.metadata_downloader.get_metadata(item.url)
                desc = meta.get("description", "").strip()
                result_parts.append(f"3 – Текст под медиа:\n{desc if desc else 'нет'}")
                views = str(meta.get("view_count", ""))
                likes = str(meta.get("like_count", ""))
            except Exception:
                result_parts.append("3 – Текст под медиа: нет (ошибка получения метаданных)")

            return LinkProcessorResult(
                material="\n\n".join(result_parts),
                comment=item.context.strip() or f"{item.platform} processed by Universal Media Worker.",
                views=views,
                likes=likes
            )

    def _extract_audio_from_video(self, video_path: Path, workdir: Path) -> Path:
        """Извлекает аудио из видео для Groq транскрибации."""
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


class YtDlpAudioDownloader:
    def __init__(self, *, executable: str = "yt-dlp", audio_format: str = "mp3", audio_quality: str = "64K") -> None:
        self.executable = executable
        self.audio_format = audio_format
        self.audio_quality = audio_quality

    @classmethod
    def from_env(cls) -> "YtDlpAudioDownloader":
        return cls(
            executable=os.getenv("YT_DLP_BIN", "yt-dlp").strip() or "yt-dlp",
            audio_format=os.getenv("LINK_WORKER_AUDIO_FORMAT", "mp3").strip() or "mp3",
            audio_quality=os.getenv("LINK_WORKER_AUDIO_QUALITY", "64K").strip() or "64K",
        )

    def download_audio(self, url: str, target_dir: Path) -> Path:
        if shutil.which(self.executable) is None:
            raise RuntimeError("yt-dlp is not installed or is not on PATH")

        target_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            self.audio_format,
            "--audio-quality",
            self.audio_quality,
            "--paths",
            str(target_dir),
            "--output",
            "%(id)s.%(ext)s",
            url,
        ]
        try:
            completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("yt-dlp timed out while downloading audio") from exc

        if completed.returncode != 0:
            detail = _last_nonempty_line(completed.stderr) or _last_nonempty_line(completed.stdout)
            raise RuntimeError(f"yt-dlp failed: {detail or 'download unavailable'}")

        audio_files = [
            path
            for path in target_dir.iterdir()
            if path.is_file() and not path.name.endswith((".part", ".ytdl", ".json"))
        ]
        if not audio_files:
            raise RuntimeError("yt-dlp did not produce an audio file")
        return max(audio_files, key=lambda path: path.stat().st_size)


class GroqAudioTranscriber:
    endpoint = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, *, api_key: str, model: str = "whisper-large-v3-turbo", language: str | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.language = language

    @classmethod
    def from_env(cls) -> "GroqAudioTranscriber":
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is required for YouTube Shorts transcription")
        language = os.getenv("GROQ_STT_LANGUAGE", "").strip() or None
        return cls(
            api_key=api_key,
            model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo").strip() or "whisper-large-v3-turbo",
            language=language,
        )

    def transcribe(self, audio_path: Path) -> str:
        fields = {"model": self.model}
        if self.language:
            fields["language"] = self.language
        body, content_type = _build_multipart_body(fields=fields, file_field="file", file_path=audio_path)
        http_request = request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": content_type, "User-Agent": "curl/7.68.0",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=180) as response:
                payload = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Groq transcription failed: {_compact_error(detail) or exc.reason}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Groq transcription unavailable: {exc.reason}") from exc

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Groq transcription returned invalid JSON") from exc
        text = str(parsed.get("text", "")).strip() if isinstance(parsed, dict) else ""
        if not text:
            raise RuntimeError("Groq transcription returned empty text")
        return text


def _build_multipart_body(*, fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----detoximan-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _last_nonempty_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        normalized = line.strip()
        if normalized:
            return normalized
    return ""


def _compact_error(text: str) -> str:
    return " ".join(text.strip().split())[:500]
