# Промпт: Реализация гибридного распознавания текста с видео (OCR + Whisper)

## Задача

В проекте SeedIntake необходимо реализовать **гибридный пайплайн распознавания контента с видео** — чтобы извлекать текст, который написан ПОВЕРХ видео (субтитры, заголовки, цитаты), даже когда в видео НЕТ голоса (только музыка). Сейчас `process_reels()` в `services/seed_pipeline/src/seed_pipeline/link_worker/platform_processors/instagram.py` скачивает только аудио и транскрибирует через Whisper. Если на видео есть текст, но нет голоса — контент теряется.

## Что нужно сделать

### 1. Гибридный пайплайн в `process_reels()`

1. Скачать **видео целиком** (не только аудио) через yt-dlp
2. Извлечь аудио и транскрибировать через Whisper (как сейчас)
3. Извлечь **кадры видео** через ffmpeg:
   - Кадр каждые 1-2 секунды (или через детекцию смены сцен `select='gt(scene,0.3)'`)
   - Сохранять в temp каталог
4. Прогнать каждый кадр через **Tesseract OCR** (уже используется для каруселей — `ImageOcrExtractor`)
5. Дедупликация похожих текстов между кадрами
6. **Логика объединения:**
   - Если Whisper вернул осмысленный текст (>50 символов) → используем транскрибацию + OCR как дополнение
   - Если Whisper пустой/короткий (<50 символов) → используем OCR как основной контент
7. Формат `material`:
   - `1 – Текст на видео (OCR):` — если есть OCR-текст
   - `2 – Транскрибация аудио/видео:` — транскрибация Whisper
   - `3 – Текст под медиа:` — описание поста
   - Поля, которых нет → `нет`

### 2. Новый класс `VideoFrameOcrExtractor`

Создать в `services/seed_pipeline/src/seed_pipeline/link_worker/processors.py`:

```python
class VideoFrameOcrExtractor:
    """Извлекает текст из видео через ffmpeg кадры + Tesseract OCR."""
    def extract(self, video_path: Path, tmp_dir: Path, fps: float = 0.5) -> list[str]:
        # 1. ffmpeg -i video.mp4 -vf "fps=0.5" frames/frame_%03d.png
        # 2. Для каждого кадра: tesseract OCR
        # 3. Дедупликация: сравнение нормализованных строк (удалить пробелы, lower())
        # 4. Возврат списка уникальных текстов
```

Требования:
- Использовать `ImageOcrExtractor` (уже существует)
- Дедупликация: если новый текст является подстрокой уже найденного (>80% совпадение) — пропустить
- Обрабатывать ошибки ffmpeg/tesseract без падения пайплайна

### 3. Обновить `process_reels()` в `instagram.py`

```python
def process_reels(self, item: LinkQueueItem) -> LinkProcessorResult:
    with tempfile.TemporaryDirectory(prefix="seed-insta-reel-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # 1. Скачать видео целиком
        video_path = downloader.download_video(item.url, tmp_path)
        
        # 2. Извлечь аудио из видео (ffmpeg)
        audio_path = extract_audio(video_path, tmp_path)
        transcript = self.get_transcriber().transcribe(audio_path).strip()
        
        # 3. OCR видео-кадров
        frame_ocr = self.frame_ocr.extract(video_path, tmp_path)
        
        # 4. Логика: если транскрипция пустая -> OCR основной
        if len(transcript) < 50 and frame_ocr:
            main_text = "\n".join(frame_ocr)
            parts = [
                f"1 – Текст на видео (OCR):\n{main_text}",
                "2 – Транскрибация аудио/видео: нет",
                f"3 – Текст под медиа:\n{desc if desc else 'нет'}"
            ]
        else:
            parts = [
                f"1 – Текст на видео (OCR):\n{chr(10).join(frame_ocr) if frame_ocr else 'нет'}",
                f"2 – Транскрибация аудио/видео:\n{transcript}",
                f"3 – Текст под медиа:\n{desc if desc else 'нет'}"
            ]
```

### 4. Обновить `YtDlpAudioDownloader` — добавить `download_video()`

Метод для скачивания полного видео:
- `yt-dlp -f "mp4" -o video.mp4 URL`
- Вернуть `Path` на видео файл
- Использовать те же cookies

### 5. Тесты

Добавить тесты для:
- `VideoFrameOcrExtractor` — на сгенерированном видео с текстом (ffmpeg из PNG + аудио тишина)
- Гибридная логика: аудио есть → транскрибация, аудио нет → OCR
- Дедупликация кадров

### 6. Критерии приёмки

- Reels с голосом: контент как раньше (транскрибация)
- Reels без голоса, но с текстом на видео: контент = OCR текст
- Reels с голосом И текстом: оба источника в material
- Ошибки ffmpeg/OCR не роняют обработку (fallback на текущий пайплайн)

## Контекст

- Код: `services/seed_pipeline/src/seed_pipeline/link_worker/platform_processors/instagram.py`
- Процессоры: `services/seed_pipeline/src/seed_pipeline/link_worker/processors.py`
- `ImageOcrExtractor` — уже есть (Tesseract), используется для каруселей
- `GroqAudioTranscriber` — уже есть (Whisper через Groq API)
- Команда запуска: `PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file <файл> --live-google`

## Опционально (мультимодальная модель)

Если Tesseract недостаточно точен для стилизованных шрифтов:
- Извлечь 3-5 ключевых кадров (первый, середина, последний кадры со сменой сцены)
- Отправить в **Groq Vision** / другую vision-модель
- Промпт: "Прочитай весь текст, который написан на этом изображении. Верни только текст без комментариев."
- Полученный текст объединить с Tesseract

⚠️ **Важно:** это следует делать ТОЛЬКО если Tesseract даёт <50% качество. Tesseract быстрее и бесплатный.