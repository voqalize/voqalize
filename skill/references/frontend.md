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

## 2. Wire the four required values

| Prop | Value |
|---|---|
| `publishableKey` | the `pk_…` above |
| `agentId` | `agent.id` from `create_agent` / `list_agents` |
| `tenantSlug` | the same slug you pass to every MCP tool |
| `apiBase` | the control-plane root **including the API version** — the SDK appends `/{tenantSlug}/…`. Production: `https://app.voqalize.com/api/v1` |

⚠️ Pointing `apiBase` at the bare host (no `/api/v1`) is the single most common
setup failure: the session mint 404s. If the app is served behind a proxy that
rewrites `/api/*` to the control plane, `apiBase: "/api/v1"` is same-origin and the
`pk_` only needs the one domain in `allowed_origins`.

## 3. Choose the voice and language — the `pipeline` prop

**This is the prop people miss.** Without it the session uses server defaults; with
it you pick STT model/language and TTS voice/language per session:

```tsx
<VoqalAgent
  apiBase={API_BASE}
  tenantSlug={TENANT_SLUG}
  publishableKey={PUBLISHABLE_KEY}
  agentId={AGENT_ID}
  pipeline={{
    stt: { model: "vql-stt", language: "hi" },
    tts: { voice: "omnivoice/gauri", language: "hi" },
  }}
  payload={{ surface: "web", user: { name: "Ada" } }}
/>
```

**Setting the language has exactly one form: the same `language` code on both
`stt` and `tts`.** Write both every time, even for English. Do not set
`stt.language_hint` — it is the raw recognizer field the runtime derives from
`stt.language`, and setting it by hand is how a config ends up half-applied.

- `stt.model` — leave it `vql-stt` (a router covering English plus 22 Indic
  languages; it picks the engine from `language`). There is no other recognizer.
- `stt.language` picks the **recognizer**; `tts.language` picks the **voice-cloning
  reference clip**, so it changes *who is speaking*, not just how text is read.
- `tts.voice` — a catalog voice id: `omnivoice/gauri` or `omnivoice/gaurav`.
- Full value list: the **Voice & language catalog** in the docs
  (`/docs/reference/catalog/`).

Get one half wrong and nothing errors. A wrong `stt.language` transcribes the
caller with the English model; a wrong `tts.language` reads the right words in the
wrong speaker's accent — and that one is inaudible to every automated check,
because the transcript is still correct. Both have shipped. Write the pair.

Mid-call the brain changes language with **one** call —
`session.configure_language("hi")` (add `voice=` if the language wants another
persona). Never as a `configure_tts` + `configure_stt` pair. The `pipeline` prop
only sets what the session *opens* with.

`payload` is separate from `pipeline`: it is app data, and it arrives brain-side as
`start.init` in `on_session_start`.

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
