/**
 * The moves a page can make, and the one result each of them reports.
 *
 * A site registers a performer per move id. The agent names the move and its
 * arguments; the performer finds the target, rings it, brings it out and acts,
 * through the `MoveContext` it is handed. What happened is built here into a
 * `StageResult`: `applied` with the performer's detail, `refused` when the
 * performer called `refuse()` (an argument the page could not use, with what
 * it offers instead), `failed` when it threw, and `moved: true` when it
 * returned `null` because the page went on to another one. Moves run one at a
 * time, in the order they arrive.
 *
 * A move that loads another page (`loadThen`), or presses something that may
 * (`keep`), carries the rest of itself to the next page through the host's
 * `Carrier`. The next page finishes it with `resume`, and reports it under
 * the move's own id and `call_ref`, as if it had never left: the agent hears
 * of one move, once.
 */

import { reveal, scrollToEl, sleep } from "./dom";
import type { RingOptions, Spotlight } from "./spotlight";
import type { Refusal, StageResult } from "./wire.gen";

/** How much a move changes, from nothing to something the person owns. */
export type MoveClass = "look" | "navigate" | "reversible" | "confirmed";

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
  /** Scroll `el` into view under the site's pinned bars. */
  scrollTo(el: Element): Promise<void>;
  /** Give up on one argument: the move ends `refused`, naming it, why, and
   *  what the page offers instead. */
  refuse(arg: string, why: string, options?: string[]): never;
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
}

/** The rest of a move, for the page it goes on on. */
export interface Then {
  move: string;
  args: unknown;
}

/** A move carried to the next page of the tab: reported there as `move`, with
 *  `call_ref`, after `then` runs; or, with no `then`, applied once that page
 *  is up, on `expect` when it names where. */
export interface Carried {
  kind: "carried";
  call_ref: string;
  move: string;
  then?: Then;
  expect?: string;
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

/** Makes one move. Returns a short detail of what it did, or `null` when it
 *  moved on to another page (which reports from there). */
export type Performer<A> = (args: A, c: MoveContext) => Promise<string | null>;

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
  /** Milliseconds now; injectable for tests. */
  now?: () => number;
}

export class Moves {
  private readonly registry = new Map<string, Registered>();
  private chain: Promise<unknown> = Promise.resolve();

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

  /** Make one move, after the one before it, and build its result. Never
   *  throws; a move handed to the next page resolves `null`. */
  run(id: string, args: unknown, callRef: string): Promise<StageResult | null> {
    return this.queue(() => this.perform(id, args, callRef, id));
  }

  /** Finish a move the last page of this tab carried here, after the one
   *  before it: its `then`, reported under the move's own id and `call_ref`;
   *  or, with none, `applied` now that this page is up (`partial`, saying
   *  where, when it is not the page asked for). */
  resume(c: Carried): Promise<StageResult | null> {
    if (c.then) {
      const then = c.then;
      return this.queue(() => this.perform(then.move, then.args, c.call_ref, c.move));
    }
    return this.queue(async () => arrived(c));
  }

  private queue(fn: () => Promise<StageResult | null>): Promise<StageResult | null> {
    const next = this.chain.then(fn);
    this.chain = next.catch(() => {});
    return next;
  }

  private async perform(id: string, args: unknown, callRef: string, reportAs: string): Promise<StageResult | null> {
    const now = this.opts.now ?? (() => performance.now());
    const t0 = now();
    const ms = () => Math.round(now() - t0);
    const base = { call_ref: callRef, move: reportAs };
    const entry = this.registry.get(id);
    if (!entry) {
      return { ...base, outcome: "failed", detail: `this page has no move ${id}`, refused: [], moved: false, ms: 0 };
    }
    const spotlight = this.spotlight;
    const fixed = this.opts.fixed;
    const carrier = this.opts.carrier;
    let kept = false;
    const c: MoveContext = {
      move: id,
      callRef,
      spotlight,
      reveal,
      ring: (el, opts) => spotlight.ring(el, typeof opts === "string" ? { label: opts } : opts),
      beat: (n = 600) => sleep(n),
      scrollTo: (el) => scrollToEl(el, { fixed }),
      refuse(arg, why, options) {
        throw new Refused({ arg, why, ...(options?.length ? { options } : {}) });
      },
      async keep(then) {
        if (!carrier) return;
        kept = true;
        await carrier.keep({ kind: "carried", call_ref: callRef, move: reportAs, ...(then ? { then } : {}) });
      },
      async drop() {
        if (!carrier || !kept) return;
        kept = false;
        await carrier.drop(callRef);
      },
      ...(carrier
        ? {
            async loadThen(url: string, then?: Then): Promise<never> {
              await carrier.keep({ kind: "carried", call_ref: callRef, move: reportAs, ...(then ? { then } : { expect: url }) });
              kept = false;
              spotlight.clear();
              carrier.load(url);
              throw new Deferred();
            },
          }
        : {}),
    };
    Object.assign(c, this.opts.extend?.(c) ?? {});
    let handedOn = false;
    try {
      const detail = await entry.performer(named(args, entry.params) as never, c);
      handedOn = detail === null;
      if (detail === null) return { ...base, outcome: "applied", detail: null, refused: [], moved: true, ms: ms() };
      return { ...base, outcome: "applied", detail, refused: [], moved: false, ms: ms() };
    } catch (error) {
      handedOn = error instanceof Deferred;
      if (error instanceof Deferred) return null;
      if (error instanceof Refused) {
        return { ...base, outcome: "refused", detail: error.refusal.why, refused: [error.refusal], moved: false, ms: ms() };
      }
      const text = error instanceof Error ? error.message : String(error);
      return { ...base, outcome: "failed", detail: text || "failed", refused: [], moved: false, ms: ms() };
    } finally {
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
