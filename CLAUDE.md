# voqalize — Claude's map

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
- **The docs pin the version PyPI serves, so a renamed export blocks the promote.**
  Every install line — `build/quickstart.md`, `build/pipecat.md`,
  `overview/status.md`, `examples/fastapi_inbound/requirements.txt` — names the
  *published* release, and gets bumped in a commit of its own once PyPI has it
  (`8104298`, "point the install lines at 0.2.0, now that PyPI serves it"). Docs on
  `main` are written against this tree, so adding or renaming an export puts the
  two out of step, and a reader who follows an install line then gets a package
  without the name the page just used. **They are level as of 0.5.0, released
  2026-09-21**, which is the normal state right after a release and not the
  normal state. The files carrying that pin are `build/quickstart.md`,
  `build/pipecat.md`, `overview/status.md`, `reference/brain.md`,
  `sdk/python/examples/fastapi_inbound/requirements.txt` and the repo
  `README.md` — named here rather than counted, because a count is a number that
  rots quietly and a list is one you can `grep` for. `build/existing-agent.md`
  was on this list until the 2026-09-21 docs consolidation took its install line
  away; it carries no pin now, and a name on a grep list that matches nothing is
  the same rot in the other direction. The root `README.md` is the one that
  hides: it says "0.5.0 is published on PyPI" without an `==`, so it survives a
  grep for the install line and rots anyway. `reference/brain.md` hides the same
  way, in the same sentence shape, and `sdk/python/RELEASING.md` hides worse —
  its published list carries neither an `==` nor a tag, so it survives both
  greps, and saying what is published is the one job that sentence has. More sites move with the *tag* rather than
  the version — `sdk/python/README.md` links the proto and the wire reference at
  `blob/python-sdk-v0.5.0/`. Harmless on dev, wrong the moment it is public.
  **Release the SDK and bump the pins before you fast-forward `prod`** — or check
  by diffing `__all__`:

  ```sh
  git show python-sdk-v0.5.0:sdk/python/src/voqalize/sdk/__init__.py | grep -A40 __all__
  ```
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

## Voice and language: the brain owns it, per session

`tts.language` selects the **language the voice reads in** — for a cloned voice,
which recorded speaker; `stt.language` selects the **recognizer**. They are one
setting with two legs, and moving only one is *silent*: the words stay right,
only the speaker is wrong. No transcript,
log, metric or WER score can see it — a Hindi call read by an English reference
clip scores identically and sounds like a foreigner reading Devanagari. That was a
real production bug on `/demos/orderdesk`, and it is the reason every rule below
exists.

**The agent record does not carry voice, language or STT/TTS models.** It says
where the brain lives — `deployment.brain_url` — and carries the recording
default, and that is all. The `stt`/`tts` blocks it used to hold were removed;
legacy keys in stored documents are ignored and dropped on read
(`controlplane/app/domains/agents/configuration.py`).

The record is the wrong owner because a language usually depends on *this*
caller, who does not exist until the session starts. The hosted lead-qual brain
is the proof: it picks the language from the enquiry form's state (Tamil Nadu →
Tamil), so the record's `tts.language: hi` was wrong for every non-Hindi customer
it served. **A brain sets it in `on_session_start`**, which lands in time for the
greeting; a browser client with no brain of its own sends it with the connect
request instead. One answer, one authority, chosen per call.

**Two rules keep the silent bug dead, and they are enforced in different places
on purpose:**

- **The pairing rule**, checked where the configuration is *written* — the SDK
  raises `ConfigError` before the request leaves the process
  (`sdk/python/src/voqalize/sdk/wire/frames.py`). Both legs keep their own
  `language` field, because a voice speaks fewer languages than `vql-stt` hears
  — and how many fewer depends on the voice — so understanding Odia while
  speaking with the Hindi clip is a real, legitimate configuration. The guard is therefore not equality
  but **statedness**: naming a language on one leg and not the other is
  **rejected**. Changing only the voice touches no language field and is
  unaffected. This is a property of the message, which is why it needs nothing
  from the far end to decide.
- **No silent substitution**, checked where the configuration is *used*. A
  `tts.language` the chosen voice does not speak is **rejected**, not quietly
  served with the Hindi clip. To run an Odia call you write `stt.language = OR,
  tts.language = HI` — which is what is actually going to happen. Which
  languages a voice speaks is *not* in the proto and must not go there: it is a
  capability of the speech tier, it moves when a clip is recorded or a voice is
  added, and a wire contract that froze today's pairings would take a proto
  release, an SDK release and a redeploy to add a language.

