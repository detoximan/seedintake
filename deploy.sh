#!/bin/bash
set -euo pipefail

# ============================================================
# SeedIntake Cloud Run Deploy
# ============================================================
# Регион: europe-west4 (Amsterdam) — тот же что micro-razbor-bot
# Проект: detoximan2026
# Сервис: seedintake-telegram-bot (ОТДЕЛЬНЫЙ от micro-razbor-bot!)
#
# Секреты (TELEGRAM_BOT_TOKEN, GITHUB_TOKEN, GROQ_API_KEY)
# передаются через Secret Manager, привязка — вручную через Console
# или gcloud (см. комментарий внизу).
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/services/telegram_intake_bot/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found at $ENV_FILE" >&2
  exit 1
fi

# Читаем .env, пропускаем секреты (они через Secret Manager)
ENV_VARS=""
while IFS='=' read -r key value || [[ -n "$key" ]]; do
  [[ -z "$key" || "$key" == \#* ]] && continue
  key=$(echo "$key" | xargs)
  case "$key" in
    TELEGRAM_BOT_TOKEN|GITHUB_TOKEN|GROQ_API_KEY)
      continue
      ;;
  esac
  value=$(echo "$value" | xargs)
  [[ -z "$key" ]] && continue
  if [[ -z "$ENV_VARS" ]]; then
    ENV_VARS="$key=$value"
  else
    ENV_VARS="$ENV_VARS,$key=$value"
  fi
done < "$ENV_FILE"

# Seed Pipeline переменные (не секреты)
EXTRA_VARS="SEED_MARKDOWN_STORAGE=github"
EXTRA_VARS="$EXTRA_VARS,SEED_GOOGLE_WORKSPACE=live"
EXTRA_VARS="$EXTRA_VARS,GITHUB_REPOSITORY=detoximan/seedintake"
EXTRA_VARS="$EXTRA_VARS,GITHUB_BRANCH=main"
EXTRA_VARS="$EXTRA_VARS,GITHUB_SEED_BASE_URL=https://github.com/detoximan/seedintake/blob/main"
EXTRA_VARS="$EXTRA_VARS,SEED_DEBUG=1"

if [[ -n "$ENV_VARS" ]]; then
  ENV_VARS="$ENV_VARS,$EXTRA_VARS"
else
  ENV_VARS="$EXTRA_VARS"
fi

echo "============================================"
echo " SeedIntake Cloud Run Deploy"
echo "============================================"
echo " Region:  europe-west4 (Amsterdam)"
echo " Project: detoximan2026"
echo " Service: seedintake-telegram-bot"
echo " Source:  $SCRIPT_DIR"
echo " Repo:    detoximan/seedintake"
echo "============================================"
echo ""
echo "IMPORTANT: micro-razbor-bot НЕ затрагивается!"
echo ""

cd "$SCRIPT_DIR"
gcloud run deploy seedintake-telegram-bot \
  --source . \
  --region europe-west4 \
  --project detoximan2026 \
  --allow-unauthenticated \
  --update-env-vars "$ENV_VARS" \
  --quiet

echo ""
echo "============================================"
echo " Deploy complete!"
echo "============================================"
echo ""
echo "Следующие шаги:"
echo ""
echo "1. Привязать секреты (если ещё не привязаны):"
echo ""
echo "   gcloud run services update seedintake-telegram-bot \\