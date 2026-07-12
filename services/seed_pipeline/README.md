# Seed Pipeline v0.1

Technical home for the Seed Pipeline implementation.

Canonical scaffold:

- `/architecture/seed_pipeline_scaffold.md`

Controlling contracts:

- `/architecture/system_contracts.md`
- `/architecture/error_contract.md`
- `/architecture/test_case_standard.md`
- `/decisions/ADR-001-seed-storage-v0.1.md`
- `/decisions/ADR-004-firestore-later-publication-queue.md`
- `/decisions/ADR-006-shared-telegram-intake-bot-v0.1.md`
- `/test_cases/seed_intake/`

Status after the `TB-A002-007` plan change:

- Minimal Python package is present.
- Local dry-run CLI is implemented.
- Dry-run builds a Seed payload preview and writes a report only to ignored runtime tmp.
- Seed ID allocation, minimal Markdown Seed writer and basic `telegram_message_id` dedup are implemented.
- Mock Google Sheets adapter is implemented for local smoke checks.
- Dry-run builds a full Markdown Seed path, a slim Markdown Seed path, and a synthetic Sheet registry row linking to the full GitHub URL.
- Mock orchestration can create the full local chain in temp/test contexts:
  SeedInput -> full Markdown -> slim Markdown -> mock Sheet row.
- Live Google Sheets adapter is implemented behind the same orchestration contract.
- Live smoke is opt-in via `--live-google` and requires protected local env vars.
- GitHub Contents API storage is implemented for Cloud Run via `SEED_MARKDOWN_STORAGE=github`.
- Local Seed Link Worker scaffold is implemented for queue items in `/Inbox/YYYY/links/`.
- Full Markdown Seed links to the slim Markdown Seed in the `# Оригинал` section.
- Real Google credentials, `.env`, service account JSON, runtime logs and live payloads must stay out of Git.
- Live transcription is not part of this service step.
- Telegram runtime is shared with `TASK-A009` in `/services/telegram_intake_bot/`; Seed Pipeline must not create a separate Telegram bot runtime.

## Local dry-run

From this folder:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python3 -m seed_pipeline.cli smoke --case ../../test_cases/seed_intake/text_seed_input.md --dry-run
```

Manual synthetic input:

```bash
PYTHONPATH=src python3 -m seed_pipeline.cli smoke \
  --dry-run \
  --material "Synthetic source material" \
  --comment "Synthetic Pavel comment"
```

Dry-run does not create files in `/Inbox/`.

Mock Google partial failure check:

```bash
PYTHONPATH=src python3 -m seed_pipeline.cli smoke \
  --case ../../test_cases/seed_intake/text_seed_input.md \
  --dry-run \
  --mock-google-fail-step google_sheets
```

This writes a dry-run report with the planned GitHub full/slim URLs and a manual action.
It does not create final Markdown files in dry-run mode.

The mock orchestrator is covered by unit tests. It creates both Markdown files
atomically, writes the Sheet row with a link to the full Markdown file, and
rolls back the Markdown files if the Sheet append fails.

## Live Google Sheets smoke

Required protected local env vars:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
GOOGLE_SHEET_ID=google-sheet-id
```

The service account must have edit access to the Google Sheet registry.

Run from this folder only after those values are available in the local shell:

```bash
PYTHONPATH=src python3 -m seed_pipeline.cli smoke \
  --case ../../test_cases/seed_intake/text_seed_input.md \
  --live-google
```

The live command creates both Markdown files locally, appends a Google Sheet row
with a hyperlink to the full GitHub file, and records the processed Telegram
message only after the Sheet append succeeds.

The Markdown writer is implemented as a package component for the next integration
steps. It is covered by tests and writes final Seed markdown only when called by
orchestration code.

## GitHub API storage for Cloud Run

Cloud Run must not rely on local filesystem writes for final Seed artifacts.
Use GitHub storage only through protected env vars:

```bash
SEED_MARKDOWN_STORAGE=github
GITHUB_TOKEN=github-token-with-contents-write
GITHUB_REPOSITORY=pashamal/seedintake
GITHUB_BRANCH=main
GITHUB_SEED_BASE_URL=https://github.com/pashamal/seedintake/blob/main
```

For the Cloud Run text `/seed` path, combine it with live Google Sheet registry:

```bash
SEED_GOOGLE_WORKSPACE=live
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
GOOGLE_SHEET_ID=google-sheet-id
```

The text path does not require `TRANSCRIPTION_PROVIDER=google`. Voice
transcription is a later smoke-check and must not block text Seed intake.

Do not store `.env`, tokens, Google credentials, runtime logs, or real Telegram user data in this folder.

## Local Seed Link Worker

The Telegram bot writes shared URLs to local/GitHub queue items:

```text
Inbox/YYYY/links/YYYY-MM-DD-NNN-link.md
```

The local worker reads `status: new` queue items and can process one file or a
limited batch. `youtube_shorts` items are processed locally with `yt-dlp`,
temporary compact audio, and Groq Speech-to-Text. TikTok/Reels/text post
processors are separate follow-up tasks.

From this folder:

```bash
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker list
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --limit 1
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file ../../Inbox/2026/links/2026-04-30-001-link.md
PYTHONPATH=src python3 -m seed_pipeline.cli link-worker process --file ../../Inbox/2026/links/2026-04-30-001-link.md --fake-processor
```

If the package is installed locally, the dedicated entry point is also available:

```bash
seed-link-worker list
seed-link-worker process --limit 1
seed-link-worker process --file Inbox/2026/links/2026-04-30-001-link.md
seed-link-worker process --file Inbox/2026/links/2026-04-30-001-link.md --fake-processor
```

Success rewrites the queue item to `status: processed` and adds
`processed_seed_id`, `processed_seed_path` and `processed_at`. Failure rewrites
the queue item to `status: failed` with a short `failure_reason` and `failed_at`.

By default the worker uses local Markdown storage and mock Google Workspace. To
append a live Google Sheet row, run with `--live-google` after protected Google
env vars are available in the shell. Do not use live mode for synthetic queue
items unless the created registry row is expected.

YouTube Shorts processing requires local protected env and binaries:

```bash
export GROQ_API_KEY=...
export GROQ_STT_MODEL=whisper-large-v3-turbo
yt-dlp --version
ffmpeg -version
ffprobe -version
```

Optional env:

- `YT_DLP_BIN` - custom `yt-dlp` executable path.
- `LINK_WORKER_AUDIO_FORMAT` - defaults to `mp3`.
- `LINK_WORKER_AUDIO_QUALITY` - defaults to `64K`.
- `GROQ_STT_LANGUAGE` - optional language hint.

Temporary media/audio is created under the OS temp directory and deleted after
success or failure. The repository should only receive the resulting Seed
Markdown, queue status update, and optional Google Sheet row.
