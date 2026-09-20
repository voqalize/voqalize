# `patience` — a wire knob for how long the recognizer waits before it calls the turn

Status: decided 2026-09-20, implementation under way. The board beside this file
(`patience-tasks.md`) sequences it; the speech-tier half is cross-referenced from
`speech/docs/flux-v2.md` §11.2.

The decisions that were open when this was written have been taken:

- **Speech owns the patience → `eager_frames` mapping.** PyGato forwards the scale
  verbatim and never knows a frame count.
- **The documented default is `patience = 7`**, which is what an unset field resolves
  to, and the resolution lives in speech: unset means the deployment's calibration, and
  `VQL_STT__VAD_EAGER_FRAMES=18` on dev and prod *is* patience 7 under the mapping. So
  the default is stated in every docstring, no existing session changes behaviour, and
  recalibrating stays one speech deploy.

---

## What this is

Today a brain can tell Voqalize *which language* to listen in and nothing else about
listening. How long the recognizer waits through a pause before it decides the caller
has finished is fixed for the whole deployment.

That is wrong for the reason the user gave: an interviewer wants to wait, a support bot
wants to answer. The same deployment serves them both.

`patience` is an abstract scale on `SttConfig` that resolves, inside the speech tier, to
the silence gate that triggers `EagerEndOfTurn`.

---

## Where the latency actually comes from

When the caller stops speaking (`speech/docs/flux-v2.md` §2, §6, §9):

- Silence accumulates in 32 ms windows. At `eager_frames`, `EagerEndOfTurn` fires and
  SmartTurn runs **once**.
- SmartTurn's probability is compared to `eot_threshold`. Above → `EndOfTurn` commits.
  At or below → the turn stays open.
- If it did not commit, the turn waits out `eot_timeout_ms` of trailing silence — counted
  from speech-stop, not from the eager.

So `eager_frames` is the **floor on every confident turn-end**. The user has already ruled
the other levers out of scope: `eot_threshold` stays internal, `eot_timeout_ms` does not solve
their problem. `eager_frames` is the lever.

The cost of moving it is recorded in `speech/infra/deploy/env/prod.env`, which raised it
from the code default 13 to 18: *"trades a flat ~160 ms latency add on every turn-end for
the longer floor"*. And the cost of moving it back is recorded in `dev.env`: at 13, dev
*"deterministically split a 9 s continuous monologue into two turns at a mid-answer breath
(6/6 runs; prod at 18 never did, 3/3)"* — and because the route uses REPLACE semantics on
the cumulative transcript, the split **truncated the reported answer to its tail**.

Both of those are real. Neither is universally right. That is the argument for the knob.

---

## Verified starting state

Every claim below was read out of the tree, not assumed.

**The Voqalize wire.** `SttConfig` (`voqalize/proto/voqalize/frames/frames.proto:268`)
carries `optional Language language = 1` and nothing else. The comment above `Config`
records the readings of unset: at session creation *take Voqalize's default*, on the
wire *leave it alone*.

**`eager_frames` is not on the Flux wire at all.** It is deployment-only
(`VQL_STT__VAD_EAGER_FRAMES`), folded into `TurnConfig.eager_frames`
(`speech/src/vql_speech/flux/turn_detector.py:233`, code default 13) by
`turn_config_from_settings` (`speech/src/vql_speech/server/flux_route.py:417`).

**It is read in exactly one place in the reducer** — `turn_detector.py:486`,
`if self._silence_run >= self._cfg.eager_frames:`, inside `_step_in_turn`. This matters
for the mid-call question below.

**The invariant is strict.** `TurnConfig.__post_init__` (`turn_detector.py:274`) raises on
`update_frames >= eager_frames`, with the message *"otherwise no mid-turn pause ever
flushes a segment"*. `app._validate_turn_shape` (`speech/src/vql_speech/server/app.py:132`)
runs the same constructor at boot so a bad shape fails the container rather than every
`/v2/listen` upgrade.

**Both deployed envs run `update_frames=10` and `eager_frames=18`**
(`speech/infra/deploy/env/{dev,prod}.env`).

**The Flux entry paths fail differently.** `FluxQueryParams` is `extra="forbid"` — an
unknown param **400s the WebSocket upgrade**. `FluxConfigureThresholds` and
`FluxConfigureFrame` are both `extra="ignore"` — an unknown field is **silently swallowed**.
Same new field, loud failure on connect and silent failure mid-call. This dictates deploy
ordering.

