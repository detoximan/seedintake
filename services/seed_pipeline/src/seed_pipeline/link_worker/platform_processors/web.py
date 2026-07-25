from __future__ import annotations

from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.link_worker.processors import (
    LinkProcessorResult, TextPostProcessor, RealYtDlpMetadataDownloader, JinaApiReader
)


class WebProcessor:
    def __init__(self, use_cookies: bool = False, rate_limiter = None):
        self.processor = TextPostProcessor(
            ytdlp=RealYtDlpMetadataDownloader(use_cookies=use_cookies),
            jina=JinaApiReader()
        )

    def process(self, item: LinkQueueItem) -> LinkProcessorResult:
        return self.processor.process(item)
