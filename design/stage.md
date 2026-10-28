# Stage — build contract (v1, branch `feat/stage`)

Internal. This is the contract the Python director, the TypeScript runtime and the first
two ports (explora, cannonhome) are built against. The architecture this implements is the
"Stage Architecture" design (owner-approved 2026-10-28). Nothing here is published to PyPI
or npm yet.

## Where things live

| Piece | Path | Notes |
|---|---|---|
| Python director | `sdk/python/src/voqalize/sdk/stage/` | `voqalize.sdk.stage`; NOT added to `voqalize.sdk.__all__`. Pydantic only; pyright strict. |
| Policy + wire (fixed) | `stage/policy.py`, `stage/wire.py` | Written. `wire.gen.ts` is generated from `wire.py`. |
| Page runtime | `sdk/js/stage/` | npm `@voqalize/stage`, `"private": true` until release. ESM TypeScript. Subpaths `.` (core) and `./extension` (Chrome extension host). |
| Ports | `demos/explora/`, `demos/cannonhome/` | Each keeps its own brain, routes, knowledge and extension; their copies of cues/narration/holder/relay/etc. are deleted in favour of Stage. |

Regenerate the page types after changing `wire.py`:
`cd demos && uv run voqalize types voqalize.sdk.stage.wire -o ../sdk/js/stage/src/wire.gen.ts`

## Ground rules that bind the code

1. The model names, the runtime moves. No selector, wait or click order ever comes from the model.
2. Class (look | navigate | reversible | confirmed — `policy.py`) decides delivery, retries, what the model hears. `commit` = human only, never a move.
3. Every visible move rings its target before it acts (the **spotlight**). `ring()` holds the move only a short beat (`beatMs`, 450 ms; per call `{beatMs}`), so a fast reply never leaves the screen behind the voice; the ring itself stays visible ≥ `dwellMs` (1.5 s) — a display guarantee, not a wait: a `clear()` inside it waits it out — unless the next ring replaces it. A move that changes the page without a ring is a bug.
4. Every move — cue or tool — gets exactly one final `StageResult` per `call_ref`, under the move id it was minted for, also when the page carried it to the next page and another performer finished it there. The brain times out a missing one as `unknown`, after a timeout by class (`RESULT_TIMEOUTS`).
5. The page segments words; the brain never does. Anchors work in any script (Latin with accents, Devanagari, CJK, Arabic).
6. Never hold the voice for the page. (The extension holder keeps playing across loads.)
7. `@voqalize/stage` takes a PipecatClient that already exists and only subscribes/sends. It never constructs, connects, wraps or re-exports pipecat's client or hooks. It names no pipecat type in its API either: it writes out what it uses (`StageClient`: `on`/`off`, `sendUIEvent`; the holder's `HolderClient`), so a `PipecatClient` of any copy or version in the peer range (`>=1.13 <2`) fits with no cast and no `paths` alias.
8. No internal service names (gato, pygato, vql-*) in SDK or package prose.

## Cue grammar (model output)

```
cue  := "{" verb [ ":" SP arg ( SP? "|" SP? arg ){0,3} ] "}"
verb := [a-z]{2,12}     one lowercase word; no underscore/dot/digit; never one of the SDK's
                        _CALL_KEYS (name function tool call args arguments action parameters)
arg  := ≤ 80 chars, no braces/newline; trimmed
```
- A cue goes right before the first word of the sentence it belongs to. Several cues before
  one sentence share its anchor and fire in order.
- Anything else in braces is not spoken either (as today). An unclosed brace is dropped once
  it runs past 220 chars, and the text is spoken.
- The verbs a reply may use are the brain's registered moves' verbs. Unknown verbs are dropped
  (logged, and told to `on_drop`), never spoken.
- Sentence ends (brain side, for anchoring and backstop): `. ! ? … 。 ！ ？ । ॥` followed by
  whitespace, or the end of the unit.

## Anchors

- Brain sends `at` = the spoken text that follows the cue, raw (as the voice will say it,
  cues removed, whitespace collapsed), up to 48 chars, cut on a whitespace boundary when
  possible; empty when nothing follows in the unit. `before` = characters of the unit's spoken
  text before the cue. A cue is released to the wire once ≥ 3 whitespace-separated tokens (or
  ≥ 12 chars for scripts without spaces) have streamed after it, or at unit end.