**PyGato owns its Configure frame.** `VqlSpeechSTTService`
(`platform/backend/pygato/src/pygato/stt.py:165`) builds
`{"type": "Configure", "language_hints": [...]}` itself at `stt.py:280`, never reaching
pipecat's `_send_configure`, and runs a one-in-flight queue with ack correlation and an
expiry timer. `_build_query_string` appends `language_hint` to the connect URL. Those are the seats
to copy.

**`refusal()` is the shared validator.** `platform/backend/pygato/src/pygato/session_config.py:52`
is reached by both the control plane's connect path and the brain's mid-call
`VqlConfigureFrame`, and its module docstring says so: *"a configuration the brain cannot
ask for at 09:00 is not one a page may connect with at 09:01."* It already refuses
`idle.timeout_ms` above `MAX_IDLE_TIMEOUT_MS` with a sentence.

**The SDK refuses where the brain wrote it.** `Config.__post_init__`
(`voqalize/sdk/python/src/voqalize/sdk/wire/frames.py:327`) raises `ConfigError` for the
one-leg-language mistake, *"Raised where the brain wrote it rather than one round trip
later, because a rejected request costs a turn to find out about."*

---

## This was built once already

`git log` in `speech/`:

| commit | date | what |
|---|---|---|
| `59d70eb` | 2026-07-07 | `feat(flux): expose VAD/turn-detector knobs via mid-call Configure` |
| `e373353` | 2026-09-05 | `refactor(flux): shrink the Configure wire surface to Deepgram's three fields` |
| `2b0148f` | 2026-09-10 | `docs(turn-detection): the turn-shape knobs are per-demo, so the experiment is not ours` |

`59d70eb` put `vad_eager_frames` on the mid-call `Configure` and proved it end to end:

> Proven end-to-end with a real-WebSocket test (`tests/support/mock_engine.py` +
> `synthetic_audio.py`): a mid-call Configure lowering `vad_eager_frames` visibly speeds
> up `EagerEndOfTurn`, with the mock engine's cumulative transcript flowing through
> correctly.

**Both helpers still exist in the tree**, and `tests/unit/server/test_flux_configure_e2e.py`
survived — `e373353` rebuilt its Configure case around `eot_threshold`/`eot_timeout_ms`
rather than deleting the harness. So the mechanism is proven and the rig is standing.

`e373353` removed it, and gave a reason that is worth quoting because **it expires the
moment this work lands**:

> `Configure.thresholds` accepted twelve fields; nine of them reshaped the turn machine
> mid-session and **no client has ever sent one**. … The turn *shape* is deployment config
> … A knob no producer writes is not a feature, it is an untested branch and an unvalidated
> input.

That reasoning was correct then and does not apply now: PyGato becomes the producer, the
field is range-validated at every seat that already validates, and the e2e test exists. Re-adding is not a
revert of a judgement — it is the arrival of the thing whose absence justified the
judgement. Say so in the commit message, and cite `e373353` by hash.

**A stale doc line to fix while in there.** `2b0148f` (five days *after* the removal) added
to `speech/docs/turn-detection-findings.md`:

> **Turn-shape knobs are already per-demo and per-session** — `barge_in_ms` and its
> neighbours are set by the caller on the wire, so trying a shorter turn for one demo needs
> no change here and no deploy.

That was already false when written — `e373353` had removed exactly those fields, and
`barge_in_ms` is deployment-only (`VQL_STT__VAD_BARGE_IN_MS`). It sent a latency program to
the wrong repo. Correct it as part of this work; it is the same subject.

---

## Decisions

### The scale is derived from the deployment, not hardcoded

**`eager_frames = update_frames + 1 + patience`**, with `patience` in `0..=10`.

The user asked for `0 → 10` and `10 → 20`. **`patience=0 → 10` is illegal on the deployed
envs** — `update_frames` is 10 and the invariant is strict, so `eager_frames` must be at
least 11. The endpoint cannot be delivered as specified.

The alternatives, and why they lose:

- *Hardcode the floor at 11* (`eager = 11 + patience`). Works today, silently breaks the
  day anyone moves `update_frames`, and the 11 is a magic number whose derivation is
  exactly the invariant it is dodging.
- *Drop `update_frames` to 9 so 10 becomes legal.* `update_frames=10` is calibrated —
  `speech/docs/rca-interview-48339-2026-08-13.md` measured mid-phrase cuts 74 → 32 and
  domain-vocabulary hits 68 → 82, **saturating at 10**. Moving a measured value to make a
  scale endpoint fit is the tail wagging the dog.

