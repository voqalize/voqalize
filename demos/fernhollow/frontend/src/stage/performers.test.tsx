/**
 * The orders page's and the return form's Stage performers (src/stage/orders.ts),
 * held to Stage's rules on the real pages: every declared move has a
 * performer under its class, nothing changes before the spotlight rings it,
 * a value the page does not offer is refused with the values it does, each
 * answers one short line — and a whole return can be made by moves alone.
 */
import { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { Moves, Spotlight } from "@voqalize/stage";
import { checkRegistry, conformance } from "@voqalize/stage/conformance";
import { productsInCategory } from "../data/catalog";
import { allOrders, findOrder, statusOf, useAccount, useOrderView } from "../orders/tracking";
import { Orders } from "../pages/Orders";
import { OrderReturn, ReturnConfirmation, ReturnsRedirect } from "../pages/Returns";
import { useReturns } from "../returns/store";
import { useCart } from "../state/cart";
import { placeOrder, useCheckout } from "../state/checkout";
import { useOrders } from "../state/orders";
import { bindRouter } from "../voice/controller";
import { performers } from "./frontdesk";
import { orderPerformers } from "./orders";
import { scene } from "./scene.gen";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
Element.prototype.scrollIntoView = function () {};

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const settle = () => sleep(120);
const CHAIR = "desk-chair-with-aluminum-frame";
const CUSHION = "textured-wool-cushion-in-pebble-grey";

let root: ReturnType<typeof createRoot> | null = null;

function moves(): Moves {
  const m = new Moves(new Spotlight({ color: "#4b45c6", beatMs: 0, dwellMs: 0 }));
  scene.registerAll(m, { ...orderPerformers(), ...performers } as unknown as Parameters<typeof scene.registerAll>[1]);
  return m;
}

/** The router hands its navigate to the controller, as the shell does. */
function Bind() {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    bindRouter((p, replace) => navigate(p, { replace }), () => location.pathname);
  }, [navigate, location.pathname]);
  return null;
}

let where = "";
function Where() {
  const l = useLocation();
  where = `${l.pathname}${l.search}`;
  return null;
}

async function mount(at: string) {
  root?.unmount();
  document.body.innerHTML = "";
  const host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  root.render(
    <MemoryRouter initialEntries={[at]}>
      <Bind />
      <Where />
      <Routes>
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/return" element={<OrderReturn />} />
        <Route path="/orders/return/confirmation" element={<ReturnConfirmation />} />
        <Route path="/returns" element={<ReturnsRedirect />} />
        <Route path="/returns/start" element={<ReturnsRedirect />} />
        <Route path="/returns/confirmation" element={<ReturnsRedirect />} />
      </Routes>
    </MemoryRouter>,
  );
  await sleep(250);
}

const run = async (m: Moves, move: string, args: unknown) => {
  await settle();
  return m.run(move, args, `${move}-${Math.random().toString(36).slice(2, 7)}`);
};

beforeEach(() => {
  try {
    localStorage.clear();
  } catch {
    /* no storage */
  }
  useOrders.setState({ orders: [] });
  useReturns.getState().reset();
  useAccount.setState({ moved: {}, cancelled: {}, earlier: {}, movedEv: null, cancelledEv: null, earlierEv: null });
  useOrderView.getState().setOpen(null);
});
afterAll(() => root?.unmount());

describe("registration", () => {
  it("every declared move has a performer under its class", () => {
    expect(checkRegistry(scene, moves())).toEqual([]);
  });
});

