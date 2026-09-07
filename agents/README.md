# База знаний агента (Agent Knowledge Base)

Эта папка содержит специализированные регламенты, промпты, инструкции и архитектурные описания, необходимые для автономной и качественной работы LLM-агента в репозитории `SeedIntake`.

---

## 📚 Каталог материалов

| Файл | Описание | Когда применять |
|---|---|---|
| [prompt_video_ocr_hybrid.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/prompt_video_ocr_hybrid.md) | Архитектура и промпт гибридного извлечения контента (Whisper + кадры OCR) | При доработке или отладке извлечения контента из видео без голоса |
| [carousel_translation_guideline.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/carousel_translation_guideline.md) | Регламент по-слайдового перевода каруселей 1-в-1 | При переводе каруселей Instagram / TikTok и синхронизации |
| [cookies_management.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/cookies_management.md) | Руководство по cookies: формат, пути, частота обновления, решение блокировок | При возникновении ошибок доступа к Instagram, TikTok, Facebook |
| [troubleshooting.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/agents/troubleshooting.md) | Справочник по устранению типовых ошибок и сбоев пайплайна | При падении воркеров, рассинхроне с Google Sheets или обнаружении дублей |

---

## 🧭 Связь с общей архитектурой

- Главная точка входа для агента: [AGENTS.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/AGENTS.md)
- Индекс всех утилит и файлов проекта: [index.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/index.md)
- Хронологический журнал событий: [log.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/log.md)
- Концепция LLM Wiki Андрея Карпаты: [3_karpathy-idea.md](file:///Users/pavelmalyk/pm_developer/SeedIntake/3_karpathy-idea.md)