Deriving it costs nothing and is self-documenting: *the lowest legal eager gate is one
frame above the mid-turn flush, and patience counts up from there.* The invariant can then
never be violated by any patience in range, which turns the live validation below into a
guard rather than a live failure path.

At the deployed `update_frames=10` this gives **11..21 frames, ~352..672 ms**. Against what
was asked (10..20, ~320..640 ms) that is one frame — 32 ms — at each end. Worth stating to
the user plainly; it is well inside the noise of what they are tuning, and the ~672 ms
ceiling sits just above the 18 (~576 ms) dev and prod already run and trust.

Today's deployed `eager_frames=18` is `patience=7` under this mapping.

### Speech owns the mapping

**Decided: speech.** This was the one recommendation against the original brief, and it
was accepted. The argument is kept because it is the reason, not the decision.

The brief said *"patience is the external name that computes the right vad_eager_frames and
sends it to speech"*, with PyGato doing the computing. **Recommend against.** PyGato should
forward `patience` verbatim and never know a frame count.

- **PyGato cannot compute it correctly.** The floor is `update_frames + 1`, and
  `update_frames` is a speech deployment setting PyGato has never seen. A PyGato that
  computes frames either hardcodes a floor it cannot verify, or computes an illegal value
  and gets a rejection back — and then the brain is told its request failed over a number
  *it never wrote*. Every error message on that path names a frame count to a developer
  whose whole interface is a 0..10 scale.
- **The calibration would be pinned in the wrong repo.** If 11..21 turns out to want to be
  13..23 next quarter, a speech-owned mapping is one speech deploy. A PyGato-owned mapping
  is a PyGato change *and* a PyGato deploy, with the speech env now lying about what it
  controls. The whole value of an abstract scale is that the numbers behind it can move;
  putting the numbers in the consumer throws that away on day one.
- **It contradicts settled doctrine in this codebase.** `voice_id` and `iso_code` are
  proto *enum options*, and PyGato builds `_PB_TO_VOICE` from the descriptor rather than a
  hand-written table, precisely so the spelling has one owner. `SttConfig.language` carries
  `Language.HI`, not `"hi"`; the tier does that translation. `patience` is the same shape of
  thing: the wire carries the meaning, the tier carries the spelling.

The one real argument the other way — that speech's Flux surface was just deliberately
shrunk to Deepgram's fields — is answered below by keeping `patience` **out of
`thresholds`**.

The invariant this buys, and the one to defend in review: **the formula exists in exactly
one place.** `eager_frames_for_patience` in `flux/turn_detector.py` is that place. No frame
count is computed in PyGato, the SDK, the control plane or a test fixture.

### The default is 7, and unset is how it is delivered

`optional uint32 patience` on `SttConfig`, documented everywhere as **defaulting to 7**.
Unset is the mechanism that delivers that default: PyGato sends no patience on the query
string and none in the `Configure`, and `VQL_STT__VAD_EAGER_FRAMES` decides, exactly as
today. Dev and prod both run `eager_frames=18`, which under the mapping *is* `patience=7`.
So the documented default and the deployed behaviour are the same number, arrived at from
opposite ends.

Stating the default and leaving the field unset are not in tension, and the alternative —
PyGato stamping `7` into every session — is worse in a specific way. It would make
`VQL_STT__VAD_EAGER_FRAMES` decorative: every session would override it with a frame count
derived in the consumer, so recalibrating the deployment would take a PyGato change and a
PyGato deploy while the speech env var went on claiming to control something. Unset keeps
the calibration where the mapping is.

What this buys: **no default patience is written on the wire**, no existing session changes
behaviour, and the rollout is inert until a brain opts in. Make the inertness a test — an
unset patience must be byte-identical to today on both the connect and mid-call paths.

The honesty risk is drift. If an operator sets `VQL_STT__VAD_EAGER_FRAMES` to a value that
is not `update_frames + 1 + 7`, then "the default is 7" quietly stops being true of that
deployment. This does not deserve a boot failure — an operator overriding the calibration is
a legitimate thing to do — so speech logs the patience its configured `eager_frames`
corresponds to at boot, and says so when the value is not a whole patience step. A
deployment that has moved off the default is then visible in its own startup log rather than
only in this sentence.

Consequence to handle: `Resolved` (`pygato/session_config.py:99`) currently documents itself
as having *"no unset field — the pipeline is built from concrete values"*. `patience: int | None`
weakens that sentence. It is the right trade — patience is **forwarded**, not used to
construct anything — but amend the docstring rather than leaving it false. `IdleConfig`
already shows the file distinguishing unset from zero.