describe("the return form", () => {
  it("opens empty on the order's items: nothing is chosen", async () => {
    await mount("/orders/return?order=FH-20418");
    const s = useReturns.getState();
    expect(s.order_number).toBe("FH-20418");
    expect(s.step).toBe(1);
    expect(s.items).toEqual({});
    expect([s.reason, s.condition, s.resolution, s.collection, s.pickup_window]).toEqual(["", "", "", "", ""]);
    expect(document.querySelectorAll('[data-return-form="FH-20418"] input:checked')).toHaveLength(0);
    expect(document.querySelector('input[name="order_number"], input[name="email"]')).toBeNull();
  });

  it("rings before it acts, opening each step itself", async () => {
    await mount("/orders/return?order=FH-20418");
    const found = await conformance(scene, moves(), [
      { move: "returns.select_item", args: { product_id: CHAIR, qty: 1 }, setup: settle },
      { move: "returns.fill", args: { field: "reason", value: "doesnt_suit_room" }, setup: settle },
      { move: "returns.fill", args: { field: "condition", value: "unused_in_packaging" }, setup: settle },
      { move: "returns.fill", args: { field: "resolution", value: "exchange" }, setup: settle },
      { move: "returns.fill", args: { field: `exchange_variant_${CHAIR}`, value: "Walnut" }, setup: settle },
      { move: "returns.fill", args: { field: "collection", value: "pickup" }, setup: settle },
      { move: "returns.fill", args: { field: "pickup_window", value: "saturday" }, setup: settle },
      { move: "returns.open_step", args: { step: 2 }, setup: settle },
    ]);
    expect(found.filter((f) => f.level === "error")).toEqual([]);
    const s = useReturns.getState();
    expect(s.items[CHAIR]).toBe(1);
    expect(s.reason).toBe("doesnt_suit_room");
    expect(s.exchange[CHAIR]).toBe("Walnut");
    expect(s.pickup_window).toBe("saturday");
    expect(s.by.reason).toBe("emily");
    expect(s.changed).toMatchObject({ field: "pickup_window", value: "saturday", by: "emily" });
  });

  it("answers with one short line", async () => {
    await mount("/orders/return?order=FH-20377");
    const m = moves();
    expect((await run(m, "returns.select_item", { product_id: CUSHION, qty: "2" }))?.detail).toBe("returning 2 × textured wool cushion in pebble grey");
    expect(useReturns.getState().changed).toMatchObject({ field: `qty_${CUSHION}`, value: "2" });
    const r = await run(m, "returns.fill", { field: "reason", value: "doesnt_suit_room" });
    expect(r?.detail).toBe("reason set to doesn't suit the room");
    expect(useReturns.getState().step).toBe(2);
  });

  it("refuses a fill whose earlier step is incomplete, naming what it needs", async () => {
    await mount("/orders/return?order=FH-20418");
    const m = moves();
    const r = await run(m, "returns.fill", { field: "reason", value: "changed_mind" });
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("items");
    await run(m, "returns.select_item", { product_id: CHAIR, qty: 1 });
    const later = await run(m, "returns.fill", { field: "collection", value: "pickup" });
    expect(later?.outcome).toBe("refused");
    expect(JSON.stringify(later)).toContain("reason, condition");
  });

  it("refuses a value the form does not offer, with the values it does", async () => {
    await mount("/orders/return?order=FH-20418");
    const r = await run(moves(), "returns.fill", { field: "reason", value: "too_big" });
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("doesnt_suit_room");
  });

  it("refuses more than were ordered, and an item not on the order", async () => {
    await mount("/orders/return?order=FH-20418");
    const m = moves();
    expect((await run(m, "returns.select_item", { product_id: CHAIR, qty: "3" }))?.outcome).toBe("refused");
    const other = await run(m, "returns.select_item", { product_id: "oatmeal-wool-runner", qty: 1 });
    expect(other?.outcome).toBe("refused");
    expect(JSON.stringify(other)).toContain(CHAIR);
  });

  it("next_step validates like Continue; open_step only to a reached step", async () => {
    await mount("/orders/return?order=FH-20418");
    const m = moves();
    expect(JSON.stringify(await run(m, "returns.next_step", {}))).toContain("items");
    const far = await run(m, "returns.open_step", { step: 4 });
    expect(far?.outcome).toBe("refused");
    expect(JSON.stringify(far)).toContain("reached step 1");
    await run(m, "returns.select_item", { product_id: CHAIR, qty: 1 });
    const ok = await run(m, "returns.next_step", {});
    expect(ok?.detail).toBe("on step 2, reason");
    expect(useReturns.getState().stepped).toMatchObject({ step: 2, by: "emily" });
  });

  it("a whole return, by moves alone, stops on review: only the shopper's hand sends it (F10)", async () => {
    await mount("/orders/return?order=FH-20418");
    const m = moves();
    const steps: [string, unknown][] = [
      ["returns.select_item", { product_id: CHAIR, qty: "1" }],
      ["returns.fill", { field: "reason", value: "changed_mind" }],
      ["returns.fill", { field: "condition", value: "unused_in_packaging" }],
      ["returns.fill", { field: "resolution", value: "refund" }],
      ["returns.fill", { field: "collection", value: "pickup" }],
      ["returns.fill", { field: "pickup_window", value: "weekday_morning" }],
      ["returns.next_step", {}],
    ];
    for (const [move, args] of steps) {
      const r = await run(m, move, args);
      expect([move, r?.outcome]).toEqual([move, "applied"]);
    }
    // No move submits, and one more Continue is refused on review.
    expect(scene.spec.moves.map((x) => x.id)).not.toContain("returns.submit");
    expect(JSON.stringify(await run(m, "returns.next_step", {}))).toContain("only the shopper can press Submit return");
    // A press that is not a person's — a script's click, as any agent's would be — sends nothing.
    const button = document.querySelector<HTMLButtonElement>('[data-stage-part="return:submit"]');
    expect(button).not.toBeNull();
    button?.click();
    await sleep(300);
    expect(document.querySelector(".return-ref")).toBeNull();
    expect(JSON.parse(localStorage.getItem("fernhollow-returns") ?? "[]")).toHaveLength(0);
    expect(useReturns.getState().submitted).toBeNull();
    // The store refuses any hand but the visitor's; the visitor's press is saved.
    expect(useReturns.getState().submit("emily")).toBeNull();
    const stored = useReturns.getState().submit("visitor");
    expect(stored?.reference).toMatch(/^RT-20418-\d+$/);
    expect(useReturns.getState().submitted).toMatchObject({ order_number: "FH-20418", by: "visitor" });
  });
});

