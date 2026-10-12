#!/usr/bin/env bash
#
# Builds the embed with the environment's embed key and uploads it to that
# environment's asset host, as a store's embed is served there:
#
#   /sites/<host>/<hash>.js  immutable, never overwritten
#   /sites/<host>.js         the current one, no-cache, so a page that carries
#                            this URL picks up the next upload on its next load
#
# The key is not the extension's: its allowed origins are every origin the
# embed runs on (https://*.qween.com, https://shop.qweendom.in). Dev reads it
# from .env.embed, prod from .env.embed.prod. Usage: ./publish-embed.sh [dev|prod]
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
SITE="qween.com"
ACCOUNT="sripathi@recruit41.com"
case "${1:-dev}" in
  dev) ENV_FILE="$here/.env.embed"; BUCKET="gs://voqal-cloud-dev-avatar-host-asia-south1"; HOST="https://cdn.dev.voqalize.com"
       RUNTIME="https://avatar.dev.voqalize.com/runtime/current.js" ;;
  prod) ENV_FILE="$here/.env.embed.prod"; BUCKET="gs://voqal-cloud-prod-avatar-host-asia-south1"; HOST="https://cdn.voqalize.com"
       RUNTIME="" ;;
  *) echo "usage: $0 [dev|prod]" >&2; exit 2 ;;
esac

[[ -f "$ENV_FILE" ]] || { echo "no $(basename "$ENV_FILE") (see README)" >&2; exit 1; }
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
(cd "$here" && pnpm exec tsc --noEmit && AVATAR_RUNTIME="$RUNTIME" VOQALIZE_ENV_FILE="$ENV_FILE" VOQALIZE_OUT_DIR="$out" node build.mjs)

file="$out/embed/qween-trisha.js"
hash=$(shasum -a 256 "$file" | cut -c1-10)
gcs() { gcloud --account="$ACCOUNT" storage cp "$file" "$@" --content-type=text/javascript; }
gcs "$BUCKET/sites/$SITE/$hash.js" --no-clobber --cache-control="public, max-age=31536000, immutable"
gcs "$BUCKET/sites/$SITE.js" --cache-control="no-cache"
echo "$HOST/sites/$SITE/$hash.js"
echo "$HOST/sites/$SITE.js"
