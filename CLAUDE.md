# voqalize — Claude's map

The **public developer surface** for Voqalize: the wire contract (`proto/`), the
brain SDKs (`sdk/python`, `sdk/react`), the runnable demos (`demos/`), the docs
site (`docs/`) and the Claude Code skill (`skill/`). The platform itself lives in
the private `voqalcloud` repo; the speech stack lives in `vql-speech`.

Read `README.md` for what each directory is and `demos/README.md` for how a demo
is built and deployed. This file is only the things that will bite you.

## ⚠️ Pushing `main` deploys PRODUCTION

There is **no `prod` branch in this repo**. A push to `main` fires four Cloud Build
triggers across two GCP projects, and two of them are production:

| Trigger | Project | Branch | What it touches |
|---|---|---|---|
| `deploy-brains-vm` | `voqal-cloud-dev` | `^main$` | dev brains → `brain.dev.voqalize.com` |
| **`deploy-brains-vm-prod`** | **`voqal-cloud-prod`** | **`^main$`** | **live brains → `brain.voqalize.com`** |
| `build-demos-web` | `voqal-cloud-dev` | `^main$` | web artifact → `gs://voqal-cloud-dev-web-artifacts/web/latest.json` |
| `build-demos-web` | `voqal-cloud-prod` | `^main$` | web artifact → the prod bucket's `web/latest.json` |

Every *other* production service (cortex, pygato, controlplane, marketing) is gated
on a `prod` branch in `voqalcloud`. **The demos are the sole exception** — they
promote themselves. One `git push origin main` and the brains behind
`voqalize.com/demos/*` are running your commit about four minutes later.

Consequences to internalize:

- **Run `cd demos && uv run pytest tests/` before you push.** It is the only gate;
  there is no staging soak, no approval, no canary.
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
  tests still rolls production if it touches the shared spine — `e2cc025` did
  exactly that. `demos/tests/**` alone is on neither list and fires nothing.
- **Neither brains host reports its commit.** `GET /_healthz` returns
  `{"ok":true,"demos":[...11 names...]}` and nothing else. To learn what is
  actually running: `ssh root@<node> 'docker ps --format "{{.Image}}"'` — the node
  addresses are in `voqalcloud`'s `docs/infrastructure-inventory.md`, not here.

Verify a push landed on **both** hosts, not one:

```sh
for h in brain.voqalize.com brain.dev.voqalize.com; do curl -fsS https://$h/_healthz; echo; done
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
        await session.configure_language("ta", voice="omnivoice/gauri")
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
`DirectAgent` socket, driven by the conformance `VoiceDriver`, with only the
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
cd demos && uv run pytest tests/     # the deploy gate — run it before every push
uv run ruff format --check . && uv run ruff check .
uv run pyright demos/voqalize_demos
```

`pyright` excludes `**/tests/**`; `demos/voqalize_demos/` is checked strictly.
Ten pre-existing errors live in `demos/orderdesk/backend/eval/disambig_eval.py` —
don't be alarmed by a full-repo `pyright` run, but don't add to them either.

## Hard rules

- Python 3.12, uv, ruff, pyright, pytest. pnpm for the frontends.
- Never `--no-verify`, never force-push, never bypass hooks.
- This repo is **public**. No secrets, tenant ids, agent ids or node addresses in
  committed source. Publishable (`pk_live_`) keys and demo agent ids are injected
  as Cloud Build substitutions; the cloudbuild YAMLs here are **templates** whose
  real values live in the triggers.
