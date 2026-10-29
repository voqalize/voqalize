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
   The ring-before-act rule is for the act. A move **reports as soon as its visible effect
   lands**: a ring that only points at the effect (the grid it filtered, the product it opened,
   the calendar it showed) trails the result, through `MoveContext.done(result)` or
   `MoveContext.after(fn)`. The next move still waits for it; the agent does not.
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
loading; the next page says `hello`, waits for its site (`SiteHooks.ready()`, at most 4 s;
without one, `domSettled()`: the DOM parsed and then still for 300 ms, at most 1.5 s —
**never the document's `load`**, which a site's trackers hold back for over 15 s; the host
warns once per adapter that gives no `ready()`), finishes the move the last page carried to
it, and only then says `ready` — and the kept jobs go to it, in the order they were asked
for. A page that never says `ready` gets them after 25 s with no progress from it. A page
already ready when the holder appears says so in its `hello`. (Dev call ed264469: a `load`
wait cost ~4.3 s on every navigation.)
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
# A move may name the phrases that claim it in speech, and the things it acts on
# (the promise guard, below).
Move(id="site.check", verb=None, cls=MoveClass.REVERSIBLE, args=("lodge",),
     claims=("opening the * calendar", "abro el * calendario"),
     objects=("calendar", "nights", "rooms", "calendario", "noches", "habitaciones"))

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
                 # a move's visible effect was reported: a written line, or None
                 on_landed: Callable[[Landing], str | None] | None = None,
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
    def landed(self, moves: str | Iterable[str], *, event: object | None = None,
               call_ref: str | None = None,
               fits: Callable[[Landing], bool] | None = None) -> str | None:
        """A site event shows what the newest running move of `moves` did (and `fits` it):
        marked shown, `on_landed` asked for its line, kept for `take_lines`. Once a move."""
    def take_lines(self) -> list[str]: ...   # landing lines not yet said (≤ 8 s old), cleared
    def shown(self, call_ref: str) -> bool: ...  # its effect was reported before its result
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
  start if a turn may have been cut off.
- **Claims by shape: `Move.objects`.** Hand-written claims miss most promises: dev call
  453f2e19 said "I'll open the calendar.", "I'm selecting three nights to see the rates."
  and "I'm opening the rooms and rates for your three nights." with no call, and none
  matched. So a move also names its **objects** — the nouns it acts on, in every language
  (explora's check_availability: calendar, availability, dates, days, nights, rooms, rates,
  prices, and their Spanish) — and any non-question sentence shaped as a promise about one
  claims it (`stage/promises.py`, `promise_in`): a first-person lead ("I'll", "I will",
  "let me", "I'm going to", "I'm", "voy a", "déjame", "estoy"), its verb within
  `VERB_REACH` (3) words (any word after a future lead; an *-ing* after "I'm"; an
  infinitive after "voy a"; a gerund after "estoy"), then an object within `CLAIM_GAP`
  words. A Spanish first-person verb is lead and verb at once ("te abro", "reviso",
  "muestro", "selecciono"…). Folded and whole-word, like claims; an object hears its
  plural ("room" → "rooms", "habitación" → "habitaciones"), never the reverse, so two moves
  can split a noun by number. Exact claims still count beside the shape.
  Not promises: a question; a sentence that only names the thing ("The rooms start at…");
  a negation between lead and verb, or before the lead ("I'm not opening", "no voy a");
  a condition before the lead ("If you like, I'll…", "Si quieres, te abro…": an offer);
  and **the past** ("I opened the calendar"): it reports a move rather than promising
  one, is true of a move an earlier turn made, and a false report is not a fault a
  retry fixes. A sentence is **one promise**: when it claims several moves ("the rooms"
  is both the rates' and a room's), any of them made keeps it, and an unkept one is told
  as the first in the brain's move order. A shape-only promise is also kept by a cue the
  model wrote in that sentence ("{show: Rooms} I'll show you the rooms" promised the
  ring). Unkept claims come back in the order they were said, one per move.
