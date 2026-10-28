/**
 * The moves a page can make, and the one result each of them reports.
 *
 * A site registers a performer per move id. The agent names the move and its
 * arguments; the performer finds the target, rings it, brings it out and acts,
 * through the `MoveContext` it is handed. What happened is built here into a
 * `StageResult`: `applied` with the performer's detail (or `partial`, when it
 * returns a `PerformResult` saying so), `refused` when the performer called
 * `refuse()` (an argument the page could not use, with what it offers
 * instead), `failed` when it threw, and `moved: true` when it returned `null`
 * because the page went on to another one. Moves run one at a time, in the
 * order they arrive.
 *
 * While it runs, a move says where it is (`StageProgress`): `queued` behind
 * another, `acting`, `ringing` while its ring holds it; a performer adds
 * `waiting_site` or `confirming` with `progress()`. Each one tells the agent
 * the move is alive. A result carries when, after the page received the move,
 * it was queued, started, first rang and finished.
 *
 * A move reports as soon as what it did shows: a performer that has more to
 * point at afterwards (the grid it filtered, the panel it opened) calls
 * `done()` with its result, or hands that trailing part to `after()`, and the
 * agent hears at once. Only the act waits for its ring; what follows the
 * result never holds it. The next move still waits for the trailing part.
 *
 * A move that loads another page (`loadThen`), or presses something that may
 * (`keep`), carries the rest of itself to the next page through the host's
 * `Carrier`. The next page finishes it with `resume`, and reports it under
 * the move's own id and `call_ref`, as if it had never left: the agent hears
 * of one move, once.
 */

import { RING_SCROLL_MS, reveal, scrollToEl, sleep } from "./dom.js";
import type { RingOptions, Spotlight } from "./spotlight.js";
import type { Refusal, StageProgress, StageResult } from "./wire.gen.js";

/** How much a move changes, from nothing to something the person owns. */
export type MoveClass = "look" | "navigate" | "reversible" | "confirmed";

/** Where a move is, before its result. */
export type Phase = StageProgress["phase"];

export interface MoveContext {
  /** The move being made (the id its performer is registered under), and the
   *  call it answers. A move carried to the next page is reported there under
   *  the id the agent asked for, whichever performer finishes it. */
  readonly move: string;
  readonly callRef: string;
  spotlight: Spotlight;
  /** Open the tab, accordion, `<details>` or slide hiding `el`. */
  reveal(el: Element): Promise<void>;
  /** Ring `el` (several: one box, or one each with `separate`) and hold the
   *  move a beat; the ring stays its dwell. A string is the label. */
  ring(el: Element | Element[], opts?: string | RingOptions): Promise<void>;
  /** A pause a person can follow (600 ms by default). */
  beat(ms?: number): Promise<void>;
  /** Scroll `el` into view under the site's pinned bars. Waits for the
   *  scroll at most `RING_SCROLL_MS`, and not at all once the next move is
   *  due: the ring follows its target wherever the scroll gets to. */
  scrollTo(el: Element): Promise<void>;
  /** Give up on one argument: the move ends `refused`, naming it, why, and
   *  what the page offers instead. */
  refuse(arg: string, why: string, options?: string[]): never;
  /** Say where the move is: `waiting_site` while the site's own scripts work,
   *  `confirming` while it checks what it did took. The runtime says
   *  `queued`, `acting` and `ringing` by itself. Each tells the agent the
   *  move is alive and gives it its time again. */
  progress(phase: Phase): void;
  /** Load `url` in this tab and finish the move on the page it lands on: with
   *  `then` (another performer, run there under this move's id and
   *  `call_ref`), or, without it, `applied` once that page is up where it
   *  should be. Present only where a host can carry a move across a page
   *  load (the extension). */
  loadThen?(url: string, then?: Then): Promise<never>;
  /** Keep the rest of this move for this tab's next page, should what it is
   *  about to press load one: `then` runs there (under this move's id and
   *  `call_ref`), or, without it, the move is `applied` once the page is up.
   *  A move that ends on this page after all drops what it kept by itself.
   *  Nothing, where no host carries moves. */
  keep(then?: Then): Promise<void>;
  /** Discard what `keep` kept: the press did not load a page. */
  drop(): Promise<void>;
  /** The visible effect has landed: report the move's result now (a detail,
   *  or a `PerformResult`), and go on with what trails it — a ring on the
   *  grid it changed, say. What the performer returns after this is not
   *  reported again. Rings after it still ring, but say no progress. */
  done(result?: string | PerformResult): void;
  /** Run `fn` once the move's result has been reported (after `done`, or
   *  after the performer returns): rings that follow the effect, not ones
   *  before the act. The next move waits for it; the agent does not. */
  after(fn: () => Promise<void> | void): void;
}

