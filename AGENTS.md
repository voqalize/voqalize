# voqalize — Codex's map

The **public developer surface** for Voqalize: the wire contract (`proto/`), the
brain SDK (`sdk/python`), the runnable demos (`demos/`) and the docs site
(`docs/`). The platform itself lives in the private `voqalcloud` repo; the speech
stack lives in `vql-speech`.

There is no `sdk/react` any more — the React client package was deprecated and
deleted on 2026-08-24. The browser half of a call is stock pipecat plus one
`fetch`, written down in `docs/src/content/docs/client/handshake.md`. Do not
reintroduce a client wrapper: it is a second surface to learn and a lag behind
every pipecat release, which is what retired the last one.

There is no `skill/` any more — it was deleted on 2026-08-21. An agent is oriented
by the MCP server's own `instructions` and then reads the docs site, every page of
which is served as raw markdown at its URL plus `.md` and indexed at
`docs.voqalize.com/llms.txt` (`docs/src/pages/`). Do not reintroduce a second, abridged copy
of the documentation: keeping it honest is a job nobody does, and the last one
drifted.

Read `README.md` for what each directory is and `demos/README.md` for how a demo
is built and deployed. This file is only the things that will bite you.

## Two branches: `main` → dev, `prod` → production

`main` deploys **dev**. Production moves only when someone pushes `prod`:

| Trigger | Project | Branch | What it touches |
|---|---|---|---|
| `deploy-brains-vm` | `voqal-cloud-dev` | `^main$` | dev brains → `brain.dev.voqalize.com` |
| **`deploy-brains-vm-prod`** | **`voqal-cloud-prod`** | **`^prod$`** | **live brains → `brain.voqalize.com`** |
| `build-demos-web` | `voqal-cloud-dev` | `^main$` | web artifact → `gs://voqal-cloud-dev-web-artifacts/web/latest.json` |
| `build-demos-web` | `voqal-cloud-prod` | `^prod$` | web artifact → the prod bucket's `web/latest.json` |

This is the same shape every other service already had (cortex, pygato,
controlplane, marketing are all `main` → dev, `prod` → prod in `voqalcloud`). The
demos were the sole exception until 2026-08-07: both production triggers watched
`^main$`, so one `git push origin main` had the brains behind `voqalize.com/demos/*`
running your commit about four minutes later, with no gate, no soak and no canary
in between.

Promote by fast-forward, never by committing on `prod`:

```sh
git checkout prod && git merge --ff-only main && git push origin prod && git checkout main
```

`--ff-only` is the point: `prod` is a pointer at a commit that has already been on
`main`, been through CI, and run in dev. Anything that cannot fast-forward means
someone committed to `prod` directly, which is the state this branch exists to
prevent.

Consequences to internalize:

- **CI is now a real gate.** `.github/workflows/ci.yml` runs ruff, pyright, the SDK
  suite and every demo e2e on every push and PR — deliberately unfiltered, because
  which paths deploy is decided by the trigger, not by anything readable here (see
  below). `ci-web.yml` builds the demo UIs and the docs site, and *is* path-filtered.
  Run `cd demos && uv run pytest tests/` locally anyway; it is 33 s.
- **A dev deploy is now the thing that proves a change**, not a hope. `main` lands
  on `brain.dev.voqalize.com`; exercise it at `dev.voqalize.com/demos/*` before you
  fast-forward `prod`.
