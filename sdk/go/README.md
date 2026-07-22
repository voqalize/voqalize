# Agent SDK (Go)

The **native, pipecat-free** Go agent SDK for the Voqalize voice AI platform.

`you bring the brain, we bring the voice` — here the brain is Go.

A Go agent peer talks the wire protocol directly (`wire/` + protobuf), so it needs
no pipecat. It speaks the same `Vql*` wire frames as the Python SDK — a concrete
subset of the Voice Protocol. Two transports, one per-session engine and one
`Vql*` vocabulary — the only difference is who dials whom:

- **Direct (primary):** an inbound WS *server* (`DirectServer` / `NewDirectServer`).
  PyGato dials `{brain_url}/s/{session_id}` per session, one socket per session,
  bare `[1-byte direction][protobuf]` framing (no session prefix), optional RS256
  token verification against Voqalize's public key.
- **Cortex (optional fallback):** one outbound multiplexed WS to `/agent`
  (`Agent`), demuxed per session by a `[16-byte session_id][1-byte direction][protobuf]`
  prefix — for brains that can't accept inbound (serverless, laptops, egress-only
  networks).

A brain written for one transport runs on the other unchanged.

## Modules

This directory is split into two Go modules so the core library stays lean —
the core has **no** `genai` / google-cloud dependency:

- **Core** — `github.com/voqalize/voqalize/sdk/go` (this directory): `brain/`,
  `cortex/`, `wire/`, `tests/`. Depends only on `coder/websocket`,
  `golang-jwt/jwt/v5`, `google/uuid`, and `google.golang.org/protobuf`.
- **Examples** — `github.com/voqalize/voqalize/sdk/go/examples`
  ([`examples/`](examples/)): the Gemini-backed travel demo brain plus dev-only
  run harnesses. Pulls the heavy `google.golang.org/genai` tree, so it is its own
  module (with a `replace` back onto the core), keeping that weight off every core
  consumer.

## Layout

Core (`github.com/voqalize/voqalize/sdk/go`):

- `wire/framespb/` — generated Go protobuf stubs (regenerate with `make proto`).
- `wire/codec.go` — typed Go frames ⇄ `Envelope` bytes (symmetric: encode + decode).
- `wire/wire.go` — `MultiplexedWire`: one outbound WebSocket to `/agent`,
  `[16-byte session_id][1-byte direction][protobuf]` framing, reconnect/backoff,
  close codes.
- `cortex/agent.go` — `Agent` (**optional Cortex-relay path**): one outbound
  multiplexed WS to `/agent`, demux per session, shared fair writer, ack-gating,
  reconnect teardown.
- `cortex/direct.go` — `DirectServer` / `NewDirectServer` (**primary path**): an
  inbound WS *server*; one `sessionRunner` per connection, dedicated per-connection
  writer, bare `[1-byte direction][protobuf]` framing, optional RS256 token
  verification. Reuses `sessionRunner` + `brain/` unchanged.
- `cortex/session.go` — per-session runner: two-lane (system/normal) buffers,
  drop-newest + `ErrorFrame`, interruption routing, the `Emitter`/`Session`/`SessionFactory`
  interfaces, and the `runnerHost` seam (the four methods `Agent` and `directConn`
  each implement so the *same* runner drives both transports).
- `brain/` — the ergonomic surface: `Brain` (required `OnInteraction`) + optional
  interfaces (`SessionStarter`, `InferenceFinalizer`, `AppEventHandler`,
  `ErrorHandler`), `Session`/`Interaction`/`Inference`, the framework-enforced
  heard-text `Conversation`, and the adapter that maps wire frames ↔ callbacks.
- `tests/` — end-to-end tests against a fake cortex over a real WebSocket:
  greeting, per-turn inference, ack-gating, the heard-text Conversation, barge-in,
  screen-driving (`ui_command`), browser→brain app events, and the direct-server
  transport.

Examples (`github.com/voqalize/voqalize/sdk/go/examples`):

- `travel/` — the TravelBrain (real Gemini via `google.golang.org/genai`),
  exercising the core concepts end to end.
- `cmd/travel-local/` — run the travel brain against a local Cortex relay
  (platform-JWT, pool `t:demo-tenant:voqal-travel`).
- `cmd/travel-direct/` — run the travel brain as an inbound DIRECT server — the
  Cortex-free path. PyGato dials the process straight at
  `ws://localhost:8788/s/{session_id}`.
- `tests/` — live Gemini screen-driving tests, gated on `GEMINI_API_KEY`
  (self-skip when unset).

The `cmd/*` harnesses are dev-only and assume a local stack / `.env`; they compile
standalone but are not meant to run outside a full dev environment.

## Core invariants (must match Cortex + PyGato)

- **Wire:** binary WebSocket. In `direct` mode (primary) each message is
  `[1-byte direction][Envelope]` (session in the URL); in `cortex` mode (fallback)
  it's `[16-byte session_id][1-byte direction][Envelope]`. The direction byte MUST
  match pipecat's `FrameDirection` enum (`DOWNSTREAM=1`, `UPSTREAM=2`). The agent
  sends everything `DOWNSTREAM` (1) — pygato relays `ui_command` UPSTREAM on its own read.
- **Ack-gating:** every inbound data frame with `request_id > 0` is acked **after**
  the frame is dispatched (pygato blocks on the ack). The agent's own frames carry
  no `request_id`.
- **Two lanes:** interruption/start/cancel ride the system (priority) lane; data
  rides the normal lane (bounded, drop-newest → non-fatal `ErrorFrame` to the
  brain). Acks never drop.
- **Interruption:** a `VqlInterruption` cancels in-flight callback goroutines
  (barge-in) and is echoed back as pygato's drain barrier.
- **Heard-text contract (framework-enforced):** the SDK commits the user utterance
  at interaction start and one assistant message per inference from its HEARD text
  at finalize, into `session.Conversation` — the brain keeps no parallel history
  and cannot commit generated text.
- **One Brain per session:** the factory runs per session; state on the Brain is
  session-scoped.

## Run / test

```bash
# Core (lean, no genai):
cd sdk/go
go build ./...
go vet ./...
go test ./...                 # wire + runtime + brain via a fake cortex over real TCP

# Examples (Gemini travel demo + dev harnesses):
cd sdk/go/examples
go build ./...
GEMINI_API_KEY=... go test ./tests/   # live Gemini travel screen-driving
go run ./cmd/travel-local             # live against a local stack
```

Regenerate protobuf stubs after editing `proto/`: `make proto` (repo root).
