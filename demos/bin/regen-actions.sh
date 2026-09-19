#!/usr/bin/env bash
#
# Regenerate every demo's `frontend/src/actions.gen.ts` from its brain.
#
# The list of demos is the set of files themselves, and each one names the brain
# it came from on its first line — so adding a demo needs nothing here, and a
# demo whose brain moved regenerates from wherever it moved to. Run from
# `demos/`; CI runs this and then `git diff --exit-code`, so a drifted file
# fails the build rather than the screen.
set -euo pipefail

cd "$(dirname "$0")/.."

for out in */frontend/src/actions.gen.ts; do
  src=$(sed -n '1s|^// Generated from \(.*\) by `voqalize types`.*|\1|p' "$out")
  if [ -z "$src" ]; then
    echo "::error::$out has no source line — regenerate it by hand" >&2
    exit 1
  fi
  # The source line is whatever path `voqalize types` was handed, so running it
  # from the repo root instead of here writes a `demos/`-prefixed path that only
  # resolves from where it was run. Say that, rather than letting the tool report
  # a missing file nobody expected to be missing.
  if [ ! -f "$src" ]; then
    echo "::error::$out names $src, which does not exist under demos/." >&2
    echo "::error::Paths on that line are relative to demos/ — rerun from here." >&2
    exit 1
  fi
  uv run voqalize types "$src" -o "$out"
done
