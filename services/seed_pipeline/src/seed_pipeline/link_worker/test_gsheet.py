import sys
import logging
from pathlib import Path

# Add src to pythonpath
sys.path.insert(0, str(Path("services/seed_pipeline/src").absolute()))

from seed_pipeline.link_worker.processors import UniversalMediaProcessor
from seed_pipeline.link_worker.queue import LinkQueueItem
from seed_pipeline.integrations.google import LiveGoogleWorkspace

logging.basicConfig(level=logging.INFO)

# 1. Распознаем текст (используем тот же код, что работал)
class FakeTranscriber:
    def transcribe(self, path):
        return f"fake_transcript_for_{path.name}"

processor = UniversalMediaProcessor.from_env()
processor.transcriber = FakeTranscriber()

url = "https://www.tiktok.com/@/photo/7428125895535185158?_r=1&_d=secCgYIASAHKAESPgo8fKdcjKV4KDXKM7uGYr58z4aSTHeG%2ByP8LwwgPo%2Bw7mi2g923TaTrnRO1BQKUgjdE5%2FxzEiJQbSfthIKoGgA%3D&u_code=e98ci1360am4ii&share_item_id=7428125895535185158&timestamp=1729633422&utm_campaign=client_share&utm_source=short_fallback&share_app_id=1233"

item = LinkQueueItem(
    path=Path("dummy"),
    relative_path="dummy",
    status="pending",
    url=url,
    platform="tiktok",
    context="Тест карусели Фрейда",
)

try:
    print("Начинаем обработку через UniversalMediaProcessor...")
    result = processor.process(item)
    print("Обработка завершена! Длина материала:", len(result.material))

    # 2. Отправляем в Google Sheet и Seed
    print("\nПодключаемся к Google Workspace...")
    workspace = LiveGoogleWorkspace()
    workspace.setup()
    
    # Чтобы запись попала в Seed и Google Sheet, нам нужно использовать методы workspace.
    # В реальном worker'е это делается так:
    # record = InboxRecord(...)
    # self.workspace.create_inbox_record(record)
    
    print("\nПопытка записать в Google Sheet напрямую отсюда нежелательна, так как мы создадим мусорную запись в Inbox,")
    print("которая сломает реальную очередь. Но мы можем вывести текст на экран, чтобы подтвердить, что он готов к отправке.")
    
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"\nFAILED: {e}")

