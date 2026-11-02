/**
 * The returns form's Stage performers, held to Stage's rules on the real form
 * (CONTRACT.md v4): every declared move has a performer under its class, each
 * reports one result, nothing on the page changes before the spotlight rings
 * it, a value the form does not offer is refused with the values it does —
 * and a whole return can be made by moves alone, ending on the confirmation.
 */
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { Moves, Spotlight } from "@voqalize/stage";
import { checkRegistry, conformance } from "@voqalize/stage/conformance";
import { productsInCategory } from "../data/catalog";
import { ReturnsConfirmation, ReturnsForm } from "../pages/Returns";
import { findOrder } from "../returns/orders";
import { useReturns } from "../returns/store";
import { useCart } from "../state/cart";
import { placeOrder, useCheckout } from "../state/checkout";
import { useOrders } from "../state/orders";
import { returnsPerformers } from "./performers";
import { scene } from "./scene.gen";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
Element.prototype.scrollIntoView = function () {};

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const settle = () => sleep(120);
const CHAIR = "desk-chair-with-aluminum-frame";
const SAM = "sam.rivera@example.com";

let root: ReturnType<typeof createRoot> | null = null;

function moves(): Moves {
  const m = new Moves(new Spotlight({ color: "#4b45c6", beatMs: 0, dwellMs: 0 }));
  scene.registerAll(m, returnsPerformers());
  return m;
}

/** The form on a fresh page, at `/returns/start` with this order (or none). */
async function openForm(order?: string) {
  root?.unmount();
  document.body.innerHTML = "";
  useReturns.getState().reset();
  const host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  root.render(
    <MemoryRouter initialEntries={[order ? `/returns/start?order=${order}` : "/returns/start"]}>
      <Routes>
        <Route path="/returns/start" element={<ReturnsForm />} />
        <Route path="/returns/confirmation" element={<ReturnsConfirmation />} />
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
});
afterAll(() => root?.unmount());

describe("returns performers", () => {
  it("registers every declared move under its class", async () => {
    await openForm();
    expect(checkRegistry(scene, moves())).toEqual([]);
  });

  it("ring before they act, and report once", async () => {
    await openForm();
    const m = moves();
    const found = await conformance(scene, m, [
      { move: "returns.find", args: { order_number: "FH-20418", email: SAM }, setup: settle },
      { move: "returns.select_item", args: { product_id: CHAIR, qty: 1 }, setup: settle },
      { move: "returns.next_step", args: {}, setup: settle },
      { move: "returns.fill", args: { field: "reason", value: "doesnt_suit_room" }, setup: settle },
      { move: "returns.fill", args: { field: "condition", value: "unused_in_packaging" }, setup: settle },
      { move: "returns.open_step", args: { step: 2 }, setup: settle },
      { move: "returns.fill", args: { field: "resolution", value: "exchange" }, setup: settle },
      { move: "returns.fill", args: { field: `exchange_variant_${CHAIR}`, value: "Walnut" }, setup: settle },
      { move: "returns.fill", args: { field: "collection", value: "pickup" }, setup: settle },
      { move: "returns.fill", args: { field: "pickup_window", value: "saturday" }, setup: settle },
    ]);
    expect(found.filter((f) => f.level === "error")).toEqual([]);
    const s = useReturns.getState();
    expect(s.order_number).toBe("FH-20418");
    expect(s.email).toBe(SAM);
    expect(s.items[CHAIR]).toBe(1);
    expect(s.reason).toBe("doesnt_suit_room");
    expect(s.exchange[CHAIR]).toBe("Walnut");
    expect(s.by.reason).toBe("emily");
  });

  it("answers with one short line", async () => {
    await openForm("FH-20418");
    const r = await run(moves(), "returns.fill", { field: "reason", value: "doesnt_suit_room" });
    expect(r?.outcome).toBe("applied");
    expect(r?.detail).toBe("reason set to doesn't suit the room");
  });

  it("refuses a value the form does not offer, with the values it does", async () => {
    await openForm("FH-20418");
    const r = await run(moves(), "returns.fill", { field: "reason", value: "too_big" });
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("doesnt_suit_room");
  });

  it("fills the email the shopper said, and refuses something that is not one", async () => {
    await openForm("FH-20418");
    const m = moves();
    expect((await run(m, "returns.fill", { field: "email", value: "not an email" }))?.outcome).toBe("refused");
    expect((await run(m, "returns.fill", { field: "email", value: SAM }))?.outcome).toBe("applied");
    expect(useReturns.getState().by.email).toBe("emily");
  });

  it("refuses to submit while a step still needs something, naming it", async () => {
    await openForm("FH-20418");
    const r = await run(moves(), "returns.submit", {});
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("email");
  });

  it("refuses a step that does not exist, and one not reached yet", async () => {
    await openForm("FH-20418");
    const m = moves();
    expect((await run(m, "returns.open_step", { step: 9 }))?.outcome).toBe("refused");
    const r = await run(m, "returns.open_step", { step: 4 });
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("reached step 1");
  });
});

