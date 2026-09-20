# `patience` — task board

Companion to `patience.md`. Read that first; this sequences it. One commit per repo —
these are sibling repos, not a monorepo.

**Decided, so nothing here is blocked:** speech owns the patience → `eager_frames`
mapping and PyGato forwards the scale verbatim; the documented default is `patience = 7`,
delivered by leaving the field unset so the deployment's calibration still decides.
`eager_frames = update_frames + 1 + patience` gives 11..21 frames (~352..672 ms) on the
deployed `update_frames=10`, and today's `eager_frames=18` is exactly patience 7.

---

## `speech/` — ships alone and inert

Nothing downstream can be tested until this is deployed to speech-dev, because PyGato
local dev talks to the shared dev GPU.

- [x] Read `git show 59d70eb` and `git show e373353` in full before writing anything.
      The first is a working implementation of this exact mechanism; the second is its
      clean removal and names every seat.
- [x] `flux/query_params.py` — `patience: int | None`, `ge=0, le=10`; add to the
      `_int_param` validator list. Amend the module docstring, which currently claims all
      turn-timing tuning is deployment-only.
- [x] `flux/protocol.py` — `patience` as a top-level field on `FluxConfigureFrame`, beside
      `language_hints`. **Not** inside `FluxConfigureThresholds` — that stays Deepgram-pure.
- [x] `flux/turn_detector.py` — `TurnDetector.configure(patience=…)`, applied as
      `self._cfg = dataclasses.replace(self._cfg, eager_frames=…)` so `__post_init__`
      re-validates. Do not copy the in-place mutation used for `combine_min_frames`.
- [x] `server/flux_route.py` — derive `eager_frames = update_frames + 1 + patience`;
      seed from the query param at connect, apply from `Configure` mid-call. Keep
      `turn_config_from_settings` the one place settings become a `TurnConfig`.
- [x] `server/app.py` — `_validate_turn_shape` sweeps the whole patience range, so an
      unhonourable range fails the container instead of some later session.
- [x] `server/app.py` — log the patience the configured `eager_frames` corresponds to at
      boot, and say so when it is not a whole patience step. An operator may legitimately
      override the calibration; when they do, "the default is 7" stops being true of that
      deployment and the startup log is where that should be visible.
- [x] Tests:
      - [x] reducer: patience changed in LISTENING / IN_TURN / ENDING, including a drop
            mid-pause where `_silence_run` already exceeds the new bar (expect
            `_enter_ending` on the next frame).
      - [x] the `== update_frames` flush still fires once per pause at every patience.
      - [x] e2e through `tests/unit/server/test_flux_configure_e2e.py` — the rig from
            `59d70eb` is still standing; a mid-call patience drop visibly speeds up
            `EagerEndOfTurn`.
      - [x] connect-path query param, including out-of-range → upgrade refused.
      - [x] an unset patience is byte-identical to today.
- [x] Docs: `flux-v2.md` §6 table, §11.2 (rewrite — it currently asserts the surface is
      Deepgram-only), §10 drift list.
- [x] Docs: correct the stale `2b0148f` line in `turn-detection-findings.md`, which claims
      `barge_in_ms` "and its neighbours" are already settable on the wire. They are not,
      and have not been since `e373353`.
- [x] Commit message cites `e373353` by hash and states that its reason — *"a knob no
      producer writes is not a feature"* — is what has now changed.
- [x] `just check` green.
- [x] Deploy speech-dev. **Nothing downstream is testable before this.**

## `voqalize/` — proto + SDK, runs in parallel with `speech/`

- [x] `proto/voqalize/frames/frames.proto` — `optional uint32 patience = 2;` on
      `SttConfig`, with the endpoints named in the comment.
- [x] Regenerate `proto/gen/`.
- [x] `sdk/python/.../wire/frames.py` — `patience: int | None` on `SttConfig`; range check
      raising `ConfigError` on `SttConfig.__post_init__` (not `Config`'s — that one exists
      for a cross-section rule).