/** The rest of a move, for the page it goes on on. */
export interface Then {
  move: string;
  args: unknown;
}

/** A move carried to the next page of the tab: reported there as `move`, with
 *  `call_ref`, after `then` runs; or, with no `then`, applied once that page
 *  is up, on `expect` when it names where. `received_at` is when the first
 *  page received it (epoch ms), so its timings run from there. */
export interface Carried {
  kind: "carried";
  call_ref: string;
  move: string;
  then?: Then;
  expect?: string;
  received_at?: number;
}

/** How a host carries a move across a page load. */
export interface Carrier {
  /** Keep `c` for this tab's next page. */
  keep(c: Carried): Promise<void>;
  /** Forget what was kept for `callRef`. */
  drop(callRef: string): Promise<void>;
  /** Load `url` in this tab. */
  load(url: string): void;
}

/** What a performer may say it did, beyond a bare detail: `partial` when only
 *  some of it took, with what it could not use in `refused`. */
export interface PerformResult {
  outcome?: "applied" | "partial";
  detail?: string | null;
  refused?: Refusal[];
}

/** Makes one move. Returns a short detail of what it did (or a
 *  `PerformResult`), or `null` when it moved on to another page (which
 *  reports from there). */
export type Performer<A> = (args: A, c: MoveContext) => Promise<string | null | PerformResult>;

/** A move under way: its result, as soon as it is reported, and the whole of
 *  it, trailing rings included, which the next move waits for. */
interface Run {
  result: Promise<StageResult | null>;
  whole: Promise<unknown>;
}

interface Registered {
  cls: MoveClass;
  performer: Performer<never>;
  /** Names for a cue's positional arguments. */
  params?: readonly string[];
}

/** Thrown by `refuse()`; caught by `Moves.run`. */
export class Refused extends Error {
  constructor(readonly refusal: Refusal) {
    super(`refused ${refusal.arg}: ${refusal.why}`);
  }
}

/** Thrown by a performer that handed its move to the next page: the result is
 *  that page's to send. */
export class Deferred extends Error {
  constructor() {
    super("the move goes on on the next page");
  }
}

export interface MovesOptions {
  /** Selectors of the site's pinned bars, for `scrollTo`. */
  fixed?: readonly string[];
  /** Carries a move across a page load: `loadThen`, `keep` and `drop` are
   *  its (the extension's host gives one). */
  carrier?: Carrier;
  /** Adds anything else a host offers. */
  extend?: (c: MoveContext) => Partial<MoveContext>;
  /** Where each move is, as it changes: send it to the agent. */
  onProgress?: (p: StageProgress) => void;
  /** Milliseconds now; injectable for tests. */
  now?: () => number;
}

/** When the page received a move, for its timings (epoch ms; now by default). */
export interface RunOptions {
  receivedAt?: number;
}

export class Moves {
  private readonly registry = new Map<string, Registered>();
  private chain: Promise<unknown> = Promise.resolve();
  /** Moves queued or running here. */
  private inQueue = 0;
  /** Cuts the running move's scroll wait short. */
  private hurrying: AbortController | null = null;
  private readonly listeners = new Set<(p: StageProgress) => void>();

  constructor(
    readonly spotlight: Spotlight,
    private readonly opts: MovesOptions = {},
  ) {}

  /**
   * Register the performer for a move id. `params` names a cue's positional
   * arguments (`{show: Atacama | rooms}` with `params: ["place", "section"]`
   * reaches the performer as `{place: "Atacama", section: "rooms"}`); without
   * it a cue's arguments arrive as the array they were written as.
   */
  register<A>(id: string, cls: MoveClass, performer: Performer<A>, opts: { params?: readonly string[] } = {}): void {
    this.registry.set(id, { cls, performer: performer as Performer<never>, params: opts.params });
  }

  has(id: string): boolean {
    return this.registry.has(id);
  }

  classOf(id: string): MoveClass | null {
    return this.registry.get(id)?.cls ?? null;
  }

  /** The ids registered. */
  get ids(): string[] {
    return [...this.registry.keys()];
  }

