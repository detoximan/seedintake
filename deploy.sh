#!/usr/bin/env bash
set -euo pipefail

PROJECT=detoximan2026
REGION=europe-west4
SERVICE=seedintake-telegram-bot

if [[ ! -f Dockerfile ]]; then
  echo "Run deploy.sh from the SeedIntake project root." >&2
  exit 1
fi

gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "SEED_MARKDOWN_STORAGE=github,LINK_QUEUE_STORAGE=github,SEED_GOOGLE_WORKSPACE=live,GITHUB_REPOSITORY=detoximan/seedintake,GITHUB_BRANCH=main,GITHUB_SEED_BASE_URL=https://github.com/detoximan/seedintake/blob/main,TELEGRAM_WEBHOOK_PATH=/telegram/webhook,GOOGLE_APPLICATION_CREDENTIALS=/secrets/google/service-account.json,TRANSCRIPTION_PROVIDER=google,TRANSCRIPTION_LANGUAGE_CODE=ru-RU" \
  --set-secrets "TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,GITHUB_TOKEN=github-token:latest,TELEGRAM_WEBHOOK_SECRET=telegram-webhook-secret:latest,GOOGLE_SHEET_ID=google-sheet-id:latest,/secrets/google/service-account.json=google-service-account-json:latest" \
  --quiet

gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format="value(status.url)"