### It applies immediately mid-call, with no deferral

`eager_frames` is read at one site, `_step_in_turn`, and compared against `_silence_run`, a
self-resetting counter. That is the same property §11.2 uses to justify applying
`eot_threshold`/`eot_timeout_ms` live. Walking the phases:

- **LISTENING** — not read. Applies from the next turn.
- **IN_TURN** — the next silence frame compares against the new bar. If patience *drops*
  while `_silence_run` already exceeds the new value, `_enter_ending()` fires on the very
  next frame. That is correct, not a glitch: the caller asked to be less patient and the
  pause already qualifies.
- **ENDING** — `_step_ending` does not read it. A turn already ending is unaffected; the
  change governs the next one.

Neither reason that defers `language_hints` applies: there is no per-turn decoder state and
nothing is read lazily at segment dispatch. **Apply immediately.** Do not build a deferral
mechanism for it — the deferral in `_commit_turn` exists for engine-swap and re-decode
hazards that patience does not have, and putting patience through it would add a queue for
no reason.

One ordering hazard to test: a Configure landing mid-pause must not let the eager gate fall
below the `== update_frames` flush check, which is a `==` and fires once per pause. The
invariant guarantees it (`eager > update` always), which is another reason to derive the
floor rather than hardcode it.

### Validation lands at every seat that already validates, each with a different job

| seat | checks | failure |
|---|---|---|
| SDK `Config.__post_init__` (`voqalize/sdk/.../frames.py`) | `patience` in `0..=10` | `ConfigError`, at the brain author's keystroke |
| PyGato `refusal()` (`pygato/session_config.py`) | `patience` in `0..=10` | a sentence → 400 at connect, `STATUS_REJECTED` `Response` mid-call |
| speech `TurnConfig.__post_init__` | `update_frames < eager_frames` | `ConfigureFailure` / upgrade refusal |

PyGato's is the authoritative one, because it is the seat the connect and mid-call paths already share. Word the
sentence like its `MAX_IDLE_TIMEOUT_MS` neighbour: name the value, say the range, say what
each end means.

The speech-side check should be **unreachable from the wire** once the boot check below
exists, and should stay in as a guard. Implement it by rebuilding rather than mutating:

```python
self._cfg = dataclasses.replace(self._cfg, eager_frames=n)   # re-runs __post_init__
```

Note that the existing `TurnDetector.configure` mutates `self._cfg.combine_min_frames` in
place (`turn_detector.py:401`), which is safe only because that field *"takes no part in
TurnConfig's invariants"* (`turn_config_from_settings` docstring). `eager_frames` does take
part. Do not copy the in-place pattern.

**Extend `_validate_turn_shape` to sweep the whole patience range at boot**, not just the
configured `eager_frames`. That is what converts "a client could send a patience this
deployment cannot honour" into "this deployment refuses to start". Given the derived
mapping it is true by construction, so the check is cheap and it pins the property against
someone later reintroducing a hardcoded floor.

### Name it `patience`

Recommend keeping it. It says what it is in the caller's own terms, it is the word the user
reached for unprompted, and the proto's house style is already plain-English nouns with the
mechanism explained in the comment (`timeout_ms`, `through_turn`, `heard_text`).

The direction objection is real — higher `patience` means *slower*, where most tuning knobs
go faster as they go up — but it is inherent to the concept, not to the word, and any
synonym inherits it. `eagerness` inverts it and reads worse against the code it controls
(`EagerEndOfTurn` is the thing that fires *sooner*, so `eagerness=0` firing later would be
its own trap). Fix the direction problem in the comment, which is where this codebase fixes
things:

> How long the recognizer waits through a pause before it decides the caller has finished.
> Higher waits longer. `0` answers as soon as it can and will sometimes cut a slow speaker
> off mid-thought; `10` lets a caller finish and costs a beat on every turn. An interviewer
> wants the top of this range, a support bot the bottom. Unset takes Voqalize's calibration.

Name the endpoints in the SDK docstring too. The scale is meaningless without them.

---

## The shape of the change, repo by repo

### `voqalize/` (public)

`proto/voqalize/frames/frames.proto` — `optional uint32 patience = 2;` on `SttConfig`, with
the comment above. `SttConfig`'s own header (*"Applies once the open turn commits, never
mid-utterance"*) stays true for patience.

