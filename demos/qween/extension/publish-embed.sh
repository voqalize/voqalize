#!/usr/bin/env bash
#
# Builds the embed with the environment's embed key and uploads it to that
# environment's asset host, as a store's embed is served there:
#
#   /sites/<host>/<hash>.js  immutable, never overwritten
#   /sites/<host>.js         the current one, no-cache, so a page that carries
#                            this URL picks up the next upload on its next load
#
# It then builds the Chrome extension from the same tree, with the extension's
# own key (.env for prod, .env.dev for dev), and uploads it as a zip beside it:
#
#   /sites/<host>/extension/<hash>.zip  immutable, never overwritten
#   /sites/<host>/extension.zip         the current one, no-cache: the link we hand out
#
# Both go up together on purpose. The extension is handed out by that link, so
# an embed published without it would leave the extension on the old build.
#
# The key is not the extension's: its allowed origins are every origin the
# embed runs on (https://*.qween.com, https://shop.qweendom.in). Prod reads it
# from .env.embed, dev from .env.embed.dev. Usage: ./publish-embed.sh prod|dev
#
# The target has no default: a bare run used to publish dev, and a bare run that
# published prod would put a build in front of Qween's shoppers by accident.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
SITE="qween.com"
ACCOUNT="sripathi@recruit41.com"
case "${1:-}" in
  dev) ENV_FILE="$here/.env.embed.dev"; EXT_ENV_FILE="$here/.env.dev"; BUCKET="gs://voqal-cloud-dev-avatar-host-asia-south1"; HOST="https://cdn.dev.voqalize.com"
       RUNTIME="https://cdn.dev.voqalize.com/runtime/current.js" ;;
  prod) ENV_FILE="$here/.env.embed"; EXT_ENV_FILE="$here/.env"; BUCKET="gs://voqal-cloud-prod-avatar-host-asia-south1"; HOST="https://cdn.voqalize.com"
       RUNTIME="" ;;
  *) echo "usage: $0 prod|dev" >&2; exit 2 ;;
esac

for f in "$ENV_FILE" "$EXT_ENV_FILE"; do
  [[ -f "$f" ]] || { echo "no $(basename "$f") (see README)" >&2; exit 1; }
done
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

# The extension: the unpacked build's files, zipped with fixed times and no
# extra attributes so the same build gives the same zip and the same hash.
ext="$out/extension"
(cd "$here" && AVATAR_RUNTIME="$RUNTIME" VOQALIZE_ENV_FILE="$EXT_ENV_FILE" VOQALIZE_OUT_DIR="$ext" node build.mjs)
rm -rf "$ext/embed"
find "$ext" -exec touch -t 200001010000 {} +
zipfile="$out/extension.zip"
(cd "$ext" && zip -q -X -r "$zipfile" content.js manifest.json README.md)
zhash=$(shasum -a 256 "$zipfile" | cut -c1-10)
zcp() { gcloud --account="$ACCOUNT" storage cp "$zipfile" "$@" --content-type=application/zip; }
zcp "$BUCKET/sites/$SITE/extension/$zhash.zip" --no-clobber --cache-control="public, max-age=31536000, immutable"
zcp "$BUCKET/sites/$SITE/extension.zip" --cache-control="no-cache"
echo "$HOST/sites/$SITE/extension/$zhash.zip"
echo "$HOST/sites/$SITE/extension.zip"
