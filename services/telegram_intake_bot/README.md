# Telegram Intake Bot v0.1

Shared Telegram runtime for DETOXIMAN intake flows.

Implemented for `TASK-A009` (`TB-A009-001...005`):

- One shared entrypoint/router for `/task`, reserved `/seed`, `/cancel`, and unknown input.
- Chat-level active session guard: cannot start `/seed` over active `/task`.
- Full `/task` flow with multi-fragment session, buttons `Продолжить` / `Отправить` / `Отменить`.
- `/seed` uses the same active session buttons for text/voice material: material fragments are collected until `Отправить`, then comment fragments are collected until final `Отправить`.
- `/seed` queues detected external URLs under `Inbox/YYYY/links/` for local processing; it does not create full/slim Seed Markdown or a Google Sheet row at queue time.
- External URLs shared directly to the bot without an active `/seed` session are routed into the same link queue.
- Task Intake markdown writer to `/Inbox/` locally or GitHub in Cloud Run with minimal contract:
  - `status: new`
  - `# Вход Павла`
  - collected task body
- Voice fragment support via shared transcription adapter interface (`mock` by default, optional `google` live provider).
- `/seed` can use env-driven Seed storage and link queue storage: local filesystem for tests or GitHub Contents API for Cloud Run.
- Main Telegram keyboard labels: `Дать задачу`, `Записать seed`, `Завершить сессию`.

## Quickstart

```bash
cd services/telegram_intake_bot
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
TMP_DIR="$(mktemp -d)"
TASK_INBOX_DIR="$TMP_DIR" PYTHONPATH=src python3 -m telegram_intake_bot.cli mock --updates-file tests/fixtures/mock_updates_task_intake_e2e.json
ls -1 "$TMP_DIR"
```

## Optional polling smoke-check

When token is configured in local env (never commit it), load it from a local `.env`
or another protected shell environment:

```bash
cd services/telegram_intake_bot
set -a
source .env
set +a
PYTHONPATH=src python3 -m telegram_intake_bot.cli diagnose
PYTHONPATH=src python3 -m telegram_intake_bot.cli polling
```

Stop with Ctrl+C.

If `diagnose` reports `webhook_url_set=yes` and the chosen local mode is polling,
clear the webhook before polling:

```bash
PYTHONPATH=src python3 -m telegram_intake_bot.cli delete-webhook
```

If token is not configured, polling mode exits with:

`TELEGRAM_BOT_TOKEN is not set. Use mock mode or configure local env.`

## Cloud Run webhook mode

Cloud Run runs the bot as an HTTP webhook service:

```bash
cd services/telegram_intake_bot
PYTHONPATH=src:../seed_pipeline/src python3 -m telegram_intake_bot.cli webhook
```

The server listens on `$PORT` and exposes:

- `GET /healthz` - readiness check.
- `POST /telegram/webhook` - Telegram update webhook by default.

After deployment, register the public URL with Telegram from a protected shell:

```bash
PYTHONPATH=src python3 -m telegram_intake_bot.cli set-webhook \
  --url https://cloud-run-url/telegram/webhook
```

Use `TELEGRAM_WEBHOOK_SECRET` to set Telegram's webhook secret token. The value
is never printed; diagnostics only show whether it is configured.

## Optional Google transcription smoke-check

For live voice transcription, configure only protected local env values:

```bash
cd services/telegram_intake_bot
set -a
source .env
set +a
TRANSCRIPTION_PROVIDER=google PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python3 -m telegram_intake_bot.cli polling
```

Then send a short voice message to `/task` or `/seed` in the allowlisted chat.
The provider downloads Telegram voice bytes via `TELEGRAM_BOT_TOKEN` and sends
them to Google Cloud Speech-to-Text using `GOOGLE_APPLICATION_CREDENTIALS`.

## Environment variables

- `TELEGRAM_BOT_TOKEN` - required only for live polling mode.
- `TELEGRAM_ALLOWED_USER_IDS` - optional CSV allowlist for live mode.
- `TELEGRAM_POLL_TIMEOUT_SECONDS` - optional polling timeout (default `25`).
- `PORT` - HTTP port for Cloud Run webhook mode, set by Cloud Run.
- `TELEGRAM_WEBHOOK_PATH` - optional webhook path, defaults to `/telegram/webhook`.
- `TELEGRAM_WEBHOOK_SECRET` - optional webhook secret token checked against Telegram's header.
- `TASK_MARKDOWN_STORAGE` - optional, `local` by default; set `github` for Cloud Run Task Intake writes.
- `SEED_MARKDOWN_STORAGE` - optional, `local` by default; set `github` for Cloud Run Seed writes.
- `LINK_QUEUE_STORAGE` - optional override for URL queue writes; defaults to `SEED_MARKDOWN_STORAGE`.
- `SEED_GOOGLE_WORKSPACE` - optional, `mock` by default; set `live` for Google Sheet registry writes.
- `GITHUB_TOKEN` - required only for GitHub-backed task, seed, or link queue writes.
- `GITHUB_REPOSITORY` - optional for GitHub storage, defaults to `detoximan/seedintake`.
- `GITHUB_BRANCH` - optional for GitHub storage, defaults to `main`.
- `TRANSCRIPTION_PROVIDER` - optional, defaults to `mock`; set `google` for Google Cloud Speech-to-Text.
- `GOOGLE_APPLICATION_CREDENTIALS` - required only for `TRANSCRIPTION_PROVIDER=google`.
- `TRANSCRIPTION_LANGUAGE_CODE` - optional for Google transcription, defaults to `ru-RU`.
- `TRANSCRIPTION_SAMPLE_RATE_HERTZ` - optional positive integer for Google transcription.
- `TRANSCRIPTION_MODEL` - optional Google Speech model name.
- `TASK_INBOX_DIR` - optional override for Task Intake output directory (useful for smoke-check).

## Security notes

- Do not commit `.env`, bot tokens, Google credentials, audio files, transcripts, or Telegram payload dumps.
- Runtime logs belong to `/runtime/logs/telegram_intake_bot/` (gitignored by root `.gitignore`).