describe("returns.find", () => {
  it("fills step 1, looks the order up and moves to step 2", async () => {
    await openForm();
    const r = await run(moves(), "returns.find", { order_number: "fh 20418", email: SAM });
    expect(r?.outcome).toBe("applied");
    expect(r?.detail).toContain("found FH-20418");
    expect(useReturns.getState().step).toBe(2);
    expect((document.querySelector('input[name="email"]') as HTMLInputElement | null)?.value ?? SAM).toBe(SAM);
  });

  it("refuses with the exact reason", async () => {
    await openForm();
    const m = moves();
    const none = await run(m, "returns.find", { order_number: "FH-99999", email: SAM });
    expect(none?.outcome).toBe("refused");
    expect(JSON.stringify(none)).toContain("there is no order FH-99999");
    const wrong = await run(m, "returns.find", { order_number: "FH-20418", email: "someone@example.com" });
    expect(JSON.stringify(wrong)).toContain("does not match");
    const late = await run(m, "returns.find", { order_number: "FH-20155", email: "jo.chen@example.com" });
    expect(JSON.stringify(late)).toContain("outside the 30-day window");
    const coming = await run(m, "returns.find", { order_number: "FH-20502", email: "jo.chen@example.com" });
    expect(JSON.stringify(coming)).toContain("not been delivered");
    expect(useReturns.getState().step).toBe(1);
  });
});

describe("returns.next_step", () => {
  it("validates like Continue, naming the missing fields", async () => {
    await openForm();
    const m = moves();
    await run(m, "returns.find", { order_number: "FH-20418", email: SAM });
    const r = await run(m, "returns.next_step", {});
    expect(r?.outcome).toBe("refused");
    expect(JSON.stringify(r)).toContain("items");
    await run(m, "returns.select_item", { product_id: CHAIR, qty: 1 });
    const ok = await run(m, "returns.next_step", {});
    expect(ok?.outcome).toBe("applied");
    expect(ok?.detail).toBe("on step 3, reason");
    const three = await run(m, "returns.next_step", {});
    expect(JSON.stringify(three)).toContain("reason, condition");
  });
});

describe("returns.select_item", () => {
  it('takes qty "1" as 1', async () => {
    await openForm();
    const m = moves();
    await run(m, "returns.find", { order_number: "FH-20418", email: SAM });
    const r = await run(m, "returns.select_item", { product_id: CHAIR, qty: "1" });
    expect(r?.outcome).toBe("applied");
    expect(useReturns.getState().items[CHAIR]).toBe(1);
  });

  it("refuses more than were ordered, and an item not in the order", async () => {
    await openForm();
    const m = moves();
    await run(m, "returns.find", { order_number: "FH-20418", email: SAM });
    expect((await run(m, "returns.select_item", { product_id: CHAIR, qty: "3" }))?.outcome).toBe("refused");
    const other = await run(m, "returns.select_item", { product_id: "oatmeal-wool-runner", qty: 1 });
    expect(other?.outcome).toBe("refused");
    expect(JSON.stringify(other)).toContain(CHAIR);
  });
});

describe("an order placed here", () => {
  it("is saved in the contract's shape, delivered at placement, and can be returned", async () => {
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
    expect(saved).toHaveLength(1);
    expect(saved[0]).toMatchObject({ number: "FH-40001", email: "ada@example.com", name: "Ada Lane", status: "delivered" });
    expect(saved[0].lines[0]).toMatchObject({ product_id: desk.id, variant_id: desk.variants[0].id, qty: 2, title: desk.title });
    expect(typeof saved[0].placed_at).toBe("string");
    expect(findOrder("FH-40001")?.delivered_days_ago).toBe(0);

    await openForm();
    const m = moves();
    const found = await run(m, "returns.find", { order_number: "FH-40001", email: "ada@example.com" });
    expect(found?.outcome).toBe("applied");
    expect((await run(m, "returns.select_item", { product_id: desk.id, qty: "2" }))?.outcome).toBe("applied");
    expect(useReturns.getState().items[desk.id]).toBe(2);
  });
});

describe("a whole return, by moves alone", () => {
  it("find → select → next → reason, condition → next → resolution → next → collection → next → submit", async () => {
    await openForm();
    const m = moves();
    const steps: [string, unknown][] = [
      ["returns.find", { order_number: "FH-20418", email: SAM }],
      ["returns.select_item", { product_id: CHAIR, qty: "1" }],
      ["returns.next_step", {}],
      ["returns.fill", { field: "reason", value: "changed_mind" }],
      ["returns.fill", { field: "condition", value: "unused_in_packaging" }],
      ["returns.next_step", {}],
      ["returns.fill", { field: "resolution", value: "refund" }],
      ["returns.next_step", {}],
      ["returns.fill", { field: "collection", value: "pickup" }],
      ["returns.fill", { field: "pickup_window", value: "weekday_morning" }],
      ["returns.next_step", {}],
      ["returns.submit", {}],
    ];
    for (const [move, args] of steps) {
      const r = await run(m, move, args);
      expect([move, r?.outcome]).toEqual([move, "applied"]);
    }
    await sleep(300);
    expect(document.querySelector(".return-ref")?.textContent).toMatch(/^RT-20418-\d+$/);
    expect(JSON.parse(localStorage.getItem("fernhollow-returns") ?? "[]")).toHaveLength(1);
  });
});