- Page normalises with `normalize("NFKC")`, `toLocaleLowerCase()`, strips Latin combining
  marks only for comparison (NFD → remove U+0300–U+036F → NFC; Devanagari/other marks kept),
  maps ’ to ', then segments with `Intl.Segmenter(lang, {granularity: "word"})` keeping
  `isWordLike` segments. Fallback when `Intl.Segmenter` is missing: `/[\p{L}\p{M}\p{N}']+/gu`.
- Anchor = first 3 word-like segments of `at` (fewer if `at` has fewer). It fires when that
  sequence appears in the heard word stream at or after the search cursor; 2 of 3 consecutive
  is accepted after 1.5 s past the expected time (fuzzy), counted as `fuzzy` in telemetry.
- Heard stream = pipecat `botOutput` (preferred) / `botTtsText`, released as audio plays.
- Clock fallback when no spoken text has arrived 1.5 s into speech: fire at
  `before / cps` seconds from speech start; `cps` starts at 14 and is recalibrated from the
  session's own spoken-text rate.
- Empty `at` fires 600 ms after the voice stops. A cue whose words never come is dropped
  after 45 s. On `userStartedSpeaking` every cue not yet fired is dropped and reported
  `refused` with why `interrupted` (not sent to the model as a failure note).
- Cues fire in order, one move at a time (a page must arrive before a section on it). Each
  waits only for the move before it, whose rings hold it a beat each, not a dwell.
