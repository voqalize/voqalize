# Frontend — embedding the agent in a React app

`@voqalize/client-react` handles the browser half: session bootstrap, WebRTC
transport, mic, audio playback, and the two-way message lane. Start from
`templates/react_embed.tsx`.

The npm package is **not published yet** — install it from a clone of the
[voqalize/voqalize](https://github.com/voqalize/voqalize) repo
(`sdk/react`, built with `pnpm build`) and reference it as a `file:` / workspace
dependency.

---

## 1. Mint a publishable key

```
create_api_key(tenant, label="web", kind="publishable",
               allowed_origins=["https://your-site.com", "http://localhost:5173"])
```

The raw `pk_…` is shown **once**. Publishable keys are origin-allowlisted and safe to
ship to the browser. **Include the dev origin too**, or local session minting is
rejected. Never put an `sk_` (backend) or `ak_` (Cortex) key in frontend code — `pk_`
is the only key the browser ever sees.

## 2. Wire the three required values

| Prop | Value |
|---|---|
| `publishableKey` | the `pk_…` above |
| `agentId` | `agent.id` from `create_agent` / `list_agents` |
| `apiBase` | the control-plane root **including the API version** — the SDK appends `/sessions.create_and_start`. Production: `https://app.voqalize.com/api/v1` |

There is no workspace prop. A `pk_` key belongs to exactly one workspace, so the
control plane reads it off the key — naming it again in the call would just be a
second answer to a question the credential already answered. (MCP tools still take
a `tenant`: they are stateless RPC and hold no credential that names one.)

⚠️ Pointing `apiBase` at the bare host (no `/api/v1`) is the single most common
setup failure: the session mint 404s. If the app is served behind a proxy that
rewrites `/api/*` to the control plane, `apiBase: "/api/v1"` is same-origin and the
`pk_` only needs the one domain in `allowed_origins`.

## 3. Voice and language are NOT set here

**The page does not choose the voice.** The brain does — as class attributes:

```python
class ConciergeBrain(Brain):
    voice = "omnivoice/gauri"
    language = "hi"          # sets the recognizer AND the voice together
```

or, when the language depends on *this* caller, with one call in
`on_session_start` (which is also how you switch mid-call):

```python
session.configure_language("ta", voice="omnivoice/gauri")
```

Nothing in the frontend, and nothing on the agent record — the record has no
`stt`/`tts` fields at all. See `references/brain.md` and the **Voice & language
catalog** in the docs (`/docs/reference/catalog/`) for the value lists.

Why the rule is this blunt: `language` is really two settings. It picks the
**recognizer** (English → Parakeet, 22 Indic languages → IndicConformer) *and* the
**voice-cloning reference clip**, which changes *who is speaking* rather than how
text is read. Get one half wrong and nothing errors: a wrong recognizer garbles
the caller, and a wrong reference clip reads the right words in the wrong
speaker's accent — inaudible to every automated check, because the transcript is
still correct. Both have shipped. One field, one owner, both halves.

The `pipeline` prop still exists for a page that is genuinely the authority over
the pipeline — a console auditioning voices, an A/B harness. A brain that declares
or configures a voice overrides it, since the brain speaks last. If you do use it,
set the same `language` code on both `stt` and `tts`, and never set
`stt.language_hint` (the raw recognizer field the runtime derives from
`stt.language`; setting it by hand is how a config ends up half-applied).

`payload` is a different thing entirely: app data, which arrives brain-side as
`start.init` in `on_session_start`. A per-caller language belongs *there* — send
the choice, let the brain apply it.

## 4. Pick a surface

**`<VoqalAgent/>`** — drop-in. With no children it renders a minimal status +
mic/end bar. Pass a render-prop for full control (audio stays wired for you):

```tsx
<VoqalAgent {...config}>
  {(session) => (
    <button onClick={session.connect} disabled={session.connectionState !== "idle"}>
      Talk ({session.connectionState})
    </button>
  )}
</VoqalAgent>
```

**`useVoqalSession(options)`** — the hook underneath, when you own the layout
entirely. Same options; returns the same handle. Note that `VoqalAgent` defaults
`autoConnect: true` while the hook defaults to `false`.

The session handle: `client`, `connectionState`
(`idle|connecting|connected|disconnected|error`), `botState`
(`idle|listening|thinking|speaking`), `isUserSpeaking`, `error`, `connect()`,
`disconnect()`, `enableMic(bool)`, `sendMessage(type, data)`.

**`<AmbientPresence/>`** — the agent as a property of the whole page rather than a
widget in a corner: a full-viewport border glow that reads the agent's state
peripherally by hue and motion. Ships no stylesheet and no dependencies beyond React.

```tsx
<AmbientPresence botState={session.botState} connectionState={session.connectionState} />
```

Props: `palette` (per-state hues — `idle`/`listening`/`thinking`/`speaking`/`offline`/
`beam`, any subset), `tempo`, `weight`, `zIndex` (default 90), `radius`, and `beam`
(`{id, targetId}` — fires a short travelling line from the screen edge to the element
the agent just acted on, the visual tell that the *agent* moved the screen).
`prefers-reduced-motion` collapses it to a static ring.

Prefer this over a chat bubble. A voice operator that drives the UI should feel
omnipresent and in-context; a widget in the corner reframes it as a chatbot.

## 5. The two-way lane

Downward, **`useUiCommand(client, handlers)`** — subscribe, filter on
`type === "ui_command"`, strip the envelope (`type`/`action`/`action_id`), dispatch
on `action`. A handler gets the args alone:

```tsx
useUiCommand(session.client, {
  add_to_cart: ({ sku, qty }) => setCart((c) => [...c, { sku, qty }]),
});
```

Type it against the brain by declaring the command map — one entry per
`voqalize.sdk.Action` subclass — and passing it explicitly (an inline handler map
gives TypeScript nothing to infer from):

```tsx
interface ShopCommands {
  add_to_cart: { sku: string; qty: number };
}

useUiCommand<ShopCommands>(session.client, {
  add_to_cart: ({ sku, qty }) => setCart((c) => [...c, { sku, qty }]),   // typed
});
```

Every handler is optional and an unknown action is **not** an error — brain and
page ship separately, so a new command reaching an old build falls through to an
optional `"*"` wildcard, else `console.debug`. Handlers are read through a ref, so
an inline literal never re-subscribes. Also exported: `createUiCommandHandlers<T>`
(pin the map where it's defined instead of at the call site), `uiCommandArgs`, and
the `UiCommand` / `UiCommandArgs` / `UiCommandHandlers` types. `onServerMessage`
remains the raw escape hatch for non-`ui_command` traffic.

And upward, `session.sendMessage("cart_edited", { removed: sku })`. Exact shapes and
the state-only-vs-take-the-floor semantics: **`references/ui-actions.md`**.

## Gotchas

- **Mic permission is per-origin.** Granting it on the deployed site does nothing for
  `localhost`, and vice versa.
- **Autoplay** may be blocked until a user gesture — keep a real click on the way in;
  `VoqalAgent` swallows the rejection rather than erroring.
- **`onServerMessage` is already unwrapped** past the transport's `{data}` quirk —
  read `msg.type` directly, don't reach into `msg.data.type`.
- The hook owns one `PipecatClient` at a time and tears it down on unmount.

## Read next

- **`references/ui-actions.md`** — the message contract in both directions.
- **`references/instrumentation.md`** — what the brain should log about these sessions.
