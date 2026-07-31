#!/bin/sh
# Expand base64-encoded secrets, then exec the real command.
#
# Why: the brains image runs two ways.
#
#   - Cloud Run, which hands multi-line values (the RS256 pubkey PEM bundle) to
#     the process natively. Nothing to do — this script is a no-op there.
#   - A Docker container on the pygato VM, where the deploy writes an
#     `--env-file`. Docker's env-file parser is strictly one KEY=value per LINE:
#     a multi-line PEM cannot survive it at all, and the escape-and-quote dance
#     that makes it survive *systemd's* EnvironmentFile parser (see
#     voqalcloud backend/pygato/deploy/deploy.py::_quote_escaped_values) does
#     NOT transfer — Docker and Compose each strip quotes differently, and both
#     differ from systemd. That mismatch is the classic "green deploy, every
#     session closes 4000" failure.
#
# So the VM path ships every secret base64-encoded and single-line
# (`VOQALIZE_BRAIN_PUBKEYS_B64`), which no env-file parser can mangle, and this
# entrypoint decodes `<NAME>_B64` back into `<NAME>` before the app reads the
# environment. The app itself stays parser-agnostic and unchanged.
#
# Generic by design: any FOO_B64 becomes FOO. `_` is not in the base64 alphabet,
# so a decoded PEM's own body can never look like another `FOO_B64=` assignment.
set -eu

for name in $(env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)_B64=.*$/\1/p'); do
	eval "encoded=\${${name}_B64}"
	decoded=$(printf '%s' "$encoded" | base64 -d)
	export "${name}=${decoded}"
	unset "${name}_B64"
	echo "entrypoint: decoded ${name}_B64 -> ${name} (${#decoded} bytes)" >&2
done

exec "$@"
