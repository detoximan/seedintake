import unittest
from pathlib import Path

from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import TextPostProcessor, JinaReader, YtDlpMetadataDownloader

class FakeJinaReader:
    def __init__(self, text: str = "Fake jina text", fail_reason: str = ""):
        self.text = text
        self.fail_reason = fail_reason
        self.called_url = ""

    def read_text(self, url: str) -> str:
        self.called_url = url
        if self.fail_reason:
            raise RuntimeError(self.fail_reason)
        return self.text

class FakeYtDlpMetadataDownloader:
    def __init__(self, metadata: dict[str, str] = None, fail_reason: str = ""):
        self.metadata = metadata or {"title": "Fake title", "description": "Fake desc"}
        self.fail_reason = fail_reason
        self.called_url = ""

    def get_metadata(self, url: str) -> dict[str, str]:
        self.called_url = url
        if self.fail_reason:
            raise RuntimeError(self.fail_reason)
        return self.metadata

class TextPostProcessorTests(unittest.TestCase):
    def setUp(self):
        self.item = LinkQueueItem(
            path=Path("fake.md"),
            relative_path="fake.md",
            status="new",
            url="https://example.com/post",
            platform="text_post",
            context="My context"
        )
        
    def test_uses_ytdlp_first_then_returns_metadata(self):
        ytdlp = FakeYtDlpMetadataDownloader({"title": "IG Post", "description": "Awesome post!"})
        jina = FakeJinaReader(fail_reason="Should not be called")
        processor = TextPostProcessor(ytdlp=ytdlp, jina=jina)
        
        res = processor.process(self.item)
        
        self.assertEqual(ytdlp.called_url, self.item.url)
        self.assertEqual(jina.called_url, "")
        self.assertIn("IG Post", res.material)
        self.assertIn("Awesome post!", res.material)
        self.assertEqual(res.comment, "My context")

    def test_falls_back_to_jina_if_ytdlp_fails(self):
        ytdlp = FakeYtDlpMetadataDownloader(fail_reason="yt-dlp failed: unsupported URL")
        jina = FakeJinaReader(text="Jina extracted text")
        processor = TextPostProcessor(ytdlp=ytdlp, jina=jina)
        
        res = processor.process(self.item)
        
        self.assertEqual(ytdlp.called_url, self.item.url)
        self.assertEqual(jina.called_url, self.item.url)
        self.assertIn("Jina extracted text", res.material)
        
    def test_fails_completely_if_both_fail(self):
        ytdlp = FakeYtDlpMetadataDownloader(fail_reason="yt-dlp failed")
        jina = FakeJinaReader(fail_reason="Jina failed 451")
        processor = TextPostProcessor(ytdlp=ytdlp, jina=jina)
        
        with self.assertRaises(RuntimeError) as ctx:
            processor.process(self.item)
            
        self.assertIn("Jina failed 451", str(ctx.exception))
        
if __name__ == "__main__":
    unittest.main()
