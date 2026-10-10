#!/usr/bin/env bash
#
# Builds the embed with the key in .env.embed and uploads it to the dev asset
# host, as a store's embed is served there:
#
#   /sites/<host>/<hash>.js  immutable, never overwritten
#   /sites/<host>.js         the current one, no-cache, so a page that carries
#                            this URL picks up the next upload on its next load
#
# The key in .env.embed is not the extension's: its allowed origins are every
# origin the embed runs on (https://*.qween.com). Usage: ./publish-embed.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
SITE="qween.com"
BUCKET="gs://voqal-cloud-dev-avatar-host-asia-south1"
HOST="https://cdn.dev.voqalize.com"
ACCOUNT="sripathi@recruit41.com"

[[ -f "$here/.env.embed" ]] || { echo "no .env.embed (see README)" >&2; exit 1; }
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
(cd "$here" && pnpm exec tsc --noEmit && VOQALIZE_ENV_FILE="$here/.env.embed" VOQALIZE_OUT_DIR="$out" node build.mjs)

file="$out/embed/qween-trisha.js"
hash=$(shasum -a 256 "$file" | cut -c1-10)
gcs() { gcloud --account="$ACCOUNT" storage cp "$file" "$@" --content-type=text/javascript; }
gcs "$BUCKET/sites/$SITE/$hash.js" --no-clobber --cache-control="public, max-age=31536000, immutable"
gcs "$BUCKET/sites/$SITE.js" --cache-control="no-cache"
echo "$HOST/sites/$SITE/$hash.js"
echo "$HOST/sites/$SITE.js"
