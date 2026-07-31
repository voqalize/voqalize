#!/usr/bin/env bash
# demos/bin/brains-node-deploy.sh — roll the demo-brains container onto ONE node.
#
# The single unit demos/cloudbuild.brains-vm.yaml invokes (once per host). Same
# idiom as vql-speech's bin/node-deploy.sh — ship config, pin the image, replace,
# health-gate, prune — with two deliberate divergences, both because this node is
# the *pygato voice node* and not a dedicated app box:
#
#   1. The node holds NO durable GCP credential. vql-speech keeps an
#      artifactregistry.reader SA JSON key on disk; pygato's node invariant is
#      "the node never authenticates to GCP" (voqalcloud
#      backend/pygato/deploy/README.md). So the pull uses an EPHEMERAL
#      `oauth2accesstoken` minted from the *build* SA, piped over stdin, and
#      `docker logout` wipes it from ~/.docker/config.json before we exit. The
#      token lives ~1h and never touches the disk of a public-facing VM.
#
#   2. Plain `docker run`, not `docker compose`. The node installs Ubuntu's
#      `docker.io`, which ships no compose plugin, and one container needs no
#      orchestrator. The resource caps below are therefore run flags rather than
#      compose keys — same values, one less moving part.
#
# Secrets: composed here from Secret Manager with the BUILD SA's creds and
# scp'd — never baked into the image, never persisted anywhere but the node's
# 0600 /etc/voqalize-brains/secrets.env. Every value is base64-encoded and
# single-line because Docker's --env-file is one-KEY=value-per-LINE and cannot
# carry a PEM; demos/docker-entrypoint.sh decodes FOO_B64 -> FOO in-container.
# Rotation = new GSM version + re-run this build.
#
# Usage:
#   demos/bin/brains-node-deploy.sh <host> <port> <image> <ssh_key> <project> <region>
#
#   host     the pygato node, e.g. 216.48.186.236
#   port     loopback port Caddy reverse-proxies to, e.g. 8091
#   image    full AR ref pinned to an immutable tag (…/demos:<short_sha>)
#   ssh_key  path to the brains deploy private key (GSM brains-deploy-ssh-key)
#   project  GCP project holding the runtime secrets, e.g. voqal-cloud-dev
#   region   AR region, e.g. asia-south1
#
# SSHes as `brains` — a distinct, independently revocable identity from pygato's
# root deploy key. It is in the `docker` group, which is trivially escalatable to
# root: this is a blast-radius/audit boundary between the two pipelines, NOT a
# security boundary. Say so out loud rather than implying otherwise.

set -euo pipefail

die() { echo "✗ $*" >&2; exit 1; }
info() { echo "→ $*"; }

