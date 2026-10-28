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
 */

import { reveal, scrollToEl, sleep } from "./dom";
import type { Spotlight } from "./spotlight";
import type { Refusal, StageResult } from "./wire.gen";

/** How much a move changes, from nothing to something the person owns. */
export type MoveClass = "look" | "navigate" | "reversible" | "confirmed";

export interface MoveContext {
  /** The move being made, and the call it answers. */
  readonly move: string;
  readonly callRef: string;
  spotlight: Spotlight;
  /** Open the tab, accordion, `<details>` or slide hiding `el`. */
  reveal(el: Element): Promise<void>;
  /** Ring `el` (or several as one box) and wait out the dwell. */
  ring(el: Element | Element[], label?: string): Promise<void>;
  /** A pause a person can follow (600 ms by default). */
  beat(ms?: number): Promise<void>;
  /** Scroll `el` into view under the site's pinned bars. */
  scrollTo(el: Element): Promise<void>;
  /** Give up on one argument: the move ends `refused`, naming it, why, and
   *  what the page offers instead. */
  refuse(arg: string, why: string, options?: string[]): never;
  /** Load `url` in this tab and finish the move on the page it lands on with
   *  `then` (another move, made there with this move's `call_ref`). Present
   *  only where a host can carry a move across a page load (the extension). */
  loadThen?(url: string, then?: { move: string; args: unknown }): Promise<never>;
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
  /** Adds what a host offers (`loadThen` in the extension). */
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
    const next = this.chain.then(() => this.perform(id, args, callRef));
    this.chain = next.catch(() => {});
    return next;
  }

  private async perform(id: string, args: unknown, callRef: string): Promise<StageResult | null> {
    const now = this.opts.now ?? (() => performance.now());
    const t0 = now();
    const ms = () => Math.round(now() - t0);
    const base = { call_ref: callRef, move: id };
    const entry = this.registry.get(id);
    if (!entry) {
      return { ...base, outcome: "failed", detail: `this page has no move ${id}`, refused: [], moved: false, ms: 0 };
    }
    const spotlight = this.spotlight;
    const fixed = this.opts.fixed;
    const c: MoveContext = {
      move: id,
      callRef,
      spotlight,
      reveal,
      ring: (el, label) => spotlight.ring(el, { label }),
      beat: (n = 600) => sleep(n),
      scrollTo: (el) => scrollToEl(el, { fixed }),
      refuse(arg, why, options) {
        throw new Refused({ arg, why, ...(options?.length ? { options } : {}) });
      },
    };
    Object.assign(c, this.opts.extend?.(c) ?? {});
    try {
      const detail = await entry.performer(named(args, entry.params) as never, c);
      if (detail === null) return { ...base, outcome: "applied", detail: null, refused: [], moved: true, ms: ms() };
      return { ...base, outcome: "applied", detail, refused: [], moved: false, ms: ms() };
    } catch (error) {
      if (error instanceof Deferred) return null;
      if (error instanceof Refused) {
        return { ...base, outcome: "refused", detail: error.refusal.why, refused: [error.refusal], moved: false, ms: ms() };
      }
      const text = error instanceof Error ? error.message : String(error);
      return { ...base, outcome: "failed", detail: text || "failed", refused: [], moved: false, ms: ms() };
    }
  }
}

/** A cue's positional arguments as named ones, where the move names them. */
function named(args: unknown, params: readonly string[] | undefined): unknown {
  if (!params || !Array.isArray(args)) return args;
  const out: Record<string, string | null> = {};
  params.forEach((p, i) => (out[p] = (args[i] as string | undefined) ?? null));
  return out;
}