`sdk/python/.../wire/frames.py` — `patience: int | None = None` on `SttConfig`; range check
raising `ConfigError`. The check belongs on `SttConfig.__post_init__`, not `Config`'s —
`Config.__post_init__` exists for a cross-section rule, and this one is local to its
section.

Regenerate the stubs; the vendored copies in `platform` are separate and come later.

### `speech/`

`flux/query_params.py` — `patience: int | None` on `FluxQueryParams`, `ge=0, le=10`, and an
entry in the `_int_param` validator list. Amend the module docstring, which currently states
that all turn-timing tuning lives in deployment settings.

`flux/protocol.py` — `patience` as a **top-level field on `FluxConfigureFrame`**, beside
`language_hints`, *not* inside `FluxConfigureThresholds`. §11.2 says `thresholds` carries
"exactly Deepgram's three turn-commit fields and nothing else"; keeping that sentence true
while adding a vql extension is free, and §11 is literally titled *"Additions to the
Deepgram Flux protocol"* with `eot_reason` and `Boundary` already living there.

`flux/turn_detector.py` — `patience` → `eager_frames` via `dataclasses.replace`;
`TurnDetector.configure` gains the parameter. `git show 59d70eb -- src/vql_speech/flux/turn_detector.py`
is the prior implementation; read it, then do the `replace` version rather than its in-place one.

`server/flux_route.py` — seed from the query param at connect, apply from `Configure` mid-call.
`turn_config_from_settings` gains an optional `patience` override, keeping it the one place
settings become a `TurnConfig`.

`server/app.py` — `_validate_turn_shape` sweeps the range.

`docs/flux-v2.md` — §6 knobs table, §11.2 rewritten (it currently asserts the surface is
Deepgram-only), §10 drift list. `docs/turn-detection-findings.md` — correct the `2b0148f` line.

### `platform/backend/pygato/`

`session_config.py` — `patience` through `refusal()` and `Resolved`; amend the `Resolved`
docstring.

`stt.py` — the real work.
- `_build_query_string` appends `patience` when set, beside `language_hint`.
- The `Configure` at `:280` carries `patience` when the delta names one.
- **`_PendingConfigure` currently carries only `language`**, and every message on the
  failure path is worded in terms of it — `_settle_configure` says *"the recognizer refused
  {pending.language.value!r}"*, `_expire_configure` says *"this session is still listening
  in {…}"*. A patience-only Configure has no language to name. Give `_PendingConfigure` a
  description of what it was about and word the failures from that.
- **`_settle_configure(accepted=True)` assigns `self._language = pending.language`.** A
  patience-only Configure must not move the language — that field also decides what a
  reconnect comes back in. Either carry the current language on a patience-only pending, or
  make the assignment conditional. This is the sharpest bug in the whole change.
- `_build_query_string` matters for **reconnects**, which must come back with the same
  patience. Test that.

`session.py` — pass the resolved patience into `VqlSpeechSTTService`. The comment at `:549`
declining client-side EOT tuning needs rewriting rather than deleting: it is still right
about `eot_threshold`, and now wrong about turn shape. Say which is which and why.

### `platform/backend/controlplane/`

Likely **nothing**. `parse_session_config` parses canonical proto3 JSON and deliberately
re-types no knowledge (*"Parsing is not validating"*), so a new proto field arrives for free
once the vendored stub is updated. Confirm the vendored `app/platform/wire/_frames_pb2.py`
is refreshed and the docstring listing what connect validates is still accurate.

---

## Release order, which is not optional

Independent hazards force the sequence.

**The vendored-proto rule.** A `.proto` change needs the SDK published to PyPI *before*
consumers go green — two stubs of one `.proto` collide in the descriptor pool.

**The `forbid`/`ignore` split.** If PyGato sends `patience` to a speech tier that does not
know it: the connect path **400s the upgrade** (`extra="forbid"`) and the mid-call path
**silently swallows it** (`extra="ignore"`). A PyGato-first rollout takes calls down on one
path and lies on the other. Speech ships first, and the gap between the deploys is a period
where the field is accepted and inert — which is exactly what makes it safe.

Also note: **PyGato local dev points at the shared dev GPU**
(`platform/backend/pygato/deploy/env/local.env:21` → `wss://speech.dev.voqalize.com`), so
speech-dev must be deployed before anyone can test PyGato locally. There is no local speech
tier in that path.

Order: **speech → proto+SDK → PyPI → PyGato → control plane stub refresh.**

`speech` and `voqalize/proto` are independent of each other and can run in parallel; each
must land before PyGato.