**The pairing is refused wherever a configuration is written down** — the
control plane at `sessions.connect`, PyGato at `session_config.py`, and the
speech tier itself as a backstop — and every tier says the same sentence,
because none of them owns the roster. The speech tier publishes it at
`/voices.json`; the others fetch it at boot, in the background, and a fetch that
fails is tracked as a failure rather than as an empty catalog: a service that
could not reach the roster lets the pairing through and lets speech answer,
because an HTTP failure there does not predict a WebSocket one. The copies that
used to carry the roster — `pygato/speech/clip_languages.json`, its twin in the
control plane, and the display-name table beside it — are gone.

**A page still never sets either.** That part of the old rule was right and stays.

The surface is **deliberately narrow: voice, language and `stt.patience`.**
Voices and languages are protobuf enums, so an unserved value is unrepresentable
rather than silently falling back to the English recognizer. The VAD knobs that
left the wire in the rewrite stay off it and keep their internal PyGato
defaults. `patience` came back in 0.5.0 as a step on a 0-to-10 scale rather than
a duration, so it survives a retune of the tier underneath it; unset takes the
deployment's calibration, which is 7. We widen as we learn.

The catalog is small and closed, and the `Voice` enum is the one copy of the
voice half we keep on purpose — it is what gives a brain author autocompletion.
`design/voice_catalog.py check` holds it to what the speech tier serves, and
renders the docs table from the same fetch. `vql-stt` serves `en` plus the 22
Indic codes. An unknown model is **HTTP 403 at connect**, an unknown voice
prefix is `voice not found` — both fail the session, not the sentence.

`frames.proto` documents every declaration in place rather than in banner
comments, and `buf lint`'s `COMMENTS` category fails the build if one is
missing. protoc carries those into `SourceCodeInfo`, so they are the contract's
documentation for every consumer, not just for whoever opens the file.

### The call a brain actually makes

`await session.configure(Config(tts=…, stt=…, idle=…))` — one method, one wire
op, three optional sections. `Config.__post_init__` raises `ConfigError` on the
pairing rule, at the call site, before anything reaches the socket; the clip
rule is not checked here and comes back as `RequestRejected`. Voice and language
are the `Voice` / `Language` enums from `voqalize.sdk.wire`, whose members are
read out of the proto descriptor rather than written down twice;
`tests/wire/test_catalog_matches_proto.py` fails if they drift, and
`tests/wire/test_config_pairing.py` pins the rule.

It is **one request, not three**: a language change has to move both legs at
once, and splitting it would put a turn boundary — and a possible refusal —
between the halves.

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

`on_session_start` runs before `greet`. The `Brain.voice` / `Brain.language`
ClassVars and the `_apply_declared_voice` step that applied them are gone, for
the same reason the record no longer carries a language: a value fixed at import
time cannot name the language of *this* call.

`tests/direct/test_configure.py` pins the ordering that makes the hook enough: a
request from `on_session_start` reaches the wire before the first
`SpeechChunkFrame`. That ordering was the ClassVar's whole justification, so it
is now the only mechanism and it is tested directly.

## A tool announces and returns (SDK 0.7.0)

`GeminiBrain` runs its own tool loop: one request per turn, each call run as it
arrives, its result filed for the **next** request — normally the user's next
message. The SDK docstrings (`gemini.py`: `respond`, `needs_result_now`,
`TOOL_BUDGET_MS`) and `docs/src/content/docs/build/brain/tools.md` carry the
detail; what binds a demo:

- **Mark only reads.** `@needs_result_now` goes on a tool that reads in-memory
  data the model needs to answer correctly — a screen read, a balance, a cart.
  Actions, UI dispatches, sign-in prompts, language switches and echoes of
  what the model already knows stay unmarked. A marked tool costs a model
  round trip of silence; a read left unmarked is answered a turn late.