- [x] Docstring names both endpoints and says what unset means. A scale is meaningless
      without them.
- [x] Tests: roundtrip, `ConfigError` at each end of the range, unset stays unset.
- [x] Gates: `ruff format --check`, `ruff check`, `pyright`, `pytest`.
- [x] **Publish the SDK to PyPI.** The vendored-proto rule: two stubs of one `.proto`
      collide in the descriptor pool, so this lands before any consumer goes green.

## `platform/backend/pygato/` — after speech-dev is deployed and the SDK published

- [x] Refresh the vendored `src/pygato/wire/_frames_pb2.py`. Pin the SDK from PyPI at the
      exact released version, never the sibling checkout.
- [x] `session_config.py` — `patience` through `refusal()` (authoritative range check,
      worded like its `MAX_IDLE_TIMEOUT_MS` neighbour) and onto `Resolved` as
      `int | None`. Amend the `Resolved` docstring, which currently promises no unset field.
- [x] `stt.py`:
      - [x] `_build_query_string` appends `patience` when set, beside `language_hint`.
      - [x] the `Configure` at `:280` carries `patience` when the delta names one.
      - [x] **`_PendingConfigure` carries what it was about, not just a language.** Every
            message on the failure path currently names a language
            (`_settle_configure`, `_expire_configure`); a patience-only Configure has none.
      - [x] **`_settle_configure(accepted=True)` must not move `self._language` on a
            patience-only Configure.** That field decides what a reconnect comes back in.
            This is the sharpest bug in the change.
- [x] `session.py` — pass resolved patience into `VqlSpeechSTTService`. Rewrite the `:549`
      comment declining client-side EOT tuning: still right about `eot_threshold`, now
      wrong about turn shape.
- [x] Tests:
      - [x] `refusal()` at each end of the range and outside it, on both the connect and
            mid-call paths.
      - [x] a patience-only Configure leaves the language alone.
      - [x] a reconnect comes back at the same patience.
      - [x] a rejected patience reaches the brain as `STATUS_REJECTED`, not a session end.
      - [x] unset sends nothing on either path.
- [x] `AGENTS.md` (the `CLAUDE.md` beside it is a **symlink** — edit the AGENTS.md;
      `perl -pi` silently replaces symlinks with regular files).
- [x] Gates green. `2005 passed, 73 skipped, 8 xfailed` in 28:09, every gate RAN —
      `journal · realtime · recording · turn · wire`. The lockfile change selects all of
      them, so this is the `--gates=all` shape rather than the 56-second core, and the
      run itself printed why: "a dependency or harness file changed".

## `platform/backend/controlplane/` — last code change

- [x] Refresh the vendored `app/platform/wire/_frames_pb2.py`.
- [x] Confirm **no validator change is needed** — `parse_session_config` re-types no
      knowledge by design, so the field should arrive for free. Verify rather than assume.
      **Verified, and the expectation was wrong.** Parsing arrives for free: the field
      lands with no change, because the vendored stub carries it. The *range* does not —
      proto3 spells `uint32`, not `0..10` — so `_require_a_patience_on_the_scale` was
      added to `session_service` beside the voice/language pairing, which is the seat
      that already holds the rules the message cannot state. An unset patience is still
      not filled in here; resolving it stays the speech tier's.
- [x] Check the module docstring listing what connect validates is still accurate.
- [x] Gates green.

## Verify on a live call

The standing rule: two wire-v3 defects passed 659 tests and only a live call caught them.

Platform `main` is at `e66db354` as of 2026-09-21 — the PyGato and control-plane change
rode out with two commits that were already stacked on `origin/main` and were not mine
(`6678f159`, `3af82c38`), as a fast-forward from `dae73ab9`. That push is what deploys the
control plane to dev, which is what makes the items below possible at all.

