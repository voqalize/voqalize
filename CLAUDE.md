# voqalize — Claude's map

The **public developer surface** for Voqalize: the wire contract (`proto/`), the
brain SDKs (`sdk/python`, `sdk/react`), the runnable demos (`demos/`), the docs
site (`docs/`) and the Claude Code skill (`skill/`). The platform itself lives in
the private `voqalcloud` repo; the speech stack lives in `vql-speech`.

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
    `sdk/react/**`, `docs/**`
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

## Voice and language belong to the brain — never to the page

`tts.language` selects the **voice-cloning reference clip**; `stt.language_hint`
selects the **recognizer**. They are one setting with two legs, and moving only one
is *silent*: the words stay right, only the speaker is wrong. No transcript, log,
metric or WER score can see it — a Hindi call read by an English reference clip
scores identically and sounds like a foreigner reading Devanagari. That was a real
production bug on `/demos/orderdesk`.

So there is exactly **one** sanctioned way to move a language, and it is server-side:

```python
class MyBrain(GeminiBrain):
    voice = "omnivoice/gauri"     # applied before on_session_start, so before greeting audio
    language = "hi"

    async def on_session_start(self, session):
        # Per-caller override, still both legs, still before the first word:
        session.configure_language("ta", voice="omnivoice/gauri")
```

`Session.configure_language(language, *, voice=None)` is `configure_tts(...)` **and**
`configure_stt(...)` in one call. That is the entire point of it — do not call the
two halves separately, and do not put a language anywhere a page or a database
record can set it. The agent record deliberately carries **no** stt/tts blocks; a
brain is version-controlled and a Firestore field is not.

The catalog is small and closed: voices are `omnivoice/gauri` (female) and
`omnivoice/gaurav` (male); `vql-stt` serves `en` plus the 22 Indic codes. An
unknown model is **HTTP 403 at connect**, an unknown voice prefix is
`voice not found` — both fail the session, not the sentence.

## Every demo has an e2e, and one of them is a sweep

`demos/tests/test_<name>_e2e.py` — all eleven. The real brain on a real
`brain_server` socket, driven by the conformance `VoiceDriver`, with only the
*model* faked: `ScriptedGemini` (`demos/voqalize_demos/testing.py`) for the nine
`GeminiBrain` demos, ADK's `ScriptedLlm` for `travel` and `orderdesk`. No network,
no API key, ~33 s for the whole suite.

`demos/tests/test_demo_voice_contract.py` is the cross-demo sweep: it asserts every
demo puts a **matched** voice/language pair on both legs before its first audio,
and carries a **negative control** proving the probe can fail. Add a demo → add a
row there, or its language pair is unguarded.

Footguns found writing them (see `demos/tests/_harness.py`):

- `driver.dump_conversation()` needs a *cooperating* brain
  (`answer_conformance_dump=True`). The `GeminiBrain` demos do not implement it —
  assert over `llm.captured_contents` instead, which is a stronger property anyway.
- A **blocking** tool (aura's `authenticate`) needs the turn in flight:
  `asyncio.create_task(driver.user_says(...))`, then
  `await driver.collect_ui_commands(min_count=1)` to read the nonce, then
  `send_client_message`.
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
renumbers every demo after it. A local nginx fronts them all at
`local.voqalize.com/demos/<name>` and `/docs`, the same paths the deployed apex
serves, so a demo mints its session same-origin exactly as it does in prod.

Each demo also runs standalone with plain `pnpm dev` (see `demos/README.md`) —
that path needs none of the above.

## Everything a developer reads is written to one standard

`design/voice.md` is the writing standard for this repo: the docs site, the SDK
docstrings, error messages, the wire contract's prose, the skill, the demo source, the
changelog and commit messages. It carries the persona, five principles, four signature
moves, a **closed lexicon** (a concept keeps one word across the proto, the SDK, the docs
and the site), and a recognition test to run before publishing. Read it before writing
anything a customer will see — including an error string, which is our highest-traffic
documentation and is read at the worst possible moment.

Two consequences worth knowing without opening it: **no surface calls Voqalize a
platform**, and **internal service or repository names never appear in customer-facing
text** — the runtime is *Voice*.

## Hard rules

- Python 3.12, uv, ruff, pyright, pytest. pnpm for the frontends.
- Never `--no-verify`, never force-push, never bypass hooks.
- This repo is **public**. No secrets, tenant ids, agent ids or node addresses in
  committed source. Publishable (`pk_live_`) keys and demo agent ids are injected
  as Cloud Build substitutions; the cloudbuild YAMLs here are **templates** whose
  real values live in the triggers.
