/**
 * `@voqalize/stage/conformance`: does a page keep Stage's rules for the moves
 * its spec declares?
 *
 * Run it from a test, against the page's own performers on a page fixture:
 *
 * ```ts
 * const moves = new Moves(new Spotlight({ color: "#000" }));
 * registerMoves(moves);                       // the site's own registration
 * const found = [
 *   ...checkRegistry(scene, moves),
 *   ...(await conformance(scene, moves, [
 *     { move: "listing.sort", args: { order: "price_asc" }, setup: () => loadFixture("listing.html") },
 *   ])),
 * ];
 * expect(found.filter((f) => f.level === "error")).toEqual([]);
 * ```
 *
 * The rules it checks:
 * - **Every declared move has a performer, under its declared class**, and no
 *   performer answers to a move the spec does not declare.
 * - **A move reports one result, under its own move id and `call_ref`**, with
 *   an outcome from the closed set.
 * - **Nothing on the page changes before the spotlight rings.** The page's DOM
 *   is watched from the moment the move starts; a change still pending when
 *   the first ring is called, or a change with no ring at all, is an error.
 *   The spotlight's own overlay is not the page.
 * - **A look that lands rings something**: a move that shows nothing is a
 *   warning.
 */

import type { Moves } from "./moves";
import type { MoveId, Scene, SceneSpec } from "./scene";
import type { StageResult } from "./wire.gen";

export interface Finding {
  level: "error" | "warning";
  move: string;
  message: string;
}

/** One move to make, on a page `setup` lays out. */
export interface Case<S extends SceneSpec = SceneSpec> {
  move: MoveId<S>;
  args: unknown;
  setup?: () => void | Promise<void>;
}

/** What one move did, as the kit saw it. */
export interface Observed {
  result: StageResult | null;
  rings: number;
  /** The page's DOM changed before the first ring was called. */
  changedBeforeRing: boolean;
  /** The page's DOM changed at all while the move ran. */
  changed: boolean;
}

const OUTCOMES = new Set(["applied", "partial", "refused", "failed", "undone", "unknown"]);

/** Every declared move registered, under its declared class; nothing else. */
export function checkRegistry<S extends SceneSpec>(scene: Scene<S>, moves: Moves): Finding[] {
  const out: Finding[] = [];
  const declared = new Set<string>();
  for (const m of scene.spec.moves) {
    declared.add(m.id);
    const cls = moves.classOf(m.id);
    if (cls === null) out.push({ level: "error", move: m.id, message: "declared, but no performer is registered" });
    else if (cls !== m.class) {
      out.push({ level: "error", move: m.id, message: `registered as ${cls}, declared ${m.class}` });
    }
  }
  for (const id of moves.ids) {
    if (!declared.has(id)) out.push({ level: "warning", move: id, message: "registered, but the spec declares no such move" });
  }
  return out;
}

function ours(node: Node | null): boolean {
  for (let n: Node | null = node; n; n = n.parentNode ?? (n as ShadowRoot).host ?? null) {
    if (n instanceof Element && n.hasAttribute("data-voqalize")) return true;
  }
  return false;
}

function pageChanges(records: MutationRecord[]): number {
  return records.filter((r) => {
    if (ours(r.target)) return false;
    const nodes = [...r.addedNodes, ...r.removedNodes];
    return !(nodes.length && nodes.every((n) => n instanceof Element && n.hasAttribute("data-voqalize")));
  }).length;
}

/** Make one move and watch what it does to the page and the spotlight. */
export async function observe(moves: Moves, id: string, args: unknown, callRef = "conformance-1"): Promise<Observed> {
  const doc = document;
  const observer = new MutationObserver(() => {});
  observer.observe(doc.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
  const spotlight = moves.spotlight;
  const ring = spotlight.ring.bind(spotlight);
  let rings = 0;
  let changedBeforeRing = false;
  let changes = 0;
  spotlight.ring = (target, opts) => {
    const before = pageChanges(observer.takeRecords());
    changes += before;
    if (rings === 0 && before > 0) changedBeforeRing = true;
    rings++;
    return ring(target, opts);
  };
  try {
    const result = await moves.run(id, args, callRef);
    changes += pageChanges(observer.takeRecords());
    if (rings === 0 && changes > 0) changedBeforeRing = true;
    return { result, rings, changedBeforeRing, changed: changes > 0 };
  } finally {
    spotlight.ring = ring;
    observer.disconnect();
  }
}

/** Make each case's move and report every rule it breaks. */
export async function conformance<S extends SceneSpec>(scene: Scene<S>, moves: Moves, cases: Case<S>[]): Promise<Finding[]> {
  const out: Finding[] = [];
  let n = 0;
  for (const c of cases) {
    const declared = scene.spec.moves.find((m) => m.id === c.move);
    if (!declared) {
      out.push({ level: "error", move: c.move, message: "a case for a move the spec does not declare" });
      continue;
    }
    await c.setup?.();
    const callRef = `conformance-${++n}`;
    const seen = await observe(moves, c.move, c.args, callRef);
    const r = seen.result;
    if (r === null) {
      out.push({ level: "warning", move: c.move, message: "reported nothing here: it went on to another page" });
      continue;
    }
    if (r.call_ref !== callRef || r.move !== c.move) {
      out.push({ level: "error", move: c.move, message: `reported as ${r.move} ${r.call_ref}, not ${c.move} ${callRef}` });
    }
    if (!OUTCOMES.has(r.outcome)) out.push({ level: "error", move: c.move, message: `unknown outcome ${r.outcome}` });
    if (seen.changedBeforeRing) {
      out.push({ level: "error", move: c.move, message: "changed the page before the spotlight rang what it touched" });
    }
    if (declared.class === "look" && r.outcome === "applied" && seen.rings === 0) {
      out.push({ level: "warning", move: c.move, message: "applied, and rang nothing: the visitor sees no change" });
    }
  }
  return out;
}
