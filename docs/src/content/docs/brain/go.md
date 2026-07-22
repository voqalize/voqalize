---
title: Build a brain (Go)
description: The native Go brain SDK — implement the Brain interface, serve it inbound or over Cortex, no pipecat.
---

The Go SDK is native and pipecat-free — it speaks the wire protocol directly.
Import path: `github.com/voqalize/voqalize/sdk/go/...`. It mirrors the Python SDK
concept-for-concept; a brain written against one ports to the other.

The package splits three ways:

- **`wire/`** — the protobuf codec and multiplexed transport.
- **`cortex/`** — the per-session runtime: `Agent` (outbound), `DirectServer`
  (inbound), the session engine, and the `Emitter` / `Session` / `SessionFactory`
  types.
- **`brain/`** — the ergonomic Brain surface your code implements.

:::note[Pre-release]
The wire protocol is identical to the Python SDK, but the Go surface is younger —
see [SDK parity](#sdk-parity-notes) for the current gaps.
:::

## The Brain interface

Go uses a **required interface plus optional interfaces** (the runtime
type-asserts each optional one). Only `OnInteraction` is required:

```go
type Brain interface {
    OnInteraction(ctx context.Context, in *brain.Interaction) error
}
```

Implement any subset of the optional interfaces:

| Interface | Method |
|---|---|
| `SessionStarter` | `OnSessionStart(ctx, s *Session, start SessionStart) error` |
| `SessionEnder` | `OnSessionEnd(ctx, s *Session)` |
| `InferenceFinalizer` | `OnInferenceFinalized(ctx, inf *Inference)` |
| `AppEventHandler` | `OnAppEvent(ctx, s *Session, ev AppEvent)` |
| `ErrorHandler` | `OnError(ctx, s *Session, direction, message string)` |

Payload types: `SessionStart{Init map[string]any}`, `AppEvent{Name string; Data
map[string]any}`, `Outcome{ActionID, InteractionID uint64; Status string; Result
any}`, `Message{Role, Content string}`.

## Speaking

Speech uses an inference **closure** (Go's equivalent of Python's `async with`
bracket). One closure equals one model call:

```go
func (Greeter) OnSessionStart(ctx context.Context, s *brain.Session, _ brain.SessionStart) error {
    return s.Inference(ctx, func(inf *brain.Inference) error {
        return inf.Speak("Hi! How can I help?")     // agent-initiated (interaction 0)
    })
}

func (Greeter) OnInteraction(ctx context.Context, in *brain.Interaction) error {
    return in.Inference(ctx, func(inf *brain.Inference) error {
        return inf.Speak("You said: " + in.Transcript)
    })
}
```

`Inference.Speak(text string) error` streams a chunk (empty string is a no-op;
calling it outside a bracket errors). The runtime emits `VqlLLMStart` … `VqlLLMEnd`
around the closure, even on error or cancel.

## Session and Interaction

```go
type Session struct {
    ID           string
    Init         map[string]any
    Conversation *Conversation
    // ...
}
func (s *Session) Inference(ctx, fn func(*Inference) error) error
func (s *Session) ConfigureTTS(voice, language, model string)   // positional; "" = unchanged; next inference
func (s *Session) ConfigureSTT(cfg STTConfig)                   // applies live

type Interaction struct {
    ID         uint64
    Transcript string
    Session    *Session
    // ...
}
func (in *Interaction) Conversation() *Conversation
func (in *Interaction) Inference(ctx, fn func(*Inference) error) error
func (in *Interaction) Action(name string, args map[string]any) uint64
func (in *Interaction) ActionWithResult(name string, args map[string]any, cb func(Outcome)) uint64
```

`ConfigureSTT` takes an `STTConfig` with **pointer fields** (`nil` = unchanged) so
same-typed knobs can't be transposed; use the `Float64Ptr(v)` / `IntPtr(v)`
helpers. `Conversation().Messages()` returns a mutex-guarded copy of the heard
transcript.

## Serving the brain

Build a factory (runs `newBrain` once per session), then choose a transport.

```go
factory := brain.Factory(func() brain.Brain { return &Greeter{} }, logger)
```

### Inbound (primary)

```go
srv, err := cortex.NewDirectServer(factory, cortex.DirectOptions{
    Logger:          logger,
    PublicKeysPEM:   "",     // empty → embedded Voqalize platform keys
    Audience:        "brain",
    AllowUnverified: false,  // true only for local dev
})
// Mount on any net/http route ending in /s/{session_id}:
http.Handle("/s/", srv)                  // srv.ServeHTTP does the WS upgrade
// or run standalone:
err = srv.ListenAndServe(ctx, "localhost:8788")
```

`DirectServer` verifies the runtime's RS256 bearer (`sub == session_id`, optional
`aud`) against the embedded platform keys by default.

### Cortex (fallback)

```go
agent, err := cortex.New(cortex.Options{
    Version:   "1.0.0",
    CortexURL: "wss://cortex.voqalize.com/<pool>",
    APIKey:    "ak_…",                 // OR AuthorizationProvider: func() string { ... }
    Logger:    logger,
}, factory)
err = agent.Run(ctx)                    // returns when the wire closes permanently
```

## Examples

- **`sdk/go/examples/travel`** — `TravelBrain`, a real Gemini function-calling loop
  (`maxToolHops = 6`), screen-driving via `in.Action(...)`, `state_sync` handling.
- **`sdk/go/examples/cmd/travel-direct`** — inbound entrypoint (`NewDirectServer` +
  `ListenAndServe`).
- **`sdk/go/examples/cmd/travel-local`** — Cortex entrypoint (`cortex.New` +
  `agent.Run`).

## SDK parity notes

The Go SDK trails the Python one in a few places. If you're porting a brain:

- **No `Session.Action`.** Go exposes `Interaction.Action` / `ActionWithResult`
  only — a Go brain can't fire a UI command *outside* an interaction (e.g. from
  `OnSessionStart` or `OnAppEvent`) yet.
- **`ConfigureTTS` is positional** (`voice, language, model string`) rather than
  keyword-style; `""` means unchanged.
- **`OnError`** gives you `(direction, message string)` rather than an error
  frame object.
- **No `serve_auto` / mode selector** — construct `cortex.New` /
  `cortex.NewDirectServer` and call `Run` / `ListenAndServe` directly.
- **Action outcome callbacks are sync-only** (`func(Outcome)`).

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — the concepts in depth.
- **[Voice protocol reference](/docs/reference/voice-protocol/)** — the wire.