  /** Hear every move's progress (as well as `onProgress`), until the
   *  returned function is called. */
  listen(fn: (p: StageProgress) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** The next move is due: the running one stops waiting for its scroll. */
  hurry(): void {
    this.hurrying?.abort();
  }

  /** Make one move, after the one before it, and build its result. Never
   *  throws; a move handed to the next page resolves `null`. */
  run(id: string, args: unknown, callRef: string, opts: RunOptions = {}): Promise<StageResult | null> {
    const receivedAt = opts.receivedAt ?? Date.now();
    return this.queue(callRef, id, receivedAt, (queuedAt) => this.perform(id, args, callRef, id, receivedAt, queuedAt));
  }

  /** Finish a move the last page of this tab carried here, after the one
   *  before it: its `then`, reported under the move's own id and `call_ref`;
   *  or, with none, `applied` now that this page is up (`partial`, saying
   *  where, when it is not the page asked for). */
  resume(c: Carried): Promise<StageResult | null> {
    const receivedAt = c.received_at ?? Date.now();
    if (c.then) {
      const then = c.then;
      return this.queue(c.call_ref, c.move, receivedAt, (queuedAt) =>
        this.perform(then.move, then.args, c.call_ref, c.move, receivedAt, queuedAt),
      );
    }
    return this.queue(c.call_ref, c.move, receivedAt, () => {
      const result = Promise.resolve({ ...arrived(c), received_ms: Math.max(0, Date.now() - receivedAt) });
      return { result, whole: result };
    });
  }

  private queue(callRef: string, move: string, receivedAt: number, fn: (queuedAt: number) => Run): Promise<StageResult | null> {
    const queuedAt = Date.now();
    if (this.inQueue > 0) {
      this.say(callRef, move, "queued", receivedAt);
      this.hurry();
    }
    this.inQueue++;
    let report!: (r: StageResult | null) => void;
    const result = new Promise<StageResult | null>((r) => (report = r));
    const next = this.chain.then(async () => {
      const run = fn(queuedAt);
      void run.result.then(report, () => report(null));
      await run.whole;
    });
    const settled = next.finally(() => this.inQueue--);
    this.chain = settled.catch(() => {});
    // A move that never reported (it threw past its own catch): null.
    void settled.then(
      () => report(null),
      () => report(null),
    );
    return result;
  }

  private say(callRef: string, move: string, phase: Phase, receivedAt: number): void {
    const p: StageProgress = { call_ref: callRef, move, phase, ms: Math.max(0, Date.now() - receivedAt) };
    for (const fn of [this.opts.onProgress, ...this.listeners]) {
      try {
        fn?.(p);
      } catch {
        /* A host that could not send it: the move goes on. */
      }
    }
  }

  private perform(id: string, args: unknown, callRef: string, reportAs: string, receivedAt: number, queuedAt: number): Run {
    let reported = false;
    let report!: (r: StageResult | null) => void;
    const result = new Promise<StageResult | null>((r) => (report = r));
    const trailing: (() => Promise<void> | void)[] = [];
    const say = (r: StageResult | null) => {
      if (reported) return;
      reported = true;
      report(r);
    };
    const whole = this.act(id, args, callRef, reportAs, receivedAt, queuedAt, {
      reported: () => reported,
      say,
      after: (fn) => trailing.push(fn),
    }).then(async (final) => {
      say(final);
      for (const fn of trailing) {
        try {
          await fn();
        } catch (error) {
          console.warn("voqalize: after a move's result:", error);
        }
      }
    });
    return { result, whole };
  }

  private async act(
    id: string,
    args: unknown,
    callRef: string,
    reportAs: string,
    receivedAt: number,
    queuedAt: number,
    early: { reported(): boolean; say(r: StageResult): void; after(fn: () => Promise<void> | void): void },
  ): Promise<StageResult | null> {
    const now = this.opts.now ?? (() => performance.now());
    const t0 = now();
    const ms = () => Math.round(now() - t0);
    const since = (t: number) => Math.max(0, Math.round(t - receivedAt));
    const firedAt = Date.now();
    let ringedAt: number | null = null;
    const base = { call_ref: callRef, move: reportAs };
    const times = () => ({
      received_ms: since(Date.now()),
      queued_ms: since(queuedAt),
      fired_ms: since(firedAt),
      ...(ringedAt !== null ? { ringed_ms: since(ringedAt) } : {}),
    });
    const entry = this.registry.get(id);
    if (!entry) {
      return { ...base, outcome: "failed", detail: `this page has no move ${id}`, refused: [], moved: false, ms: 0, ...times() };
    }
    const spotlight = this.spotlight;
    const fixed = this.opts.fixed;
    const carrier = this.opts.carrier;
    const hurrying = new AbortController();
    this.hurrying = hurrying;
    let phase: Phase | null = null;
    const progress = (next: Phase) => {
      // Past its result, the move is answered: no more of where it is.
      if (next === phase || early.reported()) return;
      phase = next;
      this.say(callRef, reportAs, next, receivedAt);
    };
    let kept = false;
    const built = (got: string | PerformResult | undefined): StageResult => {
      if (got === undefined || typeof got === "string") {
        return { ...base, outcome: "applied", detail: got ?? null, refused: [], moved: false, ms: ms(), ...times() };
      }
      const refused = got.refused ?? [];
      const outcome = got.outcome ?? (refused.length ? "partial" : "applied");
      return { ...base, outcome, detail: got.detail ?? null, refused, moved: false, ms: ms(), ...times() };
    };
    const c: MoveContext = {
      move: id,
      callRef,
      spotlight,
      reveal,
      async ring(el, opts) {
        ringedAt ??= Date.now();
        progress("ringing");
        await spotlight.ring(el, typeof opts === "string" ? { label: opts } : opts);
        progress("acting");
      },
      beat: (n = 600) => sleep(n),
      scrollTo: (el) => scrollToEl(el, { fixed, maxMs: RING_SCROLL_MS, signal: hurrying.signal }),
      refuse(arg, why, options) {
        throw new Refused({ arg, why, ...(options?.length ? { options } : {}) });
      },
      progress,
      async keep(then) {
        if (!carrier) return;
        kept = true;
        await carrier.keep({ kind: "carried", call_ref: callRef, move: reportAs, received_at: receivedAt, ...(then ? { then } : {}) });
      },
      async drop() {
        if (!carrier || !kept) return;
        kept = false;
        await carrier.drop(callRef);
      },
      done(got) {
        if (early.reported()) return;
        // Nothing kept for a next page is owed once the move has answered.
        if (kept) void c.drop().catch(() => {});
        early.say(built(got));
      },
      after: (fn) => early.after(fn),
      ...(carrier
        ? {
            async loadThen(url: string, then?: Then): Promise<never> {
              await carrier.keep({
                kind: "carried", call_ref: callRef, move: reportAs, received_at: receivedAt, ...(then ? { then } : { expect: url }),
              });
              kept = false;
              spotlight.clear();
              carrier.load(url);
              throw new Deferred();
            },
          }
        : {}),
    };
    Object.assign(c, this.opts.extend?.(c) ?? {});
    progress("acting");
    let handedOn = false;
    try {
      const got = await entry.performer(named(args, entry.params) as never, c);
      handedOn = got === null;
      if (got === null) return { ...base, outcome: "applied", detail: null, refused: [], moved: true, ms: ms(), ...times() };
      return built(got);
    } catch (error) {
      handedOn = error instanceof Deferred;
      if (error instanceof Deferred) return null;
      if (early.reported()) {
        // Answered already: what went wrong after the effect is only logged.
        console.warn("voqalize: after a move's result:", error);
        return null;
      }
      if (error instanceof Refused) {
        return { ...base, outcome: "refused", detail: error.refusal.why, refused: [error.refusal], moved: false, ms: ms(), ...times() };
      }
      const text = error instanceof Error ? error.message : String(error);
      return { ...base, outcome: "failed", detail: text || "failed", refused: [], moved: false, ms: ms(), ...times() };
    } finally {
      if (this.hurrying === hurrying) this.hurrying = null;
      // It ended here after all: what it kept for a next page is not owed.
      if (kept && !handedOn) await c.drop().catch(() => {});
    }
  }
}

/** The result of a carried move with no `then`, on the page it landed on. */
export function arrived(c: Carried, here: string = location.href): StageResult {
  const base = { call_ref: c.call_ref, move: c.move, refused: [], moved: false, ms: 0 };
  const now = new URL(here);
  if (!c.expect) return { ...base, outcome: "applied", detail: `the page loaded ${now.pathname}` };
  let want: URL;
  try {
    want = new URL(c.expect, now);
  } catch {
    return { ...base, outcome: "applied", detail: `opened ${now.pathname}` };
  }
  const host = (u: URL) => u.host.replace(/^www\./i, "").toLowerCase();
  const path = (u: URL) => u.pathname.replace(/\/+$/, "") || "/";
  if (host(want) === host(now) && path(want) === path(now)) return { ...base, outcome: "applied", detail: `opened ${now.pathname}` };
  return {
    ...base,
    outcome: "partial",
    detail: `asked for ${host(want)}${want.pathname}; the page that came up is ${host(now)}${now.pathname}`,
  };
}

/** A cue's positional arguments as named ones, where the move names them. */
function named(args: unknown, params: readonly string[] | undefined): unknown {
  if (!params || !Array.isArray(args)) return args;
  const out: Record<string, string | null> = {};
  params.forEach((p, i) => (out[p] = (args[i] as string | undefined) ?? null));
  return out;
}