Driven from `platform/frontend/e2e/calls/patience.spec.ts` against dev, through the
public Travel demo page on the apex rather than the console Playground — the dev
console cookie has expired and the calls suite never signs in on dev by design. The
brain is `calls/brain/e2e_brain.py`, an echo that asks for a patience only when the
test hands it one, so nothing on the path is faked: the ask crosses the SDK, Cortex,
PyGato and the speech tier. Two clocks per turn, both off the probe's RTVI tap:
`speak-end` → the last `user-transcription` before the reply, and `speak-end` → the
bot's first audio. The transcript clock is the one asserted on; the reply clock
carries the brain, the model and the synthesizer inside it and jitters by more than a
patience step is worth.

- [x] A brain sets `patience` at connect; confirm the turn-end floor moved. Measured on
      dev, four echo turns each, same clip, back-to-back sessions:
      patience 0 → 532.5 ms to transcript (918 ms to reply); patience 10 → 726.5 ms to
      transcript (1111.5 ms to reply). **Delta 194 ms**, and the reply clock moves with
      it. Sessions `913ed317` and `f3c1d109`, both `ended` / `user_hung_up`.
- [x] The same brain changes it mid-call; confirm the change lands on the next turn and
      the call survives. One session, turn one at patience 0 and the brain raising it to
      10 as that turn finishes: turn 1 → 540 ms to transcript, turns 2+ → 730 ms median.
      **The same 190 ms, on the same socket.** The brain logged `patience-shifted 10`,
      nothing was refused, and the call took every turn after it. Session `503dfc01`,
      `ended` / `user_hung_up`, `error: null`, files complete.
- [x] An out-of-range patience at `sessions.connect` comes back as a rejection the
      developer can read. Probed on dev once `e66db354` was serving:
      `{"stt":{"patience":99}}` returns `400 invalid_config` carrying
      `_require_a_patience_on_the_scale`'s own sentence — "it is a scale, not a duration
      in milliseconds" — rather than protobuf's "has no field named". Before the deploy
      the same request returned the descriptor error, so this also dates the rollout.
- [x] An out-of-range patience in a mid-call `Config` comes back as a readable
      `RequestRejected` and the call continues. **Not reachable from a Python brain, and
      that is the answer rather than a gap.** `SttConfig.__post_init__` raises
      `ConfigError` in the brain's own process, so 99 never reaches the socket: the live
      call proves the door a brain author actually meets, and PyGato's wire refusal is a
      backstop for clients that are not this SDK, covered by its own unit tests. The
      brain logged `patience-refused-locally 99` with the range in the reason, never
      `patience-rejected`, and kept taking turns. Session `d0b39a2d`, `ended` /
      `user_hung_up`. The docs should keep describing the wire refusal where they
      describe the wire, and `ConfigError` where they describe the SDK — which is how
      voqalize-83 placed it.
- [x] A brain that sets nothing behaves exactly as before. `pnpm smoke:dev` green
      against the deployed control plane — `2 passed in 36.8s`: the session comes up and
      the desk speaks first, then a join, an interrupt of the greeting and two screen
      actions. Real Chromium, real audio, real brain; the travel demo sets no patience,
      so this is the unset path end to end.

## The docs, in the interim

The catalog page was asserting there are no end-of-turn knobs on the wire while 0.5.0 on
PyPI already autocompleted `patience` — live and false, because `ci-web.yml` stages from
`main` and the apex picks it up. Holding the full copy until the deploy was not the neutral
option it looked like; it was choosing the wrong state that was already shipping. `5c7d449`
takes the absolute claims out and leaves the policy sentences standing, which is true before
the deploy and after it. The paragraphs that describe the knob follow with the deploy.

`reference/brain.md` deliberately stays untouched until then. Its `stt` enumeration and its
timing sentence are both descriptions of a documented surface rather than claims about the
wire, so they say nothing false to a reader the page has not yet told about `patience` —
adding the field early would be the same interim falsehood pointing the other way.