describe("the orders page", () => {
  it("lists every order of the account and opens one", async () => {
    await mount("/orders");
    expect(document.querySelectorAll("[data-stage-part^='order-card:']")).toHaveLength(7);
    const r = await run(moves(), "orders.open", { order_number: "fh 31207" });
    expect(r?.outcome).toBe("applied");
    expect(r?.detail).toContain("order FH-31207 open: packed");
    expect(document.querySelector('[data-stage-thing="order:FH-31207"]')).not.toBeNull();
    expect(useOrderView.getState().opened).toMatchObject({ order_number: "FH-31207", by: "emily" });
  });

  it("shows the slots and moves the day of a packed order", async () => {
    await mount("/orders?order=FH-31207");
    const m = moves();
    const shown = await run(m, "orders.show_slots", { order_number: "FH-31207" });
    expect(shown?.detail).toMatch(/^showing the days FH-31207 can move to: /);
    const bad = await run(m, "orders.reschedule", { order_number: "FH-31207", slot: "d9-night" });
    expect(bad?.outcome).toBe("refused");
    expect(JSON.stringify(bad)).toContain("d3-evening");
    const moved = await run(m, "orders.reschedule", { order_number: "FH-31207", slot: "d3-evening" });
    expect(moved?.detail).toMatch(/^delivery moved to \w{3} \d+ \w{3}, evening \(5 pm to 9 pm\)$/);
    expect(useAccount.getState().moved["FH-31207"]).toBe("d3-evening");
    expect(useAccount.getState().movedEv).toMatchObject({ order_number: "FH-31207", slot: "d3-evening", by: "emily" });
  });

  it("cancels only while packed", async () => {
    await mount("/orders?order=FH-20502");
    const m = moves();
    const late = await run(m, "orders.cancel", { order_number: "FH-20502" });
    expect(late?.outcome).toBe("refused");
    expect(JSON.stringify(late)).toContain("can no longer be cancelled");
    const ok = await run(m, "orders.cancel", { order_number: "FH-31207" });
    expect(ok?.detail).toBe("order FH-31207 cancelled");
    expect(statusOf(findOrder("FH-31207")!)).toBe("cancelled");
    await settle();
    expect(document.querySelector('[data-stage-thing="order:FH-31207"] .fd-status')?.textContent).toBe("Cancelled");
  });

  it("asks for an earlier delivery only while on the way", async () => {
    await mount("/orders");
    const m = moves();
    expect((await run(m, "orders.request_earlier", { order_number: "FH-31207" }))?.outcome).toBe("refused");
    const ok = await run(m, "orders.request_earlier", { order_number: "FH-31188" });
    expect(ok?.detail).toBe("asked the driver for an earlier delivery of FH-31188; it's a request, not a promise");
    await settle();
    expect(document.body.textContent).toContain("It's a request, not a promise.");
  });

  it("starts a return only inside the window, on the order's own form", async () => {
    await mount("/orders");
    const m = moves();
    const late = await run(m, "orders.start_return", { order_number: "FH-20155" });
    expect(late?.outcome).toBe("refused");
    expect(JSON.stringify(late)).toContain("41 days ago");
    expect((await run(m, "orders.start_return", { order_number: "FH-31207" }))?.outcome).toBe("refused");
    const ok = await run(m, "orders.start_return", { order_number: "FH-31042" });
    expect(ok?.outcome).toBe("applied");
    expect(ok?.detail).toContain("return form open for FH-31042, step 1, items: matte-ceramic-vase-porcelain-cream");
    expect(where).toBe("/orders/return?order=FH-31042");
    expect(useReturns.getState().started).toMatchObject({ order_number: "FH-31042", by: "emily" });
  });

  it("an order outside the window shows Start a return disabled, with the reason", async () => {
    await mount("/orders?order=FH-20155");
    const button = document.querySelector('[data-stage-part="order:FH-20155:return"]') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(document.body.textContent).toContain("Delivered 41 days ago, outside the 30-day return window");
  });
});

