/**
 * The front-of-house moves (CONTRACT.md, v5): the size finder, the gift edit,
 * the orders page and the showroom kiosk. Registered once, in the app shell,
 * so a move sent straight after a navigation is never "not on screen": each
 * performer opens its own page first when it is not showing, waits for the
 * part, rings it, then changes it, and answers one short line. They write the
 * same stores the shopper's taps do. The events the brain hears about those
 * stores are sent here too, so they reach it from whichever page is open.
 */
import type { MoveContext } from "@voqalize/stage";
import { money } from "../data/catalog";
import { GIFTS, KIOSK, type KioskScreen, kioskOption, useGifts, useKiosk } from "../frontdesk/edits";
import { bookedSlot, dayLabel, getTracked, TRACKED, useDelivery, useOrderView } from "../orders/tracking";
import { advise, nextQuestion, question, useSizeFinder } from "../sizing/finder";
import { emily } from "../voice/controller";
import { currentLanding } from "../voice/lang";
import { type useAppStage, useMove, useSlice } from "./host";

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
  await c.scrollTo(el);
  await c.ring(el, label);
  return el;
}

// ── Performers ─────────────────────────────────────────────────────────────

export const performers = {
  async "size.answer"({ question: qid, value }: { question: string; value: string }, c: MoveContext) {
    const q = question(qid) ?? c.refuse("question", `there is no question ${qid}`);
    const opt = q.options.find((o) => o.value === value) ?? c.refuse("value", `${q.label} takes ${q.options.map((o) => o.value).join(", ")}`, q.options.map((o) => o.value));
    const now = useSizeFinder.getState().answers;
    const when = q.when ?? {};
    if (qid !== "kind" && !Object.entries(when).every(([k, v]) => now[k] === v)) {
      const need = Object.entries(when).map(([k, v]) => `${k} ${v}`).join(" and ");
      c.refuse("question", `${q.label} is asked once the finder has ${need}`);
    }
    await openPage("/size-guide");
    await ringPart(c, `size:${qid}:${value}`, opt.label, "the size finder is not on screen");
    useSizeFinder.getState().set(qid, value, "emily");
    const answers = useSizeFinder.getState().answers;
    const advice = advise(answers);
    if (advice?.size) return `${opt.label} chosen; the guide picks ${advice.size}`;
    if (advice) return `${opt.label} chosen; the guide's advice is showing`;
    const next = nextQuestion(answers);
    return `${opt.label} chosen${next ? `; next: ${next.label.toLowerCase()}` : ""}`;
  },

  async "gifts.set"({ recipient, occasion, budget }: { recipient?: string | null; occasion?: string | null; budget?: number | null }, c: MoveContext) {
    const r = recipient ? (GIFTS.recipients.find((x) => x.id === recipient) ?? c.refuse("recipient", `no recipient ${recipient}`, GIFTS.recipients.map((x) => x.id))) : null;
    const o = occasion ? (GIFTS.occasions.find((x) => x.id === occasion) ?? c.refuse("occasion", `no occasion ${occasion}`, GIFTS.occasions.map((x) => x.id))) : null;
    const b = budget != null ? Number(budget) : null;
    if (b != null && !GIFTS.budgets.includes(b)) c.refuse("budget", `the budget chips are ${GIFTS.budgets.map((x) => money(x)).join(", ")}`, GIFTS.budgets.map(String));
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
      await ringPart(c, `gift:budget:${b}`, `Up to ${money(b)}`, "the gift edit is not on screen");
      set({ budget: b }, "emily");
    }
    const g = useGifts.getState();
    const who = GIFTS.recipients.find((x) => x.id === g.recipient)?.label.toLowerCase();
    const why = GIFTS.occasions.find((x) => x.id === g.occasion)?.label.toLowerCase();
    return `gift edit set: ${who}, ${why}, up to ${money(g.budget)}`;
  },

  async "orders.open"({ order_number }: { order_number: string }, c: MoveContext) {
    const o = getTracked(order_number) ?? c.refuse("order_number", `there is no order ${order_number} on this account`, TRACKED.map((x) => x.number));
    useOrderView.getState().setOpen(o.number, "emily");
    await openPage(`/orders?order=${o.number}`);
    const el = (await appear(() => thing(`order:${o.number}`))) ?? c.refuse("order_number", "the orders page is not on screen");
    await c.scrollTo(el);
    await c.ring(el, o.number);
    return `opened ${o.number}`;
  },

  async "orders.reschedule"({ order_number, slot }: { order_number: string; slot: string }, c: MoveContext) {
    const o = getTracked(order_number) ?? c.refuse("order_number", `there is no order ${order_number} on this account`, TRACKED.map((x) => x.number));
    if (!o.tracking.can_reschedule) c.refuse("order_number", o.tracking.why_not || "this delivery can no longer move");
    const s = o.tracking.slots.find((x) => x.id === slot) ?? c.refuse("slot", `${o.number} can move to ${o.tracking.slots.map((x) => x.id).join(", ")}`, o.tracking.slots.map((x) => x.id));
    const view = useOrderView.getState();
    if (view.open !== o.number) view.setOpen(o.number, "emily");
    await openPage(`/orders?order=${o.number}`);
    const change = await ringPart(c, `order:${o.number}:change`, "Change delivery day", "the order is not on screen");
    void change;
    useOrderView.getState().setPicking(true, bookedSlot(o, useDelivery.getState().moved)?.id ?? null);
    await ringPart(c, `slot:${s.id}`, `${dayLabel(s.days_from_now)}, ${s.window}`, "the delivery days are not on screen");
    useOrderView.getState().setPending(s.id);
    await ringPart(c, `order:${o.number}:save`, "Save", "the Save button is not on screen");
    useDelivery.getState().move(o.number, s.id, "emily");
    useOrderView.getState().setPicking(false);
    return `delivery moved to ${dayLabel(s.days_from_now)}, ${s.window} (${s.hours})`;
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

export type FrontDeskMove = keyof typeof performers;

/** Register the moves and send the events, once, in a shell. */
export function useStoreMoves(stage: AppStage) {
  useMove(stage, "size.answer", performers["size.answer"]);
  useMove(stage, "gifts.set", performers["gifts.set"]);
  useMove(stage, "orders.open", performers["orders.open"]);
  useMove(stage, "orders.reschedule", performers["orders.reschedule"]);
  useMove(stage, "kiosk.start", performers["kiosk.start"]);
  useMove(stage, "kiosk.answer", performers["kiosk.answer"]);
  useMove(stage, "kiosk.restart", performers["kiosk.restart"]);

  const size = useSizeFinder((s) => s.changed);
  useSlice(stage, size, (prev, next) => {
    if (!next || next.stamp === prev?.stamp) return null;
    const a = advise(useSizeFinder.getState().answers);
    return ["size.answered", { question: next.question, value: next.value, ...(a?.size ? { size: a.size } : {}) }] as const;
  });

  const gifts = useGifts((s) => s.changed);
  useSlice(stage, gifts, (prev, next) => {
    if (!next || next.stamp === prev?.stamp) return null;
    const g = useGifts.getState();
    return ["gifts.changed", { recipient: g.recipient, occasion: g.occasion, budget: g.budget }] as const;
  });

  const opened = useOrderView((s) => s.opened);
  useSlice(stage, opened, (prev, next) => {
    if (!next || next.stamp === prev?.stamp) return null;
    return ["orders.opened", { order_number: next.order_number }] as const;
  });

  const moved = useDelivery((s) => s.changed);
  useSlice(stage, moved, (prev, next) => {
    if (!next || next.stamp === prev?.stamp) return null;
    return ["orders.delivery_changed", { order_number: next.order_number, slot: next.slot }] as const;
  });

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
      el.scrollIntoView({ block: "center" });
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
  const run = performers[id] as (a: Record<string, unknown>, c: MoveContext) => Promise<string>;
  return run(args, fake);
}
