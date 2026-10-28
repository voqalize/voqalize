/**
 * The adapter as the end-to-end tests inject it: the anchors (`anchor.js` in
 * the extension) and Cannon Home's moves on Stage's `Moves` and spotlight, as
 * `content.js` registers them, without the call or the widget; plus the
 * checkout guard for the tests to drive directly.
 *
 * With no extension, a move that loads another page carries the rest of
 * itself in this tab's `sessionStorage` (the extension keeps it with its
 * service worker), and this page makes it once settled and reports its one
 * `stage_result`, as the extension's next page does.
 */

import { Deferred, Moves, Spotlight, type StageResult } from "@voqalize/stage";

import { watchAnchors } from "../src/anchors";
import { context, type PageContext, prepare, registerMoves, start, useCarry } from "../src/cannonhome-actions";
import { forbiddenPath, go, intoCheckout, press, privateField, settled } from "../src/page";
import { SPOTLIGHT } from "../src/site";

/** How a move went, for the tests: `moved` when it went on to another page,
 *  which reports from there. */
export interface RunResult {
  ok: boolean;
  error?: string;
  detail?: string;
  moved?: boolean;
  result: StageResult | null;
}

export interface TestAdapter {
  run(move: string, args: unknown): Promise<RunResult>;
  context(): PageContext;
  start(emit: (event: string, payload: unknown) => void): () => void;
  readonly commands: readonly string[];
}

declare global {
  interface Window {
    voqalizeCannonhome?: TestAdapter;
  }
}

const KEY = "voqalize.test.then";
interface Kept {
  move: string;
  args: unknown;
  call_ref: string;
}

const keepJob = (k: Kept) => sessionStorage.setItem(KEY, JSON.stringify(k));
function takeJob(): Kept | null {
  const raw = sessionStorage.getItem(KEY);
  sessionStorage.removeItem(KEY);
  return raw ? (JSON.parse(raw) as Kept) : null;
}

useCarry({
  keep: async (callRef, then) => keepJob({ ...then, call_ref: callRef }),
  drop: () => sessionStorage.removeItem(KEY),
});

const spotlight = new Spotlight(SPOTLIGHT);
const moves = new Moves(spotlight, {
  extend: (c) => ({
    async loadThen(url: string, then?: { move: string; args: unknown }): Promise<never> {
      if (then) keepJob({ ...then, call_ref: c.callRef });
      spotlight.clear();
      location.assign(url);
      throw new Deferred();
    },
  }),
});
registerMoves(moves);
prepare();
watchAnchors();

let listener: ((event: string, payload: unknown) => void) | null = null;
const backlog: [string, unknown][] = [];
const emit = (event: string, payload: unknown) => (listener ? listener(event, payload) : backlog.push([event, payload]));

let n = 0;
async function run(move: string, args: unknown): Promise<RunResult> {
  const result = await moves.run(move, args, `test-${++n}`);
  if (!result) return { ok: true, moved: true, result };
  if (result.outcome === "applied" || result.outcome === "partial") {
    return { ok: true, detail: result.detail ?? "", moved: result.moved, result };
  }
  const offers = (result.refused ?? []).flatMap((r) => r.options ?? []);
  const error = `${result.detail ?? result.outcome}${offers.length ? ` (it offers: ${offers.join(", ")})` : ""}`;
  return { ok: false, error, result };
}

// The move the last page of this tab left for this one, made once settled.
const kept = takeJob();
if (kept) {
  void settled()
    .then(() => moves.run(kept.move, kept.args, kept.call_ref))
    .then((result) => result && emit("stage_result", result));
}

window.voqalizeCannonhome = {
  run,
  context,
  start(next) {
    listener = next;
    const stop = start(next);
    for (const [event, payload] of backlog.splice(0)) next(event, payload);
    return stop;
  },
  commands: moves.ids,
};
(window as unknown as Record<string, unknown>).__voqalizeTest = { press, go, intoCheckout, forbiddenPath, privateField };
