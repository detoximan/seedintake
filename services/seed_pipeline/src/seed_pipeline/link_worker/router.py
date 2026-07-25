from __future__ import annotations

import re
from enum import Enum
from urllib.parse import urlparse


class LinkPlatformType(str, Enum):
    INSTAGRAM_REELS = "instagram_reels"
    INSTAGRAM_CAROUSEL = "instagram_carousel"
    TIKTOK_VIDEO = "tiktok_video"
    TIKTOK_PHOTO = "tiktok_photo"
    YOUTUBE_SHORTS = "youtube_shorts"
    FACEBOOK_POST = "facebook_post"
    THREADS_POST = "threads_post"
    TEXT_POST = "text_post"


class LinkRouter:
    """Маршрутизатор URL. Быстро и без сетевых запросов определяет тип контента по паттерну ссылки."""

    @classmethod
    def resolve_platform(cls, url: str) -> LinkPlatformType:
        normalized_url = url.strip()
        parsed = urlparse(normalized_url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()

        # 1. Instagram
        if "instagram.com" in domain or "instagr.am" in domain:
            if "/reel/" in path or "/reels/" in path:
                return LinkPlatformType.INSTAGRAM_REELS
            if "/p/" in path or "/tv/" in path:
                return LinkPlatformType.INSTAGRAM_CAROUSEL
            return LinkPlatformType.INSTAGRAM_CAROUSEL  # по умолчанию считаем постом/каруселью

        # 2. TikTok
        if "tiktok.com" in domain:
            if "/photo/" in path:
                return LinkPlatformType.TIKTOK_PHOTO
            if "/video/" in path or "/v/" in path:
                return LinkPlatformType.TIKTOK_VIDEO
            return LinkPlatformType.TIKTOK_VIDEO

        # 3. YouTube Shorts / Video
        if "youtube.com" in domain or "youtu.be" in domain:
            if "/shorts/" in path or "youtu.be" in domain:
                return LinkPlatformType.YOUTUBE_SHORTS
            return LinkPlatformType.YOUTUBE_SHORTS

        # 4. Facebook
        if "facebook.com" in domain or "fb.watch" in domain or "fb.com" in domain:
            return LinkPlatformType.FACEBOOK_POST

        # 5. Threads
        if "threads.net" in domain:
            return LinkPlatformType.THREADS_POST

        # 6. Fallback (любая статья или текстовая ссылка)
        return LinkPlatformType.TEXT_POST