- The web half is a two-step: `build-demos-web` only *stages* an artifact and moves
  `latest.json`. The apex site (`voqalize.com`) picks it up on the **next**
  `deploy-marketing-prod` run (fired by `voqalcloud`'s `prod` branch), which reads
  `latest.json` unless `_WEB_SHA` pins a version. So a UI change sits armed until
  someone deploys marketing for an unrelated reason — and then ships.
- **Which trigger fires is decided by `includedFiles` on the trigger, not by
  anything in this repo** — so you cannot read it off the YAML. Today:
  - brains ← `demos/**/backend/**`, `demos/voqalize_demos/**`, `sdk/python/**`,
    `demos/pyproject.toml`, `demos/Dockerfile`, `demos/docker-entrypoint.sh`,
    `demos/bin/brains-node-deploy.sh`, `demos/cloudbuild.brains-vm.yaml`, `uv.lock`
  - web ← `demos/**/frontend/**`, `demos/build.mjs`, `demos/manifest.json`,
    `sdk/react/**`, `docs/**` — that fourth entry is now dead, and only someone
    with access to the trigger can remove it; it matches nothing since the React
    SDK was deleted.
  Note what that means: **`demos/voqalize_demos/**` is on the brains list**, and
  that is where the test fakes live (`testing.py`). A commit that adds nothing but
  tests still rolls the brains if it touches the shared spine — `e2cc025` did
  exactly that. `demos/tests/**` alone is on neither list and fires nothing. This
  is also why `ci.yml` has no path filter: the list above is a transcription of a
  private trigger field, and a CI filter derived from it would skip the run on
  exactly the commits nobody expected to deploy.
- **Each brains host reports the commit it is running**, at `GET /_healthz` as
  `git_sha` (`e521f72`), and the deploy *gates* on it — a build that never
  actually replaced the container fails instead of reporting success while the old
  one keeps answering. That field is how you tell dev and prod apart now that they
  can legitimately differ.

See what each environment is running — the two `git_sha`s are now expected to
differ between a `main` push and its promotion:

```sh
for h in brain.dev.voqalize.com brain.voqalize.com; do curl -fsS https://$h/_healthz; echo; done
```

## Voice and language: the record holds the default, the brain overrides

`tts.language` selects the **voice-cloning reference clip**; `stt.language`
selects the **recognizer**. They are one setting with two legs, and moving only
one is *silent*: the words stay right, only the speaker is wrong. No transcript,
log, metric or WER score can see it — a Hindi call read by an English reference
clip scores identically and sounds like a foreigner reading Devanagari. That was
a real production bug on `/demos/orderdesk`.

The agent record carries the session's default configuration, and the brain
overrides it at runtime when the language depends on *this* caller:

```python
class MyBrain(GeminiBrain):
    async def on_session_start(self, session):
        # The enquiry form said Tamil Nadu. Both legs, before the first word:
        await session.configure(
            Config(
                stt=SttConfig(language=Language.TA),
                tts=TtsConfig(language=Language.TA, voice=Voice.OMNIVOICE_GAURI),
            )
        )
```

One request, three optional sections — `tts`, `stt`, `idle`. Not three requests:
a language change has to move both legs at once, and splitting it would put a
turn boundary and a possible refusal between the halves.

**Both legs carry their own `language`, and that is not duplication.** `vql-stt`
serves 23 languages; `omnivoice` has reference clips for ten (`hi, en, bn, gu,
kn, ml, mr, pa, ta, te`). So understanding Odia while speaking with the Hindi
clip is a real configuration that one field could not express. Two rules follow,
enforced in different places on purpose:

- **The pairing rule**, raised as `ConfigError` by `Config` itself before
  anything reaches the socket. Name a language on one leg and you must name it
  on the other. Not that they agree — that you *stated* both. Changing only the
  voice touches no language field and is unaffected. It is checked here because
  it is a property of the message, decidable without asking anyone.
- **No silent substitution**, answered by the runtime as a rejected `Response`.
  A `tts.language` the speech tier has no clip for is refused rather than
  quietly served by the Hindi clip. To run an Odia call you write
  `stt.language = OR, tts.language = HI` — which is what is actually going to
  happen. Which languages have clips is deliberately *not* in the proto: it is
  the speech tier's own capability and moves when a clip is recorded, and a
  roster frozen into a wire contract would need a proto release, an SDK release
  and a redeploy to add a language.

**A page still never sets either.** That part of the old rule was right and stays.

The surface is deliberately narrow: voice and language only. `Voice` and
`Language` are protobuf enums, so a value we do not serve is unrepresentable
rather than silently falling back to the English recognizer; the eleven VAD knobs
left the wire entirely and keep PyGato's own defaults. The catalog is small and
closed: `omnivoice/gauri` (female) and `omnivoice/gaurav` (male), and `en` plus
the 22 Indic codes. An unknown model is **HTTP 403 at connect**, an unknown voice
prefix is `voice not found` — both fail the session, not the sentence.

**A brain that wants its own voice says so in `on_session_start`**, which runs
before `greet`. The `Brain.voice` / `Brain.language` ClassVars and the
`_apply_declared_voice` step that applied them are gone: a value fixed at import
time cannot name the language of *this* call. A demo whose page settles the
language before the call exists sends it with the connect request instead and
configures nothing — one answer, one authority.
`tests/direct/test_configure.py` pins the ordering that makes the hook enough.

## Every demo has an e2e, and one of them is a sweep

`demos/tests/test_<name>_e2e.py` — all eleven. The real brain on a real
`brain_server` socket, driven by the conformance `VoqalizeDriver`, with only the
*model* faked: `ScriptedGemini` (`demos/voqalize_demos/testing.py`) drives all
eleven, aura's `GeminiInteractionsBrain` included — the ADK adapter and its
`ScriptedLlm` are gone. No network, no API key, ~33 s for the whole suite.

`demos/tests/test_demo_voice_contract.py` is the cross-demo sweep: it asserts every
demo puts a **matched** voice/language pair on both legs before its first audio,
and carries a **negative control** proving the probe can fail. Add a demo → add a
row there, or its language pair is unguarded. Every row asserts — the
`unported=True` xfail escape hatch is gone, because there is nothing left to
excuse: each demo either configures from `on_session_start` or sends the pair
with the connect request.

Footguns found writing them (see `demos/tests/_harness.py`):

- `driver.dump_conversation()` needs a *cooperating* brain
  (`answer_conformance_dump=True`). The `GeminiBrain` demos do not implement it —
  assert over `llm.captured_contents` instead, which is a stronger property anyway.
- **Nothing blocks on the customer**, and the tests have to be written that way.
  aura's `show_auth_popup` dispatches the sign-in and returns, so the turn
  completes on its own; the customer's answer is a separate step — read the nonce
  off `rig.command("open_auth")`, `send_client_message`, then
  `await asyncio.sleep(0.1)` before the next turn, since `on_rtvi` takes no floor
  and there is nothing to await. What the customer did is never on the wire: it
  reaches the model as context, so assert on the *next* request's `input`.
- Asserting on a tool result: read `part.function_response.response["result"]`,
  **not** `str(response)` — the outer dict re-escapes quotes, so a match on
  `"'status': 'declined'"` fails for exactly the results containing an apostrophe.

## Quality gates

```sh
uv run ruff format --check . && uv run ruff check .
uv run pyright                       # whole repo, and it is clean — keep it that way
cd sdk/python && uv run pytest -q
cd demos && uv run pytest tests/     # every demo's brain over the real wire, ~33 s
```

These are exactly what `.github/workflows/ci.yml` runs, in the same order, on the
Python version `demos/Dockerfile` ships (3.12) with `uv sync --frozen` — so a
lockfile that has drifted from `pyproject.toml` fails CI before it fails the image
build.

`pyright` is strict and excludes `**/tests/**`. **A bare `uv run pyright` used to
report ten errors**, which made a whole-repo type gate impossible — CI would have
been red on arrival, so every other file went unchecked. That is resolved:
`demos/orderdesk/backend/eval/disambig_eval.py` (an offline eval harness the
umbrella app never imports) is excluded in `pyproject.toml` with a note, and the
three errors that turned out to be in *shipping* brain code — a possibly-unbound
`spoke` and a `str | None` joined as `str`, both in `demos/orderdesk/backend/
brain.py` — were fixed rather than fenced. Don't add to the exclusion.

## Running it locally

```sh
pm2 start ecosystem.config.cjs
```

Starts the docs site and all eleven demo UIs. **Ports are declared in that file
and nowhere else** — pm2 passes each on the command line and no `vite.config.ts`
or `astro.config.mjs` here names one. The demo ports are a base plus the index
into the `DEMOS` array, which is therefore **append-only**: inserting a name
renumbers every demo after it. A local nginx fronts the demos at
`local.voqalize.com/demos/<name>`, the same paths the deployed apex serves, so a
demo mints its session same-origin exactly as it does in prod. The docs get an
origin instead — `docs.local.voqalize.com`, matching `docs.dev.` and `docs.` —
and the apex answers `/docs/**` with the same permanent redirect it does in dev
and prod.

Each demo also runs standalone with plain `pnpm dev` (see `demos/README.md`) —
that path needs none of the above.

## Everything a developer reads is written to one standard

`design/voice.md` is the writing standard for this repo: the docs site, the SDK
docstrings, error messages, the wire contract's prose, the demo source, the
changelog and commit messages. It carries the persona, five principles, four signature
moves, a **closed lexicon** (a concept keeps one word across the proto, the SDK, the docs
and the site), and a recognition test to run before publishing. Read it before writing
anything a customer will see — including an error string, which is our highest-traffic
documentation and is read at the worst possible moment.

Two consequences worth knowing without opening it: **no surface calls Voqalize a
platform**, and **internal service or repository names never appear in customer-facing
text** — the end that dials your brain is *Voqalize*.

## Hard rules

- Python 3.12, uv, ruff, pyright, pytest. pnpm for the frontends.
- Never `--no-verify`, never force-push, never bypass hooks.
- This repo is **public**. No secrets, tenant ids, agent ids or node addresses in
  committed source. Publishable (`pk_live_`) keys and demo agent ids are injected
  as Cloud Build substitutions; the cloudbuild YAMLs here are **templates** whose
  real values live in the triggers.