- **Never block on the UI.** A tool dispatches the sheet or picker and returns;
  the user's answer arrives as an `AppEvent` at `on_rtvi`, which appends it to the
  context. A dependency on that answer is a parameter the model cannot fabricate
  (aura's `authenticated_context`, verified by the brain), never a wait.
- **Every tool returns within `TOOL_BUDGET_MS`.** Over it, one warning is logged
  and nothing is cancelled. Slow work is started and reported later as context.
- **The prompt owns the first line.** A response that calls a tool and says
  nothing is silence until the user speaks — and, ten seconds in, Voqalize's own
  "taking longer" line. The `turn:` log line's `speechless=yes` counts them.

## Every demo has an e2e, and one of them is a sweep

`demos/tests/test_<name>_e2e.py` — one per demo. The real brain on a real
`brain_server` socket, driven by the conformance `VoqalizeDriver`, with only the
*model* faked: `ScriptedGemini` (`demos/voqalize_demos/testing.py`) drives every
one — the ADK adapter and its `ScriptedLlm` are gone, and so is the last
brain on `GeminiInteractionsBrain`, which is now marked experimental. No network, no API key, ~33 s for the whole suite.

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
  off `rig.command("open_auth")`, `send_ui_event`, then
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
uv run --with pyyaml python3 design/check_facts.py   # numbers and words, below
cd sdk/python && uv run python ../../design/voice_catalog.py check   # the voice roster, below
```

Everything above the roster line is exactly what `.github/workflows/ci.yml` runs,
in the same order, on the Python version `demos/Dockerfile` ships (3.12) with
`uv sync --frozen` — so a lockfile that has drifted from `pyproject.toml` fails CI
before it fails the image build.

The roster line is the exception, and `.github/workflows/voice-catalog.yml` runs
it on a schedule instead: it fetches a deployed speech node over the network, so
it fails for reasons a diff cannot cause, and a merge must not wait on that. What
it reports is a fact about the fleet. Run it yourself after adding a voice.

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

Starts the docs site and every demo UI. **Ports are declared in that file
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

## Everything a developer reads is checked

The docs site, the SDK docstrings, error messages, the wire contract's prose, the
demo source, the changelog and commit messages are all read by a customer — an
error string most of all, which is our highest-traffic documentation and is read
at the worst possible moment. **Internal service or repository names never appear
in any of it**: the end that dials your brain is *Voqalize*.

**A number goes in `design/facts.yaml` before it goes in a sentence.** Every
claimable version, count, licence and date lives there once, next to the file it
was read out of, and `design/check_facts.py` re-reads each one straight from that
source — so the facts file cannot quietly become the next stale page. Prose is
checked the other way round: a fact may declare the sentences that are wrong
*because* of it, which is how the docs site stopped saying the React client was
"not yet on npm" three weeks after it published. `design/lexicon.yaml` is the
same file for words — the **closed lexicon**, one word per concept across the
proto, the SDK, the docs and the site, plus the words that are never right in
customer prose — and `check_facts.py` reads it against every governed page.

**The voice roster is the same idea with the source outside this tree.**
`design/voice_catalog.py` fetches what the speech tier is actually serving — per
A-record, because `speech.*` is round-robin across nodes and one fetch proves
one node — and holds the `Voice` enum's `voice_id` options to it, and each
voice's languages to the `Language` enum, then renders `reference/catalog.md`'s
table from the same document. Run `render` after adding a voice; `check` is what
fails when somebody didn't, and `voice-catalog.yml` runs it every morning against
each environment so nobody has to remember. It needs the generated protobuf
module, so it runs from `sdk/python`.

`--host` picks the environment and defaults to prod, which is the environment the
docs describe — so the page is compared there and only there; everywhere else the
proto join still runs and the page check is skipped, because dev and prod are
*supposed* to differ between a release and its promotion.

Facts whose source is a registry or one of the three sibling repos cannot be
derived from this tree; they carry the command that re-earns the stamp, and
`--attested` lists them with the age of the last check. Run `--sweep` when you
want the retired synonyms too — mostly ordinary English, so it is advisory and a
person reads it.

`design/practices.md` is the other half, and it is internal: the numbered rules
for designing a voice agent, each marked *agreed*, *contested* or *violated*,
plus the reasoning the public page argues from — the moving parts and why there
is no merge, the tiers, the clocks, and the questions to ask before wrapping
anything. `practices.md` is what we know. It replaced `design/explanations/` on
2026-09-20, when the shipped design pages became one page and the outlines behind
them stopped having a separate job. Read it before you argue a design decision from first principles —
most of them have already been argued once, and the file says which ones are still
open.

## Standing direction: the app→brain leg is a platform gap, not a demo problem

Recorded verbatim (corrected for grammar) on 2026-09-09, and binding on anything
that touches the screen↔voice seam:

> This is the crux, isn't it? The root cause of state mismatch is a coarse full-state
> push. This also causes context bloat and reconciliation errors.
>
> Let's step back and fix this the right way. The right way is to send small,
> incremental and *semantic* updates to the brain. This then plays nicely with the
> LLM context as well — because the LLM sees "Change quantity for volini to 3" or
> "Selected variant 150g from Volini gel" or similar, along with id information.
>
> And this opens up the other question as well — are we doing typed updates in the
> UI → brain direction? Because this change requires it, and if our infrastructure
> doesn't provide it, it is a gap.
>
> So I want to zoom out and solve the larger problem first. As always, demos are a
> way to get to the root of the issue at the platform level — always remember that.
> We cannot brush this off as a demo issue (we own them). Ask the five whys — and ask
> specifically what the platform should do so that they become cheaper in the client
> implementation.

Three decisions taken on it the same day, also verbatim:

> **On whether events mutate the brain's model:** not really. The brain receives the
> typed message, then decides if it wants to inject it into the LLM context, or update
> its model, or ignore it, or whatever else it wants to do with it. Not our decision to
> make.
>
> **On the wire:** I want the wire to be backward compatible, but it is okay to
> deprecate and recommend something better.
>
> **On scope:** OrderDesk should be the first to implement, without changing the wire
> today. Let's learn what works and what doesn't. Then we extract what works into the
> platform in a better way. Which means the first cut is purely an OrderDesk change. In
> other words — we start from the demo, prove out the concept, generalize to typed
> objects in the reverse direction, decide if we need a wire change. Start small and
> then work upwards.

So the order of work was fixed: **demo first, SDK second** — the `Action`-symmetric
type was not written until OrderDesk had shown which events a real screen actually
needs. All three steps have shipped: the demo cut, the SDK type, and the fleet —
`state_sync` is gone from every demo, and every app→brain gesture is a typed event.

**There is no third step — the wire cannot earn one** (traced 2026-09-09, once the demo cut
was in). `state_sync` is a string a demo invented: it appears nowhere in `proto/`, the
control plane or PyGato. The browser sends it with stock `client.sendClientMessage`, which
makes it an RTVI `client-message` whose payload the wire carries as an opaque JSON string,
and the typed events ride that identical envelope. Even moving them onto the reserved
`ui-event` / `ui-snapshot` types is an SDK choice, not a proto edit — both are already
defined, already whitelisted app→V→B, and both unused. The whole gap is in `sdk/python`;
detail in `platform/docs/demo-quality-tracker.md` row 31.

**A demo defect is a platform question until proven otherwise.** The demos are ours;
a workaround written inside one is a bill the next developer pays in full, and the
same workaround appearing in two demos is a feature the SDK owes them.

**The asymmetry it named is closed** (2026-09-09). app→brain was
`RTVIMessage.data: Any`, an untyped dict the developer dug through by string key; it
is now `AppEvent` + `AppEvents` in `sdk/python`, `Action`'s mirror image, riding
RTVI's own `ui-event`, with `voqalize types` generating both unions out of the one
module. Every demo with a screen is now a user, and no demo calls `sendClientMessage`
any more — OrderDesk's last two untyped requests became `catalog_searched` and
`variants_opened` on 2026-09-09, so app→brain is one envelope. `client-message`/`{t, d}`
still parses, forever, for a page written before it.
The SDK docstrings and `docs/src/content/docs/build/brain/{context,typescript}.md`
carry the detail; do not restate it here.

### Typed and fine-grained, in both directions

Recorded verbatim on 2026-09-09, and binding on every screen↔voice seam we build:

> a11y tree is the WRONG abstraction in general. That's the whole point on why
> voqalize works the way it does. Don't build generic tools; instead, build typed
> and application specific fine grained events in both directions.

A generic screen abstraction — an a11y tree, a DOM snapshot, a `state_sync` blob — is
the coarse full-state push wearing a different hat, and it fails the same way in both
directions. app→brain it bloats the context and reconciles wrongly; brain→app it makes
every update a whole-row rewrite, which is why OrderDesk grew `pinned`, `keepChoice`
and `offersPin` to defend the screen from its own brain. Those guards are not the fix;
fine granularity is, because a `RowQuestion` that carries only a question cannot
un-match a row no matter how stale it is. RTVI reserves `ui-snapshot` for exactly the
generic streamer we are declining — it stays unused.

**A session starts from first principles, not from a screen.** When a call opens the
brain reconstructs its model from backend state — empty, if that is what the backend
says. The app does not load a view from an API and hand it to the brain to seed it.

**Backward compatibility binds the SDK and the wire, and nothing else.** A demo owes
compatibility to no one: `state_sync` was a string a demo invented, so a demo could
delete it outright. `client-message` and its `{t, d}` payload keep working forever
because they are SDK surface; what changes is what we teach.

## Hard rules

- Python 3.12, uv, ruff, pyright, pytest. pnpm for the frontends.
- Never `--no-verify`, never force-push, never bypass hooks.
- This repo is **public**. No secrets, tenant ids, agent ids or node addresses in
  committed source. Publishable (`pk_live_`) keys and demo agent ids are injected
  as Cloud Build substitutions; the cloudbuild YAMLs here are **templates** whose
  real values live in the triggers.