- A slow scroll never holds the cues behind it: `MoveContext.scrollTo` waits for a scroll at
  most `RING_SCROLL_MS` (800 ms), and a cue that fires while the move before it still runs
  (`Timeline` `onQueued`) hurries that move (`Moves.hurry()`, the holder's `hurry`), which
  stops waiting for its scroll at once. The ring follows its target wherever the scroll gets.

## Wire (see `wire.py`)

down `ui-command`: `stage_cue {call_ref, move, verb, args[], at, before, unit}` ·
`stage_move {call_ref, move, args{}, when: now|quiet}`
up `ui-event`: `stage_result {call_ref, move, outcome, detail?, refused[], moved, ms, fired?,
received_ms?, queued_ms?, fired_ms?, ringed_ms?, lag_ms?, late}` ·
`stage_progress {call_ref, move, phase, ms}` · `stage_hello {runtime, contract, url, title}`

Every field added since the first port is optional, so a page that does not send it still
parses. Result telemetry, all milliseconds from the page's receipt of the move: `received_ms`
to the result, `queued_ms` to being set off and queued (a cue: its words heard; a quiet move:
the voice quiet), `fired_ms` to the performer starting, `ringed_ms` to its first ring.
`fired` says how it was set off (`anchor | fuzzy | clock | end` for a cue, `now | quiet` for
a tool's move); `lag_ms` is a cue's start minus when its words were heard. `ms` stays the
performer's own time. `late` is set only by the director (below), never by a page.

`stage_progress` is never final. `phase ∈ queued | loading | waiting_site | ringing | acting |
confirming`; the runtime sends `queued` (behind another move, or kept for a page),
`loading` (kept for a tab whose page is loading; a carried move's next page is up), `acting`
(the performer started) and `ringing` (while a ring holds it); a performer adds
`waiting_site` / `confirming` with `MoveContext.progress()`. Each one gives the move its time
again at the director, so a slow move is not taken for a failed one.

`moved: true` is interim: the move's page went, and its next page owes the final result. The
extension's holder sends one as a carried move's page goes, and fails the move itself
(`failed`, "no page came up to finish it after the load") when no page reports it within
20 s of the load or of that page's last progress. A move whose page went without carrying
anything is never `applied`: it is `unknown` ("the page left while it ran", or "the page went
on to another before it said what it did"); one the page never started goes to the tab's next
page instead, once, and is `unknown` ("the page left before it ran") if that page goes too.

**A new page, in order** (extension): the holder keeps the jobs for a tab whose page is
loading; the next page says `hello`, waits for its site (`SiteHooks.ready()`, else the
document's `load`, at most 4 s), finishes the move the last page carried to it, and only then
says `ready` — and the kept jobs go to it, in the order they were asked for. A page that never
says `ready` gets them after 25 s with no progress from it. A page already ready when the
holder appears says so in its `hello`.
Site-specific typed Actions/AppEvents (page_changed, listing_shown, check_availability, …)
keep riding the same channels beside these. `command_done` / `command_failed` are replaced
by `stage_result`.

## Python director API (to build)

```python
from voqalize.sdk.stage import (
    Move, MoveClass, Stage, CueParser, RawCue, match_label, StageEvents, StageResult,
)

# A move the brain knows. Cue moves have a verb; tool-only moves have none.
Move(id="core.show", verb="show", cls=MoveClass.LOOK, args=("target",), say="...")
# A move may name the phrases that claim it in speech (the promise guard, below).
Move(id="site.check", verb=None, cls=MoveClass.REVERSIBLE, args=("lodge",),
     claims=("opening the * calendar", "abro el * calendario"))

class Stage:
    """Composable director. A brain owns one per session."""
    def __init__(self, *, dispatch: Callable[[Action], None], moves: Sequence[Move],
                 resolve: Callable[[Move, list[str]], list[str] | None],   # None = drop
                 backstop: AutoCues | None = None,
                 # one number, or by class; missing classes keep RESULT_TIMEOUTS
                 # (look 10, navigate 25, reversible 20, confirmed 30 s)
                 result_timeout_s: float | Mapping[MoveClass, float] = RESULT_TIMEOUTS,
                 # every cue not sent: why ∈ "unresolved" | "unknown_verb" | "too_many_args"
                 on_drop: Callable[[RawCue, Dropped], None] | None = None,
                 on_progress: Callable[[StageProgress], None] | None = None,
                 # every claim a turn made and did not keep: (move, phrase, sentence)
                 on_unkept: Callable[[Move, str, str], None] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None: ...
    def cued(self, turn: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        """Strip cues from SpeechChunks, resolve, dispatch StageCue with a fresh call_ref."""
    def send(self, move: str, args: dict, *, when: Literal["now","quiet"]="now") -> str | None:
        """Tool-delivered move: one at a time per policy.serial; returns the call_ref, or
        None when it was queued behind the running one (it is sent when that one answers)."""
    # overloads: StageResult -> StageResult | None; StageHello -> None;
    # StageProgress -> StageProgress | None
    def handle(self, event: StageResult | StageHello | StageProgress) -> ...:
        """Fold a result: clears the in-flight move, sends the queued one, returns the result
        (with outcome as received, `move` the one minted for its call_ref) so the brain can
        write its note; None for duplicates. A `moved` result is interim and restarts its
        time. A result for a move already reported `unknown` comes back once with
        `late=True` (finished call_refs are kept FINISHED_KEEP_S = 60 s). A progress for a
        running move extends its deadline (never shortens it) and comes back."""
    def timeout(self, cls: MoveClass) -> float: ...
    def move_of(self, call_ref: str) -> Move | None: ...  # rarely needed: results name it
    def expire(self) -> list[StageResult]:
        """Results that timed out, as outcome="unknown"."""
    def next_deadline(self) -> float | None: ...       # on the director's clock
    async def watch(self, on_expired, *, poll_s=0.25) -> None:
        """expire() as each deadline falls (≤ poll_s late), forever; one task per session."""
    def running(self) -> list[Running]: ...            # (move, call_ref, phase, seconds)
    def holding(self, after_s: float = HOLDING_LINE_S) -> list[Running]:
        """Confirmed/reversible moves past 6 s, each handed out once: one written
        holding line apiece."""
    @property
    def busy(self) -> str | None: ...   # the move in flight
    def begin_turn(self) -> None: ...      # optional: forget a turn cut off before it ended
    def end_turn(self) -> list[Unkept]:
        """After the turn's tool calls: each move it claimed and did not keep, once
        (Unkept(move, phrase, sentence)); logged and told to on_unkept. Starts the next turn."""
```
- Parse page events with `StagePageEvents` (result, hello, progress). `StageEvents` is the
  result/hello pair the first ports parse with, kept as it was; a brain on it never sees
  progress (and logs each `stage_progress` as an event it does not know).
- The director logs at INFO each cue sent (as written, its anchor and sentence), each drop
  (why, the cue as written, its sentence), each backstop decision (`added` with the cue and
  its offset, or `none` and why) and each result (outcome, `late`, detail, telemetry, and
  sent→answered time).
- `CueParser` generalises `demos/explora/backend/cues.py`: verbs from the registered moves,
  args split on `|`, raw `at`/`before` per the anchor rules, an `auto` backstop callback
  `(sentence, index, placed) -> Sequence[(verb, args) | (verb, args, offset)]`. An offset is a
  character offset into the sentence it was handed; the cue anchors at the word there, so a
  sentence naming four places rings four times, in order. Without one it anchors at the
  sentence's start. `placed` holds only the model's cues that will be sent: with a `check`
  (the director passes its resolver), each model cue is resolved when its sentence finishes,
  before the backstop is asked, and one that is dropped leaves the sentence to the backstop.
  A cue resolved there is not resolved again when sent: `RawCue.resolved` holds the
  resolved arguments, which go to the page, while `RawCue.args` stays as the model wrote it —
  what a brain shows the model of its own cue (and what the log prints), so the model keeps
  imitating its own grammar, never the page's ids (`{filter: Tamaño | king}`, not
  `{filter: tamano | King | /12-…}`).
- `match_label(want, options) -> str | None`: NFKC + casefold + Latin-accent-insensitive; exact,
  then unique prefix, then best token overlap ≥ 0.6; None when ambiguous.
- `StageBrain` is optional sugar for simple brains; explora/cannonhome compose `Stage` inside
  their own respond pipelines.
- **The promise guard.** A voice that says "I'm opening the calendar" and makes no call
  is worse than silence, and a backstop ring under it makes the false claim look true (dev
  call 2f94965e, twice in one call). `Move.claims` are short phrases, any language, that
  assert the move is happening. They are matched on the turn's spoken text as the parser
  released it to the voice (cues out), per sentence, folded like `match_label` (NFKC,
  casefold, Latin accents off) and on whole words: "reopening it" is not "opening it".
  `*` stands for up to `CLAIM_GAP` (3) words ("opening the * calendar" hears "opening the
  Atacama calendar"). A question is an offer, not a claim. A claim is kept when its move
  was cued or `send`-ed this turn (queued and refused-as-running count), is still running
  or queued, or was answered during the turn. Write claims as announcements ("opening",
  "abro"): a past tense is also true of a move an earlier turn made. The director does not
  know turns by itself: the brain calls `end_turn()` when its turn is over — after the
  model's tool calls, which come at the end of its response — and `begin_turn()` at the
  start if a turn may have been cut off. What to do with an unkept claim is the brain's:
  explora appends "[You said you were <phrase> but did not do it. Call <tool> now, or say
  plainly you have not.]" and asks the model once more with its tools, never more than once
  a turn; what that follow-up claims is only logged.
- **Barge-in and tool moves.** When the visitor starts speaking, the page drops every cue
  not yet fired (`refused`, why `interrupted`, never a failure note). A tool move is not a
  cue: it was asked for by a call the model already made, so it is **kept** — it runs to
  the end (a `quiet` one still waits for the voice to be quiet) and is **reported by its
  result**, like any other, which the brain folds into the context for the next turn. It is
  never cancelled by speech; only its timeout ends it unanswered (`unknown`, then `late`).
- Floor policies (nod, silent-turn line, fallback) stay in `demos/voqalize_demos/` — the team
  kept fillers out of the SDK.

## Page runtime API (to build)

```ts
// @voqalize/stage
export * from "./wire.gen";
export function words(text: string, lang?: string): string[];          // the one segmenter
export class Timeline { constructor(fire: (cue: StageCue) => Promise<StageResult | void>, opts?: {lang?: string; now?: () => number});
  add(cue: StageCue): void; hear(text: string): void; speaking(): void; stopped(): void;
  interrupted(): StageCue[]; clear(): void; }
export interface SpotlightTheme { color: string; width?: number; radius?: number; glow?: string;
  beatMs?: number /* 450: how long ring() holds the move */; dwellMs?: number /* 1500: least a ring is visible */;
  holdMs?: number; pad?: number }
export interface RingOptions { label?: string; beatMs?: number; dwellMs?: number; separate?: boolean /* one box per element */ }
export class Spotlight { constructor(theme: SpotlightTheme, doc?: Document);
  ring(target: Element | Element[], opts?: RingOptions): Promise<void>;   // resolves after the beat
  clear(): void; }  // waits out a young ring's dwell; shadow-root overlay in document coordinates; follows scroll/resize; never restyles the site; aria-live label; reduced-motion aware
export function locate(spec: Locator, root?: ParentNode): Element | null;   // any_of strategies, unique-or-null
export function reveal(el: Element): Promise<void>;     // open closed tab/accordion/details/carousel hiding it
export function scrollToEl(el: Element, opts?: {align?: "top"|"center"; fixed?: string[]}): Promise<void>;
export function press(el: Element): void; export function setValue(el: Element, v: string): void;
export function waitFor<T>(fn: () => T | null | false, ms: number): Promise<T | null>;
export function quiet(el: Element, quietMs: number, maxMs: number): Promise<void>;
export interface PerformResult { outcome?: "applied" | "partial"; detail?: string | null; refused?: Refusal[] }
// detail, or a PerformResult (refused[] with no outcome = partial); null = moved on to another page
export type Performer<A> = (args: A, c: MoveContext) => Promise<string | null | PerformResult>;
export interface MoveContext { move: string; callRef: string; spotlight: Spotlight; reveal(el: Element): Promise<void>;
  ring(el: Element | Element[], opts?: string /* label */ | RingOptions): Promise<void>; beat(ms?: number): Promise<void>;
  scrollTo(el: Element): Promise<void>;   // waits ≤ RING_SCROLL_MS (800), cut short by hurry()
  refuse(arg: string, why: string, options?: string[]): never;
  progress(phase: Phase): void;           // waiting_site | confirming (the runtime says the rest)
  // With a Carrier (the extension): load url; `then` runs on the next page under this move's id and
  // call_ref, or, without it, the move is applied once that page is up on the expected host/path
  // (partial, saying where, when it is not).
  loadThen?(url: string, then?: {move: string; args: unknown}): Promise<never>;
  // A press that may load a page: keep the rest for the next page / discard it. A move that ends on
  // this page drops what it kept by itself. No-ops without a Carrier.
  keep(then?: {move: string; args: unknown}): Promise<void>; drop(): Promise<void>; }
export interface Carrier { keep(c: Carried): Promise<void>; drop(callRef: string): Promise<void>; load(url: string): void }
export class Moves { constructor(spotlight: Spotlight, opts?: {fixed?: string[]; carrier?: Carrier;
    onProgress?(p: StageProgress): void});
  register<A>(id: string, cls: MoveClass, performer: Performer<A>, opts?: {params?: string[]}): void;
  // one at a time; builds the Result with its timings from `receivedAt` (epoch ms, default now)
  run(id: string, args: unknown, call_ref: string, opts?: {receivedAt?: number}): Promise<StageResult | null>;
  resume(c: Carried): Promise<StageResult | null>;   // finish a carried move on the page it reached
  listen(fn: (p: StageProgress) => void): () => void; hurry(): void; }
// Timeline's fire callback gets (cue, info: FireInfo {how, heardAt, firedAt}); withFire(result,
// info, receivedAt) stamps fired / queued_ms / lag_ms. scrollToEl takes {maxMs, signal}.
export interface StageClient { on(event: string, h: (...a: any[]) => void): unknown;
  off(event: string, h: (...a: any[]) => void): unknown; sendUIEvent(event: string, payload?: unknown): void }
export function attachStage(client: StageClient, opts: { onCue(c: StageCue): void; onMove(m: StageMove): void;
  onSiteCommand?(command: string, payload: unknown): void }): { send(ev: StageResult | StageHello | StageProgress): void; detach(): void };
```
`@voqalize/stage/extension` — the Chrome MV3 host shared by every site extension, extracted
from explora + cannonhome: offscreen holder (call, tab registry, routing to the front tab,
moves kept for loading tabs / `loadThen` across hosts, Timeline), relay/follow/catch-up/
mouth-clock for the avatar, call-client, grant flow, page bridge/hub, shell/persist, widget
shell. Site extensions provide: config (hosts, agent, theme, languages, widget copy), their
site adapters registered with `Moves`, and their site AppEvents. An adapter returns
`SiteHooks`: `context()` for the session's start, `report(emit)` (the page as it stands — run
once the call can hear the page and again whenever the tab comes back to the front; the host
owns the `visibilitychange`/`focus` listening), `start(emit)` (watch and report changes),
`command()` for site Actions, and `ready()` (optional: resolves once the site's own scripts
can take a press; nothing is pressed on a new page before it). The holder's `makeClient` returns a `HolderClient` (structural:
the site's own `PipecatClient` fits), and `avatar.create` gets the stand-in client typed loosely
(`AvatarClient`) so it passes as whichever `PipecatClient` the site's avatar package wants.

## Gates

```
uv run ruff format --check . && uv run ruff check . && uv run pyright
cd sdk/python && uv run pytest -q
cd demos && uv run pytest tests/test_explora*.py tests/test_cannonhome*.py   # + the cross-demo voice contract
cd sdk/js/stage && pnpm typecheck && pnpm test   # incl. catch-up, mouth clock, client types
cd demos/<site>/extension && pnpm install --ignore-workspace && pnpm typecheck && pnpm build && pnpm test:e2e
```
