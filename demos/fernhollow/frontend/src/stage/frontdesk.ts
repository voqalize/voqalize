/**
 * The front-of-house moves (CONTRACT.md, v5–v6): the gift edit and the
 * showroom kiosk here; the orders page and the return form in ./orders.ts. Registered once, in the app shell,
 * so a move sent straight after a navigation is never "not on screen": each
 * performer opens its own page first when it is not showing, waits for the
 * part, rings it, then changes it, and answers one short line. They write the
 * same stores the shopper's taps do. The events the brain hears about those
 * stores are sent here too, so they reach it from whichever page is open.
 */
import type { MoveContext } from "@voqalize/stage";
import { money } from "../data/catalog";
import { BUDGET_CHIPS, GIFTS, KIOSK, type KioskScreen, budgetLabel, kioskOption, useGifts, useKiosk } from "../frontdesk/edits";
import { emily } from "../voice/controller";
import { currentLanding } from "../voice/lang";
import { type useAppStage, useMove, useSlice } from "./host";
import { orderPerformers, useOrderMoves } from "./orders";
import { revealGroup } from "./reveal";

type AppStage = ReturnType<typeof useAppStage.getState>["stage"];

const part = (name: string) => document.querySelector(`[data-stage-part="${CSS.escape(name)}"]`);
const thing = (name: string) => document.querySelector(`[data-stage-thing="${CSS.escape(name)}"]`);

/** Wait for React to put `find()` on the page. */
async function appear(find: () => Element | null, ms = 2500): Promise<Element | null> {
  const end = Date.now() + ms;
  for (;;) {
    const el = find();
    if (el || Date.now() > end) return el;
    await new Promise((r) => setTimeout(r, 30));
  }
}

