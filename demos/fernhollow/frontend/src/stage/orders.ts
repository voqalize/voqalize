/**
 * The orders page and an order's return form on Stage (CONTRACT.md): every
 * `orders.*` and `returns.*` move, and the events the brain hears about both.
 * Registered once, in the app shell (`useStoreMoves` calls `useOrderMoves`),
 * never per page: a move sent straight after a navigation must not be refused
 * as "not on screen". So each performer opens its own page first when it is
 * not showing (the order's detail, or the order's return form), waits for the
 * part, brings its whole group into view, rings it, then changes the same
 * store a tap would, and answers one short line the agent can repeat.
 *
 * Events carry values (they are choices, never personal data) and say who
 * made the change: the agent when one of these performers did, the visitor
 * otherwise — read off the stores' own `by`, not a time window.
 */
import * as React from "react";
import type { MoveContext, Performers } from "@voqalize/stage";
import { getProduct } from "../data/catalog";
import {
  type AccountOrder,
  allOrders,
  bookedSlot,
  canCancel,
  canMove,
  dayLabel,
  findOrder,
  isOnTheWay,
  normalOrderNumber,
  RETURN_WINDOW_DAYS,
  returnable,
  slotLabel,
  slotShort,
  statusOf,
  useAccount,
  useOrderView,
  whyNoReturn,
} from "../orders/tracking";
import { CHOICE_FIELDS, CHOICES, type ChoiceField, exchangeOptions, FIELD_SPOKEN, LAST_STEP, SPOKEN, STEPS, stepOfField, labelOf } from "../returns/orders";
import { currentOrder, filledNames, firstMissing, markAgentPress, missingFields, storedReturns, useReturns } from "../returns/store";
import { emily } from "../voice/controller";
import type { By } from "../voice/events";
import { type useAppStage, useMove } from "./host";
import { revealGroup } from "./reveal";
import type { scene } from "./scene.gen";

type Spec = typeof scene.spec;
type AppStage = ReturnType<typeof useAppStage.getState>["stage"];

const ORDER_MOVES = [
  "orders.open",
  "orders.show_slots",
  "orders.reschedule",
  "orders.cancel",
  "orders.request_earlier",
  "orders.start_return",
  "returns.select_item",
  "returns.fill",
  "returns.open_step",
  "returns.next_step",
  "returns.submit",
] as const;
export type OrderMove = (typeof ORDER_MOVES)[number];

// ── The page, found and opened ─────────────────────────────────────────────

const q = (sel: string) => document.querySelector(sel);
const part = (name: string) => q(`[data-stage-part="${CSS.escape(name)}"]`);
const thing = (name: string) => q(`[data-stage-thing="${CSS.escape(name)}"]`);
const ordersPage = () => q("[data-orders-page]");
const formFor = (n: string) => q(`[data-return-form="${CSS.escape(n)}"]`);

/** Wait for React to put `find()` on the page. */
async function appear(find: () => Element | null, ms = 2500): Promise<Element | null> {
  const end = Date.now() + ms;
  for (;;) {
    const el = find();
    if (el || Date.now() > end) return el;
    await new Promise((r) => setTimeout(r, 30));
  }
}

