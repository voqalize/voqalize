/**
 * The adapter as the end-to-end tests inject it: the anchors (`anchor.js` in
 * the extension) and PC Factory's moves on Stage's `Moves` and spotlight, as
 * `content.js` registers them, without the call or the widget; plus the
 * checkout guard for the tests to drive directly.
 *
 * With no extension, a move that loads another page carries the rest of
 * itself through a Stage `Carrier` over this tab's `sessionStorage` (the
 * extension's keeps it with its service worker), and this page finishes it
 * once settled (`Moves.resume`) and reports its one `stage_result`, under the
 * move's own id, as the extension's next page does.
 */

import { type Carried, type Carrier, Moves, Spotlight, type StageResult } from "@voqalize/stage";

import { watchAnchors } from "../src/anchors";
import { context, type PageContext, prepare, registerMoves, reportPage, start } from "../src/pcfactory-actions";
import { forbiddenPath, go, intoCheckout, press, privateField, settled, target } from "../src/page";
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
    voqalizePcfactory?: TestAdapter;
  }
}

const KEY = "voqalize.test.then";

function takeJob(): Carried | null {
  const raw = sessionStorage.getItem(KEY);
  sessionStorage.removeItem(KEY);
  return raw ? (JSON.parse(raw) as Carried) : null;
}

const spotlight = new Spotlight(SPOTLIGHT);
const carrier: Carrier = {
  async keep(c) {
    sessionStorage.setItem(KEY, JSON.stringify(c));
  },
  async drop(callRef) {
    const raw = sessionStorage.getItem(KEY);
    if (raw && (JSON.parse(raw) as Carried).call_ref === callRef) sessionStorage.removeItem(KEY);
  },
  load(url) {
    location.assign(url);
  },
};
const moves = new Moves(spotlight, { carrier });
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
    .then(() => moves.resume(kept))
    .then((result) => result && emit("stage_result", result));
}

window.voqalizePcfactory = {
  run,
  context,
  start(next) {
    listener = next;
    reportPage(next);
    const stop = start(next);
    for (const [event, payload] of backlog.splice(0)) next(event, payload);
    return stop;
  },
  commands: moves.ids,
};
(window as unknown as Record<string, unknown>).__voqalizeTest = { press, go, target, intoCheckout, forbiddenPath, privateField };