[[ $# -eq 6 ]] || die "usage: $0 <host> <port> <image> <ssh_key> <project> <region>"

HOST="$1" PORT="$2" IMAGE="$3" SSH_KEY="$4" PROJECT="$5" REGION="$6"

CONTAINER=voqalize-brains
ETC_DIR=/etc/voqalize-brains
REGISTRY="https://${REGION}-docker.pkg.dev"

SSH=(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 "brains@${HOST}")

info "=== brains-node-deploy: ${HOST} <- ${IMAGE} ==="

# --- 1. Compose + ship secrets.env (base64, one line per value). --------------
# Read with the build SA's ambient creds; the node never calls Secret Manager.
b64() { printf '%s' "$1" | base64 | tr -d '\n'; }

fetch_secret() {
	gcloud secrets versions access latest --secret="$1" --project="$PROJECT" \
		|| die "cannot read secret $1 in $PROJECT"
}

GEMINI_API_KEY="$(fetch_secret gemini-api-key)"
# The dev/prod PyGato RS256 signer(s) this brain verifies session tokens against.
# REQUIRED in dev: dev and prod sign with different keys and the SDK's embedded
# fallback is the PROD signer only, so a dev deploy without this closes every
# session 4000.
VOQALIZE_BRAIN_PUBKEYS="$(fetch_secret controlplane-pygato-pubkeys)"

[[ -n "$GEMINI_API_KEY" ]] || die "gemini-api-key resolved empty"
[[ "$VOQALIZE_BRAIN_PUBKEYS" == *"BEGIN PUBLIC KEY"* ]] \
	|| die "controlplane-pygato-pubkeys does not look like a PEM bundle"

{
	printf 'GEMINI_API_KEY_B64=%s\n' "$(b64 "$GEMINI_API_KEY")"
	printf 'VOQALIZE_BRAIN_PUBKEYS_B64=%s\n' "$(b64 "$VOQALIZE_BRAIN_PUBKEYS")"
} | "${SSH[@]}" "umask 077 && cat > ${ETC_DIR}/secrets.env && chmod 600 ${ETC_DIR}/secrets.env"
info "secrets.env written (${ETC_DIR}/secrets.env, 0600, base64 values)"

# --- 2. Pull with an EPHEMERAL registry token (nothing durable left behind). ---
registry_logout() { "${SSH[@]}" "docker logout ${REGISTRY} >/dev/null 2>&1 || true" || true; }

gcloud auth print-access-token \
	| "${SSH[@]}" "docker login -u oauth2accesstoken --password-stdin ${REGISTRY}" >/dev/null
trap registry_logout EXIT

"${SSH[@]}" "docker pull '${IMAGE}'" || die "docker pull failed on ${HOST}"
info "image pulled"

# --- 3. Replace the container. --------------------------------------------
# Caps exist because this box is the voice node: pygato is latency- and
# loss-sensitive, so the brains must be *physically unable* to starve it.
#   --cpus 1.0            hard 25%-of-box ceiling (4 vCPU); a runaway demo brain
#                         still leaves 3 cores for pygato's sessions.
#   --cpu-shares 256      soft backstop for the other 75%. Docker maps shares to
#                         cgroup v2 cpu.weight (2..262144 -> 1..10000), so 256 is
#                         weight ~10 against pygato.service's systemd default
#                         CPUWeight=100: under contention pygato wins ~10:1
#                         before the hard cap is even reached.
#   --memory 1g           2x the Cloud Run limit this same image runs fine on. An
#                         OOM at 1g is a leak to find, not a limit to raise.
#   --memory-swap 1g      == memory ⇒ swap disabled for the container, so a brains
#                         leak can never induce swap thrash into pygato's jitter
#                         budget. (The box has no swap today; this makes it
#                         explicit rather than incidental.)
#   --pids-limit 512      fork-bomb guard; the app is one uvicorn process.
#   --log-driver journald container recreate deletes json-file logs, but journald
#                         indexes by tag, so `journalctl CONTAINER_TAG=…` survives
#                         redeploys — and the box's Grafana Alloy already tails
#                         journald, so container logs reach Loki with zero new
#                         plumbing. Strictly better than the Cloud Run logs it
#                         replaces.
#   -p 127.0.0.1:8091     loopback ONLY. Caddy is the sole public TCP listener.
#
# `docker run` is not zero-downtime the way a Cloud Run revision was: this kills
# in-flight demo sessions. That is accepted collateral for demos; --stop-timeout
# softens it. If it ever stops being acceptable the fix is two containers
# blue/green behind a Caddy upstream swap, not a longer grace period.
"${SSH[@]}" "docker rm -f ${CONTAINER} >/dev/null 2>&1 || true"
"${SSH[@]}" "docker run -d \
	--name ${CONTAINER} \
	--restart unless-stopped \
	--cpus 1.0 \
	--cpu-shares 256 \
	--memory 1g \
	--memory-swap 1g \
	--memory-reservation 512m \
	--pids-limit 512 \
	--stop-timeout 30 \
	--log-driver journald \
	--log-opt tag=${CONTAINER} \
	-p 127.0.0.1:${PORT}:8080 \
	--env-file ${ETC_DIR}/secrets.env \
	-e PORT=8080 \
	'${IMAGE}'" >/dev/null
info "container started"

# --- 4. Health-gate on loopback. ------------------------------------------
"${SSH[@]}" "curl -fsS --retry 60 --retry-delay 2 --retry-all-errors --retry-connrefused \
	http://127.0.0.1:${PORT}/_healthz" \
	|| die "brains never became healthy on ${HOST} — container left up for inspection (docker logs ${CONTAINER})"

# The PEM round-trip is the one thing a 200 does NOT prove: the app starts fine
# with zero pubkeys and only fails later, per session, with close 4000.
#
# Read PID 1's environ, NOT `docker exec printenv`: exec builds a fresh
# environment from the container's *configured* env (image + -e + --env-file), so
# it shows the _B64 var and never the decoded one — the decode happens in the
# entrypoint's own process, and `exec "$@"` carries it into PID 1 and only there.
# (An earlier version of this check asserted on `docker exec printenv` and failed
# a perfectly good deploy.)
PEM_PROBE='tr "\0" "\n" < /proc/1/environ | grep -m1 "^VOQALIZE_BRAIN_PUBKEYS=" | cut -c1-49'
PEM_HEAD="$("${SSH[@]}" "docker exec ${CONTAINER} sh -c '${PEM_PROBE}'" || true)"
[[ "$PEM_HEAD" == "VOQALIZE_BRAIN_PUBKEYS=-----BEGIN PUBLIC KEY-----" ]] \
	|| die "VOQALIZE_BRAIN_PUBKEYS did not survive into the container (got: '${PEM_HEAD}') — every session would close 4000"
info "pubkey round-trip OK"

# --- 5. Reclaim disk (running containers pin their own image). --------------
"${SSH[@]}" "docker image prune -af >/dev/null 2>&1 || true"

info "✓ ${HOST} done"
