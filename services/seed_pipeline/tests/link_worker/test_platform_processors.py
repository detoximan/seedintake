import unittest
from pathlib import Path
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import PlatformLinkProcessor, get_cookies_file

class PlatformProcessorTests(unittest.TestCase):
    def test_instantiate_platform_processor(self):
        processor = PlatformLinkProcessor(use_cookies=True)
        self.assertTrue(processor.insta.use_cookies)
        self.assertTrue(processor.tiktok.use_cookies)
        self.assertTrue(processor.youtube.use_cookies)
        self.assertTrue(processor.web.processor.ytdlp.use_cookies)

    def test_get_cookies_file(self):
        # Even if file doesn't exist, function executes without error
        cookie_path = get_cookies_file("https://www.instagram.com/reel/123456/")
        if cookie_path is not None:
            self.assertTrue(isinstance(cookie_path, Path))

if __name__ == "__main__":
    unittest.main()
