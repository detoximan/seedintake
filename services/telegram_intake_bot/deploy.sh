#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PROJECT=detoximan2026
REGION=europe-west4
SERVICE=seedintake-telegram-bot
IMAGE="gcr.io/${PROJECT}/${SERVICE}"

echo "Building container image via Cloud Build..."
gcloud builds submit "$REPO_ROOT" \
  --config "$SCRIPT_DIR/cloudbuild.yaml" \
  --project "$PROJECT" \
  --substitutions "_IMAGE=$IMAGE"

echo "Deploying $SERVICE to Cloud Run..."
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "SEED_MARKDOWN_STORAGE=github,LINK_QUEUE_STORAGE=github,SEED_GOOGLE_WORKSPACE=live,GITHUB_REPOSITORY=detoximan/seedintake,GITHUB_BRANCH=main,GITHUB_SEED_BASE_URL=https://github.com/detoximan/seedintake/blob/main,TELEGRAM_WEBHOOK_PATH=/telegram/webhook,GOOGLE_APPLICATION_CREDENTIALS=/secrets/google/service-account.json,TRANSCRIPTION_PROVIDER=google,TRANSCRIPTION_LANGUAGE_CODE=ru-RU" \
  --set-secrets "TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,GITHUB_TOKEN=github-token:latest,TELEGRAM_WEBHOOK_SECRET=telegram-webhook-secret:latest,GOOGLE_SHEET_ID=google-sheet-id:latest,/secrets/google/service-account.json=google-service-account-json:latest" \
  --quiet

gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format="value(status.url)"