const go = (path: string) => emily.navigate({ page: path.replace(/^\//, "") });

/** Bring `el`'s whole group into view and ring it. */
async function ring(c: MoveContext, el: Element, label: string) {
  await revealGroup(el);
  await c.ring(el, label);
}

async function ringPart(c: MoveContext, name: string, label: string, missing: string): Promise<Element> {
  const el = (await appear(() => part(name))) ?? c.refuse("move", missing);
  await ring(c, el, label);
  return el;
}

const orderOrRefuse = (c: MoveContext, number: string): AccountOrder => {
  const n = normalOrderNumber(number);
  return findOrder(n) ?? c.refuse("order_number", `there is no order ${n}; the account's orders are ${allOrders().map((o) => o.number).join(", ")}`, allOrders().map((o) => o.number));
};

/**
 * The order's detail on the orders page: when the page shows, its card is
 * ringed before the order opens, as a tap would; otherwise the page opens on
 * the order.
 */
async function openOrder(o: AccountOrder, c: MoveContext): Promise<Element> {
  const detail = () => thing(`order:${o.number}`);
  if (!detail()) {
    if (ordersPage()) {
      const card = part(`order-card:${o.number}`);
      if (card) await ring(c, card, o.number);
    }
    useOrderView.getState().setOpen(o.number, "emily");
    go(`/orders?order=${o.number}`);
  }
  return (await appear(detail)) ?? c.refuse("order_number", "the orders page did not open");
}

/** The order's return form, opened if it is not showing. */
async function openForm(c: MoveContext): Promise<{ order: AccountOrder; form: Element }> {
  const s = useReturns.getState();
  const order = currentOrder(s) ?? c.refuse("move", "no return form is open; start one on a delivered order with orders.start_return");
  if (!formFor(order.number)) go(`/orders/return?order=${order.number}`);
  const form = (await appear(() => formFor(order.number))) ?? c.refuse("move", `the return form for ${order.number} did not open`);
  return { order, form };
}

/** Bring a step in front: ring its card first, then open it. */
async function openStep(step: number, c: MoveContext): Promise<void> {
  if (useReturns.getState().step === step) return;
  const el = await appear(() => thing(`step-${step}`));
  if (el) await ring(c, el, STEPS[step - 1].title);
  useReturns.getState().setStep(step, "emily");
  await appear(() => q(`[data-stage-thing="step-${step}"].is-open`), 600);
}

/** Refuse when a step before `step` still needs something, naming it. */
function earlierComplete(c: MoveContext, step: number, arg = "field") {
  const s = useReturns.getState();
  for (let n = 1; n < step; n++) {
    const gap = missingFields(s, n);
    if (gap.length) c.refuse(arg, `step ${n}, ${STEPS[n - 1].title.toLowerCase()}, still needs ${gap.join(", ")} first`, gap);
  }
}

const titleOf = (pid: string, fallback: string) => getProduct(pid)?.title ?? fallback;
const itemsLine = (o: AccountOrder) =>
  o.lines.map((l) => `${l.product_id} (${titleOf(l.product_id, l.title)}, ${l.variant}, ${l.qty} ordered)`).join("; ");

/** One line about where an order is and what it allows. */
function orderLine(o: AccountOrder): string {
  const st = statusOf(o);
  const slot = bookedSlot(o);
  switch (st) {
    case "packed":
      return `order ${o.number} open: packed, delivery booked for ${slot ? slotLabel(slot) : "a day we will agree"}; the day can still change and it can still be cancelled`;
    case "on_the_way":
      return `order ${o.number} open: on its way, due ${slot ? slotLabel(slot) : "soon"}; the day can no longer change and it cannot be cancelled, an earlier delivery can be requested`;
    case "out_for_delivery":
      return `order ${o.number} open: out for delivery ${slot ? slotLabel(slot) : "today"}${o.tracking.delivery.stops_before ? `, ${o.tracking.delivery.stops_before} stops before yours` : ""}; an earlier delivery can be requested`;
    case "delivered": {
      const r = returnable(o);
      return r.kind === "eligible"
        ? `order ${o.number} open: delivered ${dayLabel(-r.days)}, ${r.daysLeft} days left to start a return`
        : `order ${o.number} open: delivered ${dayLabel(-(o.delivered_days_ago ?? 0))}, outside the ${RETURN_WINDOW_DAYS}-day return window`;
    }
    case "cancelled":
      return `order ${o.number} open: cancelled`;
  }
}

/** Why a packed-only action is refused now. */
function notPacked(o: AccountOrder, what: "cancel" | "move"): string {
  const st = statusOf(o);
  if (st === "cancelled") return `order ${o.number} is cancelled`;
  if (isOnTheWay(st)) {
    return what === "cancel"
      ? `order ${o.number} is on its way, so it can no longer be cancelled; an earlier delivery can be requested instead`
      : `order ${o.number}: ${o.tracking.why_not ?? "it is on its way, so the day can no longer be changed"}`;
  }
  if (st === "delivered") {
    return what === "cancel"
      ? `order ${o.number} was delivered, so it cannot be cancelled; it can be returned within ${RETURN_WINDOW_DAYS} days of delivery instead`
      : `order ${o.number} has already been delivered`;
  }
  return `order ${o.number} has no other days to move to`;
}

// ── Performers ─────────────────────────────────────────────────────────────

/** A performer as the debug console's run-by-hand calls it. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ByHand = (args: any, c: MoveContext) => Promise<string>;

/** The move id → performer map (the shell registers it; the debug console runs it by hand). */
export function orderPerformers(): Record<OrderMove, ByHand> {
  return typed() as unknown as Record<OrderMove, ByHand>;
}

function typed(): Pick<Performers<Spec>, OrderMove> {
  return {
    "orders.open": async ({ order_number }, c) => {
      const o = orderOrRefuse(c, order_number);
      const el = await openOrder(o, c);
      await ring(c, el, o.number);
      return orderLine(o);
    },

    "orders.show_slots": async ({ order_number }, c) => {
      const o = orderOrRefuse(c, order_number);
      if (!canMove(o)) c.refuse("order_number", notPacked(o, "move"));
      await openOrder(o, c);
      if (!useOrderView.getState().picking) {
        await ringPart(c, `order:${o.number}:change`, "Change delivery day", "the delivery day is not on screen");
        useOrderView.getState().setPicking(true, bookedSlot(o)?.id ?? null);
      }
      const picker = (await appear(() => part(`order:${o.number}:slots`))) ?? c.refuse("order_number", "the delivery days did not open");
      await ring(c, picker, "Delivery days");
      const booked = bookedSlot(o);
      return `showing the days ${o.number} can move to: ${o.tracking.slots.map(slotShort).join(", ")}${booked ? `; booked now for ${slotShort(booked)}` : ""}`;
    },

    "orders.reschedule": async ({ order_number, slot }, c) => {
      const o = orderOrRefuse(c, order_number);
      if (!canMove(o)) c.refuse("order_number", notPacked(o, "move"));
      const ids = o.tracking.slots.map((s) => s.id);
      const s =
        o.tracking.slots.find((x) => x.id === String(slot).trim()) ??
        c.refuse("slot", `${o.number} can move to ${o.tracking.slots.map((x) => `${x.id} (${slotShort(x)})`).join(", ")}`, ids);
      await openOrder(o, c);
      if (!useOrderView.getState().picking) {
        await ringPart(c, `order:${o.number}:change`, "Change delivery day", "the delivery day is not on screen");
        useOrderView.getState().setPicking(true, bookedSlot(o)?.id ?? null);
      }
      await ringPart(c, `slot:${s.id}`, slotShort(s), "the delivery days are not on screen");
      useOrderView.getState().setPending(s.id);
      await ringPart(c, `order:${o.number}:save`, "Save", "the Save button is not on screen");
      useAccount.getState().move(o.number, s.id, "emily");
      useOrderView.getState().setPicking(false);
      return `delivery moved to ${slotLabel(s)}`;
    },

    "orders.cancel": async ({ order_number }, c) => {
      const o = orderOrRefuse(c, order_number);
      if (!canCancel(o)) c.refuse("order_number", notPacked(o, "cancel"));
      await openOrder(o, c);
      if (!useOrderView.getState().confirming) {
        await ringPart(c, `order:${o.number}:cancel`, "Cancel order", "the Cancel order button is not on screen");
        useOrderView.getState().setConfirming(true);
      }
      await ringPart(c, `order:${o.number}:cancel-yes`, "Yes, cancel", "the confirmation is not on screen");
      useAccount.getState().cancel(o.number, "emily");
      useOrderView.getState().setConfirming(false);
      return `order ${o.number} cancelled`;
    },

    "orders.request_earlier": async ({ order_number }, c) => {
      const o = orderOrRefuse(c, order_number);
      const st = statusOf(o);
      if (!isOnTheWay(st)) {
        c.refuse(
          "order_number",
          st === "packed"
            ? `order ${o.number} is still packed at the warehouse; its delivery day can be changed instead`
            : st === "delivered"
              ? `order ${o.number} has already been delivered`
              : `order ${o.number} is cancelled`,
        );
      }
      await openOrder(o, c);
      if (useAccount.getState().earlier[o.number]) {
        const note = (await appear(() => part(`order:${o.number}:earlier`))) ?? thing(`order:${o.number}`);
        if (note) await ring(c, note, "Earlier delivery requested");
        return `an earlier delivery of ${o.number} was already requested; it's a request, not a promise`;
      }
      await ringPart(c, `order:${o.number}:earlier`, "Request an earlier delivery", "the order's actions are not on screen");
      useAccount.getState().requestEarlier(o.number, "emily");
      return `asked the driver for an earlier delivery of ${o.number}; it's a request, not a promise`;
    },

    "orders.start_return": async ({ order_number }, c) => {
      const o = orderOrRefuse(c, order_number);
      const why = whyNoReturn(o);
      if (why) c.refuse("order_number", why);
      if (!(formFor(o.number) && useReturns.getState().order_number === o.number)) {
        await openOrder(o, c);
        await ringPart(c, `order:${o.number}:return`, "Start a return", "the Start a return button is not on screen");
        useReturns.getState().start(o.number, "emily");
        go(`/orders/return?order=${o.number}`);
      }
      const step = (await appear(() => formFor(o.number) && thing("step-1"))) ?? c.refuse("order_number", "the return form did not open");
      await ring(c, step, STEPS[0].title);
      const s = useReturns.getState();
      return `return form open for ${o.number}, step ${s.step}, items: ${itemsLine(o)}`;
    },

    "returns.select_item": async ({ product_id, qty }, c) => {
      const order = currentOrder(useReturns.getState()) ?? c.refuse("product_id", "no return form is open; start one with orders.start_return");
      const ids = order.lines.map((l) => l.product_id);
      const line = order.lines.find((l) => l.product_id === String(product_id).trim()) ?? c.refuse("product_id", `that item is not on ${order.number}; its items are ${ids.join(", ")}`, ids);
      // The wire may carry "1" for 1: coerce before judging it.
      const raw = qty as unknown;
      const n = raw == null || raw === "" ? 1 : Number(String(raw).trim());
      if (!Number.isInteger(n) || n < 0 || n > line.qty) {
        c.refuse("qty", `between 1 and ${line.qty}, or 0 to take it off`, Array.from({ length: line.qty + 1 }, (_, i) => String(i)));
      }
      await openForm(c);
      await openStep(1, c);
      const title = titleOf(line.product_id, line.title);
      await ringPart(c, `items:${line.product_id}`, title, "the items step is not on screen");
      useReturns.getState().setItem(line.product_id, n, "emily");
      return n === 0 ? `took the ${title.toLowerCase()} off the return` : `returning ${n} × ${title.toLowerCase()}`;
    },

    "returns.fill": async ({ field, value }, c) => {
      const f = String(field).trim();
      const v = String(value).trim();
      const s0 = useReturns.getState();
      const order = currentOrder(s0) ?? c.refuse("field", "no return form is open; start one with orders.start_return");
      const chosen = order.lines.filter((l) => s0.items[l.product_id]);
      const fields = [...CHOICE_FIELDS, ...chosen.map((l) => `exchange_variant_${l.product_id}`)];

      if (f.startsWith("qty_") || f === "items") c.refuse("field", "items and how many are chosen with returns.select_item", fields);

      if (f.startsWith("exchange_variant_")) {
        const pid = f.slice("exchange_variant_".length);
        const line = order.lines.find((l) => l.product_id === pid) ?? c.refuse("field", `that item is not on ${order.number}`, fields);
        if (!s0.items[pid]) c.refuse("field", `the ${titleOf(pid, line.title).toLowerCase()} is not on the return; tick it with returns.select_item first`, fields);
        earlierComplete(c, 3);
        if (s0.resolution !== "exchange") c.refuse("field", "set resolution to exchange first", ["resolution"]);
        const options = exchangeOptions(line);
        const pick = options.find((o) => o.toLowerCase() === v.toLowerCase()) ?? c.refuse("value", `${titleOf(pid, line.title)} comes in ${options.join(", ") || "no other option"}`, options);
        await openForm(c);
        await openStep(3, c);
        await ringPart(c, `${f}:${pick}`, `${titleOf(pid, line.title)}: ${pick}`, "the exchange options are not on screen");
        useReturns.getState().setExchange(pid, pick, "emily");
        return `exchange set to ${pick} for the ${titleOf(pid, line.title).toLowerCase()}`;
      }

      if (!(CHOICE_FIELDS as string[]).includes(f)) c.refuse("field", `the form has no field "${f}"`, fields);
      const choice = f as ChoiceField;
      const values = CHOICES[choice].map(([x]) => x as string);
      if (!values.includes(v)) c.refuse("value", `${choice} is one of ${values.join(", ")}`, values);
      const step = stepOfField(choice) ?? 1;
      earlierComplete(c, step);
      if (choice === "pickup_window" && s0.collection !== "pickup") {
        c.refuse("field", "a collection window applies only to a pickup; set collection to pickup first", ["collection"]);
      }
      await openForm(c);
      await openStep(step, c);
      await ringPart(c, `${choice}:${v}`, labelOf(choice, v), `${choice} is not on screen`);
      useReturns.getState().setChoice(choice, v, "emily");
      return `${FIELD_SPOKEN[choice]} set to ${SPOKEN[v] ?? labelOf(choice, v).toLowerCase()}`;
    },

    "returns.open_step": async ({ step }, c) => {
      const n = Number(step);
      if (!Number.isInteger(n) || n < 1 || n > LAST_STEP) c.refuse("step", `the form has ${LAST_STEP} steps`, STEPS.map((x) => String(x.n)));
      const reached = useReturns.getState().reached;
      if (n > reached) c.refuse("step", `step ${n} is not reached yet; the form has reached step ${reached}`, Array.from({ length: reached }, (_, i) => String(i + 1)));
      await openForm(c);
      const el = (await appear(() => thing(`step-${n}`))) ?? c.refuse("step", "the return form is not on screen");
      await ring(c, el, STEPS[n - 1].title);
      useReturns.getState().setStep(n, "emily");
      return `opened step ${n}, ${STEPS[n - 1].title.toLowerCase()}`;
    },

    "returns.next_step": async (_args, c) => {
      await openForm(c);
      const s = useReturns.getState();
      if (s.step >= LAST_STEP) c.refuse("step", `the form is already on step ${LAST_STEP}, review; the shopper's yes submits it`);
      const missing = missingFields(s, s.step);
      if (missing.length) c.refuse("step", `step ${s.step}, ${STEPS[s.step - 1].title.toLowerCase()}, still needs ${missing.join(", ")}`, missing);
      const button = q(`[data-stage-thing="step-${s.step}"] [data-continue]`) ?? thing(`step-${s.step}`);
      if (button) await ring(c, button, "Continue");
      const next = s.step + 1;
      useReturns.getState().setStep(next, "emily");
      return `on step ${next}, ${STEPS[next - 1].title.toLowerCase()}`;
    },

    "returns.submit": async (_args, c) => {
      const s = useReturns.getState();
      if (!currentOrder(s)) c.refuse("form", "no return form is open; start one with orders.start_return");
      const gap = firstMissing(s);
      if (gap) c.refuse("form", `step ${gap.step}, ${STEPS[gap.step - 1].title.toLowerCase()}, still needs ${gap.fields.join(", ")}`, gap.fields);
      await openForm(c);
      await openStep(LAST_STEP, c);
      const button = (await appear(() => part("return:submit"))) ?? c.refuse("form", "the review step is not on screen");
      await ring(c, button, "Submit return");
      const before = storedReturns().length;
      markAgentPress();
      (button as HTMLButtonElement).click();
      await appear(() => (storedReturns().length > before ? document.body : null), 1500);
      const ref = storedReturns().length > before ? storedReturns().at(-1)?.reference : null;
      return ref ? `return submitted, reference ${ref}` : "submit pressed";
    },
  };
}

// ── Events, with the hand that made them ───────────────────────────────────

type EventId = Parameters<NonNullable<AppStage>["scene"]["event"]>[0];

function send(stage: AppStage, id: EventId, data: Record<string, unknown>, by: By) {
  if (!stage) return;
  const agent = by === "emily" ? stage.agent : null;
  const opts = by === "emily" ? { by: "agent" as const, ...(agent ? { callRef: agent.callRef } : {}) } : { by: "visitor" as const };
  stage.page.send(stage.scene.event(id, data as never, opts));
}

/** Like `useSlice`, but the event says the hand the store recorded. */
function useStamped<T extends { stamp: number; by: By } | null>(stage: AppStage, value: T, toEvent: (v: NonNullable<T>) => [EventId, Record<string, unknown>]) {
  const last = React.useRef<number | null>(value?.stamp ?? null);
  React.useEffect(() => {
    if (!value || value.stamp === last.current) return;
    last.current = value.stamp;
    const [id, data] = toEvent(value as NonNullable<T>);
    send(stage, id, data, value.by);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, value]);
}

/** Register every orders and returns move, and send their events — once, in a shell. */
export function useOrderMoves(stage: AppStage) {
  const all = React.useMemo(() => orderPerformers(), []);
  for (const id of ORDER_MOVES) {
    // A fixed list, in a fixed order: the hooks run the same way every render.
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useMove(stage, id, all[id] as never);
  }

  const opened = useOrderView((s) => s.opened);
  useStamped(stage, opened, (e) => {
    const o = findOrder(e.order_number);
    return ["orders.opened", { order_number: e.order_number, status: o ? statusOf(o) : undefined }];
  });
  const moved = useAccount((s) => s.movedEv);
  useStamped(stage, moved, (e) => ["orders.delivery_changed", { order_number: e.order_number, slot: e.slot }]);
  const cancelled = useAccount((s) => s.cancelledEv);
  useStamped(stage, cancelled, (e) => ["orders.cancelled", { order_number: e.order_number, status: "cancelled" }]);
  const earlier = useAccount((s) => s.earlierEv);
  useStamped(stage, earlier, (e) => ["orders.earlier_requested", { order_number: e.order_number }]);

  const started = useReturns((s) => s.started);
  useStamped(stage, started, (e) => ["orders.return_started", { order_number: e.order_number, step: 1, filled: [] }]);
  const changed = useReturns((s) => s.changed);
  useStamped(stage, changed, (e) => {
    const s = useReturns.getState();
    return ["returns.field_filled", { order_number: s.order_number, field: e.field, value: e.value, filled: filledNames(s) }];
  });
  const stepped = useReturns((s) => s.stepped);
  useStamped(stage, stepped, (e) => {
    const s = useReturns.getState();
    return ["returns.step_reached", { order_number: s.order_number, step: e.step, filled: filledNames(s) }];
  });
  const submitted = useReturns((s) => s.submitted);
  useStamped(stage, submitted, (e) => ["returns.return_submitted", { order_number: e.order_number, reference: e.reference, filled: e.filled }]);
}