**The interim is over.** voqalize-83 placed the full copy in `1c1bee5` on `main`, gates
green: the field and both refusal paths in `reference/wire.md`, the enumeration and the
split timing bullet in `reference/brain.md`, the connect JSON and its prose in
`build/session.md`, the argument in `reference/catalog.md`, and `stt.patience`'s range and
default in `design/facts.yaml` — the default carrying its derivation rather than the bare
number, which is what gets it past the house rule on counts.

## Found while verifying: the blanket `stt` timing claim

`Session.configure`'s docstring lands the whole `stt` section "once the open turn
commits". That is `stt.language`'s rule, and `patience` does not follow it —
`SttConfig`'s own docstring, two modules away in the same package, says so. **Both
sentences shipped in 0.5.0**, contradicting each other, in the method a brain author
actually calls. `sdk/python/.../brain.py` now splits the bullet into `stt.language` and
`stt.patience`; it is a docstring, so it carries no behaviour and renames no export.

The same claim was made in two more places, both of which voqalize-83 has now fixed in
`1c1bee5`: the "Acceptance is not audibility" bullet in `reference/brain.md`, and the
landing-points table in `reference/wire.md`, whose timing column the copy I first sent did
not cover — corrected to them separately and renamed rather than patched.

## Found while verifying: the floor moves less than the frame arithmetic predicts

Across the whole scale the measured floor moves **~190 ms**, reproducibly, on three
separate runs and on both the connect path and the mid-call path. The configured gate
moves 10 frames over that range, and a frame is 32 ms, so the arithmetic predicts
~320 ms. The direction and the reproducibility are not in question; the magnitude is
about 60% of nominal.

This contradicts nothing we publish — no millisecond figure is customer-facing, by
design, and that is exactly the kind of retune the abstract scale exists to absorb. It
does mean the `~352..672 ms` in `eager_frames_for_patience`'s docstring describes the
gate rather than the floor a caller experiences, which is true but reads as a promise.

Unverified hypothesis, for whoever owns the speech calibration: something ends the turn
before the eager gate at high patience — the smart-turn model, or a segment flush — so
patience raises a ceiling the turn does not always reach, and its effect saturates. Not
proven, and not provable from the browser: it needs the flux-side event stream.

## After it is proven

- [ ] Decide whether `VQL_STT__VAD_EAGER_FRAMES=18` should stay the deployment
      calibration now that agents can opt out of it per session. Probably yes — it is the
      safe default and the evidence behind it has not changed.
- [ ] Docs on `docs.voqalize.com` (design.md — turns, interruption, screen actions).
- [ ] Consider whether the marketing agent wants a low patience. **Separate session; not
      part of this work.**

---

## Decisions taken (2026-09-20)

- **Mapping ownership: speech.** PyGato forwards `patience` and never computes a frame
  count. The formula lives in exactly one function, `eager_frames_for_patience`.
- **Default: 7, delivered as unset.** No default patience is written on the wire; unset
  means the deployment's calibration, which is patience 7 on dev and prod. Every
  docstring states 7.
- **`patience=0` is 11 frames, not 10.** The invariant is strict and `update_frames=10`
  is deployed, so the range is ~352..672 ms — one frame (32 ms) off each endpoint
  originally sketched. Accepted.
- **The name stays `patience`**, with the direction explained in the comment.

## Not verified

- Whether any non-PyGato client of the Flux surface (the playground, `speech/web/`) would
  need to know about `patience`. `e373353` says the playground sends no Configure, so it
  should be unaffected — not confirmed by reading it.
- Whether `docs.voqalize.com` has a page enumerating `SttConfig` fields that would go
  stale. Docs live in `voqalize/docs/`; not swept.
- The TypeScript/JS client side. `SttConfig` is set by the brain, not the browser, so it
  should not surface there — not confirmed.