/** Open `path` (router path, may carry a query) unless it is already showing. */
async function openPage(path: string): Promise<void> {
  const [bare, query = ""] = path.split("?");
  const here = currentLanding();
  const sameQuery = !query || window.location.search.replace(/^\?/, "") === query;
  if (here === bare && sameQuery) return;
  emily.navigate({ page: path.replace(/^\//, "") });
  await new Promise((r) => setTimeout(r, 120));
}

async function ringPart(c: MoveContext, name: string, label: string, missing: string): Promise<Element> {
  const el = (await appear(() => part(name))) ?? c.refuse("move", missing);
  await revealGroup(el);
  await c.ring(el, label);
  return el;
}

// ── Performers ─────────────────────────────────────────────────────────────

export const performers = {
  async "gifts.set"({ recipient, occasion, budget }: { recipient?: string | null; occasion?: string | null; budget?: number | null }, c: MoveContext) {
    const r = recipient ? (GIFTS.recipients.find((x) => x.id === recipient) ?? c.refuse("recipient", `no recipient ${recipient}`, GIFTS.recipients.map((x) => x.id))) : null;
    const o = occasion ? (GIFTS.occasions.find((x) => x.id === occasion) ?? c.refuse("occasion", `no occasion ${occasion}`, GIFTS.occasions.map((x) => x.id))) : null;
    const b = budget != null ? Number(budget) : null;
    if (b != null && !BUDGET_CHIPS.includes(b)) c.refuse("budget", `the budget chips are ${GIFTS.budgets.map((x) => money(x)).join(", ")}, or 0 for no limit`, BUDGET_CHIPS.map(String));
    if (!r && !o && b == null) c.refuse("recipient", "give at least one of recipient, occasion or budget");
    await openPage("/gifts");
    const set = useGifts.getState().set;
    if (r) {
      await ringPart(c, `gift:recipient:${r.id}`, r.label, "the gift edit is not on screen");
      set({ recipient: r.id }, "emily");
    }
    if (o) {
      await ringPart(c, `gift:occasion:${o.id}`, o.label, "the gift edit is not on screen");
      set({ occasion: o.id }, "emily");
    }
    if (b != null) {
      await ringPart(c, `gift:budget:${b}`, budgetLabel(b), "the gift edit is not on screen");
      set({ budget: b }, "emily");
    }
    const g = useGifts.getState();
    const who = GIFTS.recipients.find((x) => x.id === g.recipient)?.label.toLowerCase() ?? "nobody chosen yet";
    const why = GIFTS.occasions.find((x) => x.id === g.occasion)?.label.toLowerCase() ?? "no occasion yet";
    const cap = g.budget == null ? "no budget chosen yet" : g.budget === 0 ? "no budget limit" : `up to ${money(g.budget)}`;
    return `gift edit set: ${who}, ${why}, ${cap}`;
  },

  async "kiosk.start"(_: Record<string, never>, c: MoveContext) {
    await openPage("/kiosk");
    if (useKiosk.getState().screen !== "attract") return "the kiosk is already started";
    await ringPart(c, "kiosk:start", "Start", "the kiosk is not on screen");
    useKiosk.getState().start("emily");
    return "started";
  },

  async "kiosk.answer"({ question: qid, value }: { question: "room" | "feel" | "budget"; value: string }, c: MoveContext) {
    const q = KIOSK.questions.find((x) => x.id === qid) ?? c.refuse("question", `there is no question ${qid}`, KIOSK.questions.map((x) => x.id));
    const opt = kioskOption(qid, value) ?? c.refuse("value", `${q.label} takes ${q.options.map((o) => o.value).join(", ")}`, q.options.map((o) => o.value));
    await openPage("/kiosk");
    const k = useKiosk.getState();
    if (k.screen !== qid) k.go(qid as KioskScreen);
    await ringPart(c, `kiosk:${qid}:${opt.value}`, opt.label, "the kiosk is not on screen");
    useKiosk.getState().answer(qid, opt.value, "emily");
    return useKiosk.getState().screen === "picks" ? `${opt.label} chosen; the three picks and the QR code are showing` : `${opt.label} chosen`;
  },

  async "kiosk.restart"(_: Record<string, never>, c: MoveContext) {
    await openPage("/kiosk");
    const el = part("kiosk:restart");
    if (el) await c.ring(el, "Start over");
    useKiosk.getState().restart("emily");
    return "back to the start screen";
  },
};

export type FrontDeskMove = keyof typeof performers | keyof ReturnType<typeof orderPerformers>;

/** Register the moves and send the events, once, in a shell. */
export function useStoreMoves(stage: AppStage) {
  useMove(stage, "gifts.set", performers["gifts.set"]);
  useMove(stage, "kiosk.start", performers["kiosk.start"]);
  useMove(stage, "kiosk.answer", performers["kiosk.answer"]);
  useMove(stage, "kiosk.restart", performers["kiosk.restart"]);

  const gifts = useGifts((s) => s.changed);
  useSlice(stage, gifts, (prev, next) => {
    if (!next || next.stamp === prev?.stamp) return null;
    const g = useGifts.getState();
    return [
      "gifts.changed",
      { ...(g.recipient ? { recipient: g.recipient } : {}), ...(g.occasion ? { occasion: g.occasion } : {}), ...(g.budget != null ? { budget: g.budget } : {}) },
    ] as const;
  });

  // The orders page and the return form: their moves and events (stage/orders.ts).
  useOrderMoves(stage);

  const screen = useKiosk((s) => s.screen);
  useSlice(stage, screen, (prev, next) => (prev === undefined || prev === next ? null : (["kiosk.screen", { screen: next }] as const)));

  const answered = useKiosk((s) => s.changed);
  useSlice(stage, answered, (prev, next) => {
    if (!next || next.stamp === prev?.stamp) return null;
    return ["kiosk.answered", { question: next.question, value: next.value }] as const;
  });
}

/**
 * `?debug=1`: run a move's performer by hand, without a call, so a mid-flow
 * state can be seen and screenshotted. The ring is a plain outline here.
 */
export async function runByHand(id: FrontDeskMove, args: Record<string, unknown> = {}): Promise<string> {
  const fake = {
    move: id,
    callRef: "debug",
    async ring(el: Element | Element[]) {
      for (const e of Array.isArray(el) ? el : [el]) {
        const h = e as HTMLElement;
        h.style.outline = "3px solid var(--emily)";
        h.style.outlineOffset = "3px";
        window.setTimeout(() => {
          h.style.outline = "";
          h.style.outlineOffset = "";
        }, 1400);
      }
      await new Promise((r) => setTimeout(r, 250));
    },
    async scrollTo(el: Element) {
      await revealGroup(el);
    },
    async beat(ms = 600) {
      await new Promise((r) => setTimeout(r, ms));
    },
    async reveal() {},
    refuse(arg: string, why: string): never {
      throw new Error(`refused ${arg}: ${why}`);
    },
    progress() {},
    async keep() {},
    async drop() {},
  } as unknown as MoveContext;
  const all = { ...performers, ...orderPerformers() } as unknown as Record<string, (a: Record<string, unknown>, c: MoveContext) => Promise<string>>;
  const run = all[id];
  return run(args, fake);
}