describe("old URLs", () => {
  it("/returns/start?order=X lands on the order's return form, /returns on the orders page", async () => {
    await mount("/returns/start?order=FH-20418");
    expect(where).toBe("/orders/return?order=FH-20418");
    await mount("/returns");
    expect(where).toBe("/orders");
    await mount("/returns/start");
    expect(where).toBe("/orders");
  });
});

describe("an order placed here", () => {
  it("is packed, booked into the template's slot, and can be moved or cancelled", async () => {
    const desk = productsInCategory("desks")[0];
    useCart.setState({ lines: [{ product_id: desk.id, variant_id: desk.variants[0].id, qty: 2 }] });
    useCheckout.getState().reset();
    for (const [f, v] of [
      ["email", "ada@example.com"],
      ["first_name", "Ada"],
      ["last_name", "Lane"],
      ["address1", "1 Fern Way"],
      ["city", "Hollow"],
      ["postcode", "12345"],
    ] as const)
      useCheckout.getState().set(f, v);
    const order = placeOrder("FH-40001");
    expect(order?.number).toBe("FH-40001");
    const saved = JSON.parse(localStorage.getItem("fernhollow-orders") ?? "[]");
    expect(saved[0]).toMatchObject({ number: "FH-40001", name: "Ada Lane", status: "packed" });
    expect(saved[0]).not.toHaveProperty("email");
    expect(allOrders()[0].number).toBe("FH-40001");
    const o = findOrder("FH-40001")!;
    expect(o.tracking).toMatchObject({ stage: "packed", delivery: { slot: "d4-morning" }, can_reschedule: true });

    await mount("/orders");
    const m = moves();
    expect((await run(m, "orders.reschedule", { order_number: "FH-40001", slot: "d5-morning" }))?.outcome).toBe("applied");
    expect((await run(m, "orders.cancel", { order_number: "FH-40001" }))?.detail).toBe("order FH-40001 cancelled");
  });
});
