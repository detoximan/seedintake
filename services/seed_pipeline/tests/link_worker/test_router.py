import unittest
from seed_pipeline.link_worker.router import LinkRouter, LinkPlatformType

class LinkRouterTests(unittest.TestCase):
    def test_instagram_urls(self):
        self.assertEqual(
            LinkRouter.resolve_platform("https://www.instagram.com/reel/C_M-kYyiBI_/?igsh=123"),
            LinkPlatformType.INSTAGRAM_REELS
        )
        self.assertEqual(
            LinkRouter.resolve_platform("https://www.instagram.com/p/C6a8gWYsI5g/"),
            LinkPlatformType.INSTAGRAM_CAROUSEL
        )

    def test_tiktok_urls(self):
        self.assertEqual(
            LinkRouter.resolve_platform("https://www.tiktok.com/@user/video/71234567890"),
            LinkPlatformType.TIKTOK_VIDEO
        )
        self.assertEqual(
            LinkRouter.resolve_platform("https://www.tiktok.com/@user/photo/71234567890"),
            LinkPlatformType.TIKTOK_PHOTO
        )
        self.assertEqual(
            LinkRouter.resolve_platform("https://vt.tiktok.com/ZS2o2Hp3a/"),
            LinkPlatformType.TIKTOK_VIDEO
        )

    def test_youtube_urls(self):
        self.assertEqual(
            LinkRouter.resolve_platform("https://www.youtube.com/shorts/qMJOD0-E5vk"),
            LinkPlatformType.YOUTUBE_SHORTS
        )
        self.assertEqual(
            LinkRouter.resolve_platform("https://youtu.be/qMJOD0-E5vk"),
            LinkPlatformType.YOUTUBE_SHORTS
        )

    def test_facebook_threads_and_fallback(self):
        self.assertEqual(
            LinkRouter.resolve_platform("https://www.facebook.com/watch/?v=12345"),
            LinkPlatformType.FACEBOOK_POST
        )
        self.assertEqual(
            LinkRouter.resolve_platform("https://www.threads.net/@user/post/12345"),
            LinkPlatformType.THREADS_POST
        )
        self.assertEqual(
            LinkRouter.resolve_platform("https://example.com/article/123"),
            LinkPlatformType.TEXT_POST
        )

if __name__ == "__main__":
    unittest.main()