- **What the brain does with an unkept claim** is the brain's. Explora appends "[You said
  you were <phrase> but did not do it. Do it now.]" (the quoted sentence instead, when the
  phrase is not an English *-ing*) and asks the model once more with that move's tool
  **forced** (`ToolChoice.only(tool)`), never more than once a turn; what that follow-up
  claims is only logged. Forced, it calls silently, so the follow-up runs through the same
  silent-turn path as any turn — the move's written line ("Let me pull that up.") — and
  the landing line follows the page. A follow-up that only *offered* the tool answered in
  words again.
- **Some models never speak and act in one response.** gpt-6.1-terra at low reasoning, on
  dev call 453f2e19, either spoke or called a tool, never both: every promise in words was
  a response with no call, and every check_availability came with no words (where the
  silent-turn line, the landing line and the talk-through worked every time). So for a
  **tool move**, the recommended pattern is a **silent call plus written and landing
  lines**, not "announce it and call in the same response": the prompt tells the model to
  call a booking step's tool and write no words; the silent-turn line, said as the call
  returns, names nothing the page has not shown yet ("Let me pull that up.", "Te lo
  busco.", never "Here's the booking calendar."); the landing line says what came up. Cue
  narration (show/page cues inside a spoken reply) is unchanged: a cue rides the words.
- **Barge-in and tool moves.** When the visitor starts speaking, the page drops every cue
  not yet fired (`refused`, why `interrupted`, never a failure note). A tool move is not a
  cue: it was asked for by a call the model already made, so it is **kept** — it runs to
  the end (a `quiet` one still waits for the voice to be quiet) and is **reported by its
  result**, like any other, which the brain folds into the context for the next turn. It is
  never cancelled by speech; only its timeout ends it unanswered (`unknown`, then `late`).
- **Landing lines.** The voice must not wait for a page the visitor can already see. Dev call
  ed264469 measured 14.7 s from a product landing to his voice after a tool move, and 18.6 s
  after a filter cue: a `load` wait, rings after the effect, a 2 s quiet window, ~0.6 s of
  plumbing, the model's 4–4.5 s first token, and a cue's landing that only wrote a note, so
  nothing spoke until the 20 s nudge. Now, the moment the page shows what a move did, the
  brain says a **written line** at once, with no model request before it:
  - The brain maps a site event to the move it shows — `stage.landed(("filter_listing",
    "listing.filter"), event=listing, fits=…)` — or the move's own `applied` result does it
    when no event came first (an event up to `LANDED_AFTER_RESULT_S`, 3 s, behind its
    result still counts). `fits` keeps a load's unfiltered listing from passing for the
    filter's.
  - `on_landed(Landing)` returns the line ("Here are 16; the first is Liso Menta at …",
    "Here's the Atacama calendar for November.") built from what the event carries, or
    `None`. A `Landing` has the move, its `call_ref`, its age, the event or the result, and
    the move's arguments (`args` for a tool move, `cue_args` for a cue).
  - The brain sets its idle window to `LANDING_FLOOR_MS` (300 ms), says `take_lines()` in
    that quiet spell (the latest one, when several landed), then may ask the model for at
    most one more sentence (`landed_ask(line)`), tools off. The visitor speaking first
    discards them (`take_lines()` in its turn).
  - A move shown this way gets **no holding line** (`holding()` skips it; `Running.shown`),
    is not listed as still running, and its later `applied` result only confirms: a brain
    talks a result through only when it failed or was partial.
  - The quiet window for talking a result through is short (Cannon Home 600 ms, 300 ms when
    a written line leads): the voice has already stopped when it starts.
- **Holding and landing lines never blame the site.** "The site is slow", "la página va
  lenta" is heard as a fault of the site's owner, whose site it is. A holding line says the
  agent is still on it ("Still opening the calendar for you, one moment.", "Sigo en eso, un
  momento."), picked at random among two or three per move so two in a call differ; a line
  for a page that has not come up says it is not up yet and offers to try again. The same
  goes for the prompt: tell the model a move may take a few seconds and to say it is still
  on it, and forbid calling the site slow. The ports test that no written line matches
  `/slow|lent[ao]/i`.
- Floor policies (nod, silent-turn line, fallback) stay in `demos/voqalize_demos/` — the team
  kept fillers out of the SDK. A landing line is not a filler: it is what the page showed,
  and the director only keeps it; the brain writes and says it.

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
export function domSettled(quietMs?: number /* 300 */, maxMs?: number /* 1500 */): Promise<void>;  // parsed + DOM still
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
  keep(then?: {move: string; args: unknown}): Promise<void>; drop(): Promise<void>;
  // The visible effect has landed: report the result now; what the performer returns later is
  // not reported again, and rings after it say no progress.
  done(result?: string | PerformResult): void;
  // Run once the result is reported (after done, or after the performer returns): rings that
  // point at the effect. The next move waits for it; the agent does not.
  after(fn: () => Promise<void> | void): void; }
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
`command()` for site Actions, and `ready()` (resolves once the site's own scripts can take a
press; nothing is pressed on a new page before it; without one the page waits only for
`domSettled()`, and the host warns). The holder's `makeClient` returns a `HolderClient` (structural:
the site's own `PipecatClient` fits), and `avatar.create` gets the stand-in client typed loosely
(`AvatarClient`) so it passes as whichever `PipecatClient` the site's avatar package wants.

## The Stage Spec (built)

An app's moves are declared once, as data: `<app>/scene.json`, validated by
`sdk/js/stage/stage.schema.json`. The schema is generated from the pydantic model
`voqalize.sdk.stage.StageSpec` (`spec.py`), never written by hand: regenerate it with
`voqalize stage schema -o sdk/js/stage/stage.schema.json`, and a test fails when it is stale.

```json
{ "stage": 1, "id": "shop", "languages": ["es", "en"],
  "moves": [
    { "id": "listing.filter", "verb": "filter", "class": "reversible",
      "args": [{ "name": "facet" }, { "name": "value", "optional": true }],
      "say": "{filter: Tamaño | King}", "claims": ["…"], "objects": ["…"],
      "doc": "for the performer's author", "notes": ["the call that taught it"] },
    { "id": "filter_listing", "class": "reversible",
      "args": [{ "name": "category_path" },
               { "name": "color", "type": "array", "optional": true },
               { "name": "sort", "enum": ["price_asc", "price_desc"], "optional": true },
               { "name": "qty", "type": "integer", "default": 1 }] } ] }
```

- An argument is `string` (default), `integer`, `number`, `boolean` or `array` (of `items`,
  strings by default); `enum` fixes a string's values; `optional` lets it be absent or null;
  `default` makes it optional and never null. A cue takes at most 4 word arguments; a move
  only a tool makes takes at most 12 (`MAX_TOOL_ARGS`). Every `Move` rule (verb shape, call
  words, class may be cued, claims) holds when the spec is loaded.
- `StageSpec.move_set()` is the `MoveSet` the director runs (a hosted brain loads a pack's spec
  this way, as data); `prompt_lines()` the cues' `say` lines; `sha256` the hash of its
  canonical JSON (the `$schema` pointer excluded).
- `voqalize stage gen scene.json --py … --ts … [--prompt …]` writes:
  - **Python**: a pydantic `…Args` model per move (argless ones too), a `Move` constant per
    move (named by the id's last part, or the whole id when two share it), `MOVES`,
    `PROMPT_LINES`, `SPEC_SHA256`. Formatted as `ruff format` leaves it.
  - **TypeScript**: `export const scene = defineScene({...})` with only what the page reads
    (no claims, objects, say, doc, notes, languages), and `SPEC_SHA256`.
  - **Prompt lines**: the `say` lines, one per line.
  `voqalize types --scene scene.json -o x.py` is the Python half alone. `voqalize stage check`
  validates specs.
- `defineScene(spec)` (`@voqalize/stage`, `scene.ts`) keeps the literal (`const` type
  parameter), so `ArgsOf<typeof scene.spec, "filter_listing">` is inferred:
  `{category_path: string; color?: string[] | null; sort?: "price_asc" | "price_desc" | null;
  qty?: number}`. `scene.register(moves, id, performer)` takes the class and a cue's
  argument names from the declaration; `scene.registerAll(moves, {...})` wants a performer for
  every move, so one left out does not compile.
- The ports: `demos/{explora,cannonhome}/scene.json` → `backend/stage_gen.py` and
  `extension/src/scene.gen.ts`. The brains import their moves and wire models from
  `stage_gen` (Explora's prompt teaches its cues from `PROMPT_LINES`, byte for byte the old
  lines); the extensions register with `scene.registerAll` and take their argument types
  from `ArgsOf`. `demos/tests/test_stage_specs.py` regenerates both and fails on a stale file.

### State: slices, events, the mirror, the read tool (built)

A spec may declare `slices` (named, typed pieces of the page's state) and `events` (named acts
that change one slice):

```json
"slices": [{ "id": "cart", "doc": "what is in their cart", "window": 20,
             "fields": [{ "name": "count", "type": "integer" },
                        { "name": "items", "type": "array",
                          "fields": [{ "name": "name" }, { "name": "gift_note", "private": true }] },
                        { "name": "email", "private": true }] }],
"events": [{ "id": "cart.changed", "slice": "cart", "op": "set",
             "note": "{by} changed the cart: {count} items" }]
```

- Wire: `stage_event {name, by: visitor|agent, data, call_ref?}` on `ui-event`
  (`StageEvent`, in `StagePageEvents`). The page never sends a slice whole by any other road.
- Page: `scene.event(id, data, {by, callRef})` builds it, typed from the slice
  (`EventData`: the slice's value for `set`, `Partial` of it for `merge`, the default, nothing
  for `clear`; `SliceOf` leaves private fields out of the type), and strips every field the slice
  does not declare or marks private, whatever it was handed. `Attached.send` sends it.
- Brain: `Mirror(spec)` folds each event into its slice, allowlisted again (private dropped
  here too), versioned per slice, and returns `Folded(slice, version, note)`. The note is the
  event's template, with `{by}` as "The visitor" or "You", and other placeholders limited to
  plain, public fields of the slice (checked when the spec loads), in square brackets. A
  slice nothing has reported reads as unknown, never as empty. `Stage(mirror=...)` folds a
  `StageEvent` in `handle`.
- Read tool: `Mirror.read(slice)` answers in plain lines from the mirror, at most `window`
  entries of a list (the rest counted). The generated Python carries `SliceId` and a
  `ReadRequest` model whose description lists the slices; a brain's tool is
  `@needs_result_now async def read_screen(self, request: ReadRequest) -> str: return
  self.stage.mirror.read(request.slice)`.
- An event that leaves its slice as it was is no act: `Folded.changed` is false, the version
  stays, and there is no line (dev call 84c62a64: the unchanged cart, re-read on every page load
  a move made, told the model three times it had changed the cart).
- Who made a change is the page runtime's to say, once: `Moves.author()` is the agent (with the
  move's `call_ref`) while a move acts and for `AGENT_WINDOW_MS` (500 ms) after, and the
  extension host's `PageKit.author()` adds a move the last page carried here, until this page
  makes it (the listing a `{page:}` cue opened is the agent's, not the visitor's). Sites pass it
  to `scene.event` as `by`.
- A cue's "where" is the place, never its address with state in it: Cannon Home's filter and
  sort cues name the category (`category_of`), so a second filter in one reply runs on the
  listing the first one left (dev call 84c62a64: it reloaded the address the reply was written
  on, which undid the first filter).
- Both ports now report their screen state as state events (Explora: page, stay, enquiry;
  Cannon Home: the kit's listing and cart, and product, search, checkout) and answer
  `read_screen` from the mirror.

### Conformance (built)

- **Static: `voqalize stage check spec.json… [--strict] [--budget N]`** (`check.py`). Beyond
  what loading refuses: every cue run through the SDK's own leaked-call guard (`_looks_like_call`
  at the start of a reply, `_SPOKEN_CALL` in the middle), so a guard change or a verb that trips
  it fails the build; a cue with no `say` line, or one whose line never writes its verb
  (warnings), and a line teaching a verb no move declares (error); a move that changes the page
  with neither `claims` nor `objects` (warning: its promise cannot be caught); the cue lines
  over the token budget (800 by default, at ~4 characters a token); a slice no event changes.
  Exit 1 on an error, and on a warning with `--strict`. `demos/tests/test_stage_specs.py` holds
  each port's spec to no errors.
- **Dynamic: `@voqalize/stage/conformance`** (`conformance.ts`), run from a test against the
  page's own performers on a fixture: `checkRegistry(scene, moves)` (every declared move has a
  performer under its declared class; a performer for an undeclared move is a warning) and
  `conformance(scene, moves, cases)`, which makes each case's move and checks one result under
  its own move id and `call_ref`, an outcome from the closed set, **no page change before the
  first ring** (a `MutationObserver` on the document, its pending records taken synchronously
  when `ring` is called; the spotlight's own `[data-voqalize]` overlay is not the page), and a
  look that lands rings something (warning). `observe(moves, id, args)` gives the raw
  observation. In the ports, `scene.registerAll` makes the registry check a compile error.

### Kits and plugins (built)

- **Kit**: a spec fragment many apps share, as data shipped in the SDK
  (`voqalize/sdk/stage/kits/<id>.json`, `KitSpec`: `kit: 1`, `id`, semver `version`, moves named
  `<id>.…`, slices, events). An app takes it with `"kits": [{"id": "commerce", "major": 1,
  "moves": [...]?}]`; loading merges the kit's chosen moves and all its slices and events in
  (a `mode="before"` validator), so the director, `stage gen` and the TS scene see one spec. A
  part already present exactly as the kit has it is the same part (a dump loads again); one
  declared otherwise, a wrong major, an unknown kit or move, or a verb clash is refused. A minor
  version only adds; lowering a class or renaming is a major.
- **`commerce` 1.0.0**: `commerce.filter` (cue `{filter: Facet | Option[, Option]}`),
  `commerce.sort` (cue, closed orders), `commerce.search`, `commerce.open_item`,
  `commerce.cart_add` / `cart_update` (confirmed), `commerce.cart_show`; slices `listing`
  (path, title, count, filters on/offered, sort, items) and `cart` (count, subtotal, lines);
  events `listing.shown|filtered|sorted`, `cart.changed`. Claims and objects in en and es. Every
  shipped kit is held to `stage check` with no errors.
- **Plugin** (`PluginSpec` in the spec's `plugins`): `name` (`magento.prices`), `major`,
  `side: brain|page`, `class`, `args`, `output` fields, `egress` (https origins only, no path),
  `deadline_ms`, `pii`. Bounds checked on load: a brain plugin is `look` only, answers within
  20 ms (the tool budget) and has no egress (our servers never reach a customer's site; a read of
  the site runs on the page); a page plugin is at most `reversible` and answers within 5 s.
- **Page runtime** (`Plugins`, `@voqalize/stage`): `new Plugins(scene.spec.plugins)`,
  `register(name, impl)` only for a declared page plugin, `run(name, args)` within the
  declaration: a `fetch` that requests only the `egress` origins, always `credentials: "omit"`,
  aborted at the deadline (the run fails with `PluginError`), and only the declared, non-private
  `output` fields returned. No loader: plugins are compiled in, never fetched.
- The ports keep their own move ids; moving Cannon Home onto `commerce.*` and its live price
  read onto a `magento.prices` plugin renames moves on both sides, so it lands with a dev
  re-test. The hosted brain and the explorer are the kit's first users.

### Developer mode (built)

- **Markup** (`markup.ts`, `@voqalize/stage`): `data-stage-thing="name"` (+ `data-stage-label`,
  else the accessible name), `data-stage-part="Facet:Option"`, `data-stage-place="name"`.
  Locators only: no moves, labels or prompt text come from markup. `findThing` matches the name,
  then the label whole, then its start, folded; `findPart` folds both halves. Stock performers:
  `showThing` (`{show: Name}`: reveal, scroll, ring; refuses with the labels on the page) and
  `pressParts` (`{filter: Facet | A, B}`: scroll, ring, beat, press each; refuses with the
  facet's options).
- **Script-tag host** (`@voqalize/stage/script`): `attach(client, {spec, theme?, lang?,
  performers?})`, where `spec` is a spec object or the URL of its page JSON. Each declared move
  gets the page's own performer, else the stock one for its verb (`STOCK`: show, filter), else
  is listed in `unbound` and warned about. It runs on `stagePage`; `navigated()` sends hello
  again for a single-page route change. It is a source module: our snippet and extension
  bundle it, so a plug-and-play customer never installs npm.
- **`voqalize stage gen --json page.json`** writes the page's spec for a page with no build
  step: kits merged, brain-only fields out (`page_spec()`, the same body the TS output hands to
  `defineScene`).
- **React** (`@voqalize/stage/react`): `stageHooks(React)` → `useStage(client, scene, opts)`,
  `useMove(stage, id, performer)` (registered once, runs the latest render's closure, refuses
  once unmounted), `useSlice(stage, value, toEvent)` (a change named by `toEvent` is sent as the
  spec's event; within a performer, or `AGENT_WINDOW_MS` = 500 ms after it, it is `by: "agent"`
  with the move's `call_ref`), `useNavigated(stage, path)`. React is handed in, never imported:
  the package stays dependency-free, no second copy of React can meet the app's, and it is typed
  structurally (`ReactHooks`), as the pipecat client is.
- **Example**: `sdk/python/examples/stage_shop/` (spec taking two `commerce` moves, marked-up
  page, brain, generated files, README). `test_example.py` keeps it current and importable;
  `test/example.test.ts` makes its cues on its own markup under the Stage conformance checks.
- **`stage build scene.ts -o scene.json`** (`bin/stage.mjs`, the package's `stage` bin): imports
  the module on Node's own type stripping and writes `scene.spec`. It needs the package as
  compiled JS, which is what is published (`dist`, with `.js` relative imports in the source so
  the output runs on Node).
- Not built: a ts-morph pass that every declared thing is bound; Vue and Svelte bindings.

### Releasing (release candidates first)

- Python: `voqalize-agent-sdk` `0.12.0-rc1` (PEP 440 `0.12.0rc1`, a pre-release pip installs
  only when asked), tag `python-sdk-v0.12.0-rc1` on `main` once this PR is merged.
- npm: `@voqalize/stage` `0.1.0-rc.1`, tag `stage-v0.1.0-rc.1`,
  `.github/workflows/release-npm-stage.yml`: gate, `pnpm build`, `scripts/publish-manifest.mjs`
  (exports to `dist`, `private` dropped, on the run's own checkout), `npm publish --provenance`
  under `next` for a pre-release. Needs the `npm` environment and npm trusted publishing for
  the package, set up by an owner of the `@voqalize` npm org (a new package needs its first
  publish before a trusted publisher can be added).

### The hosted brain (not started: waits on a release)

Platform's hosted brain runs on exactly the published `voqalize-agent-sdk==0.11.0`, with "no
SDK change and no vendored wheel" (its DECISIONS, "LIFECYCLE v2" item 4) and a startup guard
that refuses any other version; the snippet would need `@voqalize/stage` from npm. So hosting
Stage there (pack format 3 carrying a Stage Spec, a format-2 adapter, the explorer writing
specs, the snippet and preview extension on `@voqalize/stage`) starts once both are released,
or once the owner decides otherwise. What it builds on is here: `StageSpec` as the pack's
scene, kits for the shared moves, the Stage conformance checks for proofs, the script host
for the snippet.

Not yet in the spec (next steps): places and things (regions with spoken labels), `effect`,
`spotlight`, `undo`, the stale-version check on moves (`resolved_at`), and `stage build` for a
`defineScene` module.

## Gates

```
uv run ruff format --check . && uv run ruff check . && uv run pyright
cd sdk/python && uv run pytest -q
cd demos && uv run pytest tests/test_explora*.py tests/test_cannonhome*.py tests/test_stage_specs.py   # + the cross-demo voice contract
cd sdk/js/stage && pnpm typecheck && pnpm test   # incl. catch-up, mouth clock, client types
cd demos/<site>/extension && pnpm install --ignore-workspace && pnpm typecheck && pnpm build && pnpm test:e2e
```
